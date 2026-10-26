"""Backend log capture and compatibility checks. No UI execution."""
import json
import hashlib
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pipeline.config import PipelineConfig
from pipeline.console_reader import ConsoleFiles, EXPORT_TRAILER, export_console, read_console, scheduler_records
from pipeline.executor import ExecutionRequest, LocalDockerExecutor
from pipeline.tool_output import ToolOutputCapture, record_scheduler_result


class ConsoleLoggingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.job = self.root / 'job_console'
        self.job.mkdir()
        self.output = self.root / 'outputs'
        self.output.mkdir()
        self.config = {'mode': 'files', 'input_files': ['/input/a.nii', '/input/b.nii'],
                       'subject_id_map': {'/input/a.nii': 'A', '/input/b.nii': 'B'},
                       'output_dir': str(self.output), 'selected_tools': {'segmentation': 'synthseg'}}
        self.save_config()
        self.payload = {'subject_id': 'A', 'input_file': '/input/a.nii', 'mode': 'detailed'}

    def save_config(self):
        (self.job / 'job_config.json').write_text(json.dumps(self.config))

    def capture(self, subject='A', text='line\n', success=True):
        config = PipelineConfig(f'/input/{subject.lower()}.nii', str(self.output), subject,
                                console_job_dir=str(self.job), console_attempt_id=f'{subject}:seg:attempt:2')
        capture = ToolOutputCapture(config, 'segmentation', 'synthseg')
        capture.write(text.encode())
        capture.finish(success, '' if success else 'Tool failed', 0 if success else 7)
        return capture

    def test_tail_count_isolation_and_complete_download(self):
        original = ''.join(f'A line {i}\n' for i in range(450))
        self.capture(text=original, success=False)
        self.capture('B', 'PRIVATE SUBJECT B OUTPUT\n')
        files = ConsoleFiles(str(self.job))
        result = read_console(files, self.payload)
        self.assertEqual(len(result['text'].splitlines()), 200)
        self.assertEqual(result['hidden_lines'], 250)
        self.assertNotIn('PRIVATE SUBJECT B', result['text'])
        self.assertEqual(result['records'][0]['exit_code'], 7)
        target = self.root / 'download.log'
        exported = export_console(files, dict(self.payload, target_file=str(target)))
        self.assertTrue(exported['ok'])
        self.assertIn(original, target.read_text())
        self.assertNotIn('PRIVATE SUBJECT B', target.read_text())
        data = target.read_bytes()
        marker = data.rfind(EXPORT_TRAILER)
        manifest = json.loads(data[marker + len(EXPORT_TRAILER):])
        self.assertEqual(manifest['subject_id'], 'A')
        self.assertEqual(len(manifest['records']), 1)
        entry = manifest['records'][0]
        raw = data[entry['offset']:entry['offset'] + entry['bytes']]
        self.assertEqual(raw, original.encode())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), entry['sha256'])
        with self.assertRaises(FileExistsError):
            export_console(files, dict(self.payload, target_file=str(target)))

    def test_combined_text_includes_every_stage_and_only_the_selected_subject(self):
        config = PipelineConfig('/input/a.nii', str(self.output), 'A', console_job_dir=str(self.job))
        for stage in ('reorientation', 'segmentation', 'stats_extraction'):
            capture = ToolOutputCapture(config, stage, 'synthseg')
            capture.write(''.join(f'{stage} line {i} ' + 'X' * 200 + '\n' for i in range(500)).encode())
            capture.finish(True, '', 0)
        self.capture('B', 'PRIVATE SUBJECT B OUTPUT\n')
        result = read_console(ConsoleFiles(str(self.job)), dict(self.payload, mode='combined'))
        self.assertLessEqual(len(result['text'].encode()), 65536)
        for stage in ('reorientation', 'segmentation', 'stats_extraction'):
            self.assertIn(f'{stage} line 499', result['text'])
        self.assertEqual(result['text'].count('Started:'), 3)
        self.assertEqual(result['text'].count('Status: SUCCESS'), 3)
        self.assertIn('earlier lines hidden.', result['text'])
        self.assertNotIn('PRIVATE SUBJECT B', result['text'])

    def test_combined_text_keeps_failures_without_an_output_capture(self):
        self.capture()
        events = [{'kind': 'progress', 'subject_id': 'A', 'stage': 'preflight',
                   'status': 'failed', 'time': 1, 'msg': 'Required image unavailable'}]
        (self.job / 'events.jsonl').write_text(json.dumps(events[0]) + '\n')
        result = read_console(ConsoleFiles(str(self.job)), dict(self.payload, mode='combined'))
        self.assertIn('Required image unavailable', result['text'])

    def test_streams_large_stdout_and_stderr_without_buffering_the_complete_result(self):
        config = PipelineConfig('/input/a.nii', str(self.output), 'A', console_job_dir=str(self.job))
        capture = ToolOutputCapture(config, 'segmentation', 'synthseg')
        program = "import sys,time; print('BEGIN',flush=True); time.sleep(.4); print(('X'*200+'\\n')*1000,end=''); print('STDERR END',file=sys.stderr); sys.exit(7)"
        original_popen = subprocess.Popen
        def fake_docker(_command, **kwargs):
            return original_popen([sys.executable, '-c', program], **kwargs)
        with patch('pipeline.executor.subprocess.Popen', side_effect=fake_docker):
            results = []
            worker = threading.Thread(target=lambda: results.append(LocalDockerExecutor().execute(
                ExecutionRequest('unused', [], [], output_capture=capture))))
            worker.start()
            deadline = time.monotonic() + 5
            while capture.path.stat().st_size == 0 and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(worker.is_alive())
            self.assertIn(b'BEGIN', capture.path.read_bytes())
            self.assertEqual(capture.meta['status'], 'running')
            worker.join(timeout=10)
            self.assertFalse(worker.is_alive())
            result = results[0]
        capture.finish(result.success, result.error, result.return_code)
        raw = capture.path.read_bytes()
        self.assertGreater(len(raw), 200000)
        self.assertIn(b'BEGIN', raw)
        self.assertIn(b'STDERR END', raw)
        self.assertLessEqual(len(result.output.encode()), 65536)
        self.assertNotIn('BEGIN', result.output)
        self.assertEqual(result.return_code, 7)
        self.assertEqual(capture.meta['bytes'], len(raw))

    def test_shared_concurrent_legacy_messages_are_not_assigned(self):
        events = [
            {'kind': 'image_start', 'time': 1, 'input_file': '/input/a.nii'},
            {'kind': 'image_start', 'time': 2, 'input_file': '/input/b.nii'},
            {'kind': 'progress', 'time': 3, 'stage': 'segmentation', 'msg': 'UNKNOWN OWNER'},
            {'kind': 'progress', 'time': 4, 'stage': 'segmentation', 'msg': '[B] PRIVATE B'},
            {'kind': 'progress', 'time': 5, 'stage': 'segmentation', 'msg': '[A] ACTUAL A'},
        ]
        (self.job / 'events.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events))
        result = read_console(ConsoleFiles(str(self.job)), dict(self.payload, mode='summary'))
        self.assertIn('ACTUAL A', result['text'])
        self.assertNotIn('PRIVATE B', result['text'])
        self.assertNotIn('UNKNOWN OWNER', result['text'])

    def test_legacy_saved_log_is_available_without_claiming_complete_output(self):
        directory = self.output / 'A' / 'logs'
        directory.mkdir(parents=True)
        (directory / 'synthseg.log').write_text('Stage: segmentation\n--- Output ---\nsaved tail\n')
        result = read_console(ConsoleFiles(str(self.job)), self.payload)
        self.assertIn('saved tail', result['text'])
        self.assertIsNone(result['records'][0]['attempt_number'])
        self.assertEqual(result['records'][0]['coverage'], 'partial_or_unknown')
        self.assertTrue(result['warnings'])

    def test_legacy_stage_header_uses_only_attributable_events(self):
        self.config['input_files'] = ['/input/a.nii']
        self.save_config()
        directory = self.output / 'A' / 'logs'
        directory.mkdir(parents=True)
        (directory / 'synthseg.log').write_text('saved output\n')
        events = [
            {'kind': 'image_start', 'input_file': '/input/a.nii', 'time': 1},
            {'kind': 'progress', 'stage': 'segmentation', 'status': 'running', 'time': 2},
            {'kind': 'progress', 'stage': 'segmentation', 'status': 'failed', 'subject_id': 'B', 'time': 3},
            {'kind': 'progress', 'stage': 'segmentation', 'status': 'success', 'time': 4},
        ]
        (self.job / 'events.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events))
        result = read_console(ConsoleFiles(str(self.job)), self.payload)
        self.assertEqual(result['records'][0]['started_at'], 2)
        self.assertEqual(result['records'][0]['status'], 'success')
        self.assertEqual(result['records'][0]['metadata_scope'], 'stage')
        self.assertIsNone(result['records'][0]['attempt_number'])

    def test_large_activity_history_stays_bounded_and_reports_omissions(self):
        with (self.job / 'events.jsonl').open('w') as handle:
            for number in range(1300):
                handle.write(json.dumps({'kind': 'progress', 'subject_id': 'A', 'stage': 'segmentation',
                                         'time': number + 1, 'msg': 'X' * 4000}) + '\n')
        files = ConsoleFiles(str(self.job))
        first = read_console(files, dict(self.payload, mode='summary'))
        self.assertTrue(first['loading_older'])
        final = read_console(files, dict(self.payload, mode='summary'))
        self.assertFalse(final['loading_older'])
        self.assertTrue(files.history_trimmed)
        self.assertLessEqual(len(final['text'].encode()), 65536)
        self.assertTrue(any('history limit' in warning for warning in final['warnings']))

    def test_subject_input_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            read_console(ConsoleFiles(str(self.job)), dict(self.payload, subject_id='B'))

    def test_unknown_mode_does_not_report_success_with_empty_text(self):
        self.capture()
        with self.assertRaisesRegex(ValueError, 'Unsupported console mode'):
            read_console(ConsoleFiles(str(self.job)), dict(self.payload, mode='unrecognized'))
        response = read_console(ConsoleFiles(str(self.job)), dict(self.payload, mode='combined'))
        self.assertIn('combined', response['supported_modes'])
        self.assertTrue(response['text'])

    def test_new_job_does_not_relabel_old_output_as_current_tool_output(self):
        self.config['console_log_version'] = 1
        self.save_config()
        directory = self.output / 'A' / 'logs'
        directory.mkdir(parents=True)
        (directory / 'synthseg.log').write_text('OUTPUT FROM AN EARLIER JOB')
        result = read_console(ConsoleFiles(str(self.job)), self.payload)
        self.assertEqual(result['records'], [])
        self.assertNotIn('EARLIER JOB', result['text'])

    def test_actual_scheduler_retry_decision_is_preserved(self):
        capture = self.capture(success=False)
        retry_time = datetime(2026, 10, 27, 0, 0, 0, tzinfo=timezone.utc)
        receipt = SimpleNamespace(task_state=SimpleNamespace(value='RETRY_DELAY'), retry_eligible_at=retry_time)
        record_scheduler_result(self.job, 'A', capture.meta['attempt_id'], receipt)
        result = read_console(ConsoleFiles(str(self.job)), dict(self.payload, mode='summary'))
        self.assertIn('Retry scheduled:', result['text'])
        self.assertEqual(result['records'][0]['retry_eligible_at'], retry_time.timestamp())

    def test_capture_write_error_does_not_raise_into_processing(self):
        config = PipelineConfig('/input/a.nii', str(self.output), 'A', console_job_dir=str(self.job))
        capture = ToolOutputCapture(config, 'segmentation', 'synthseg')
        capture.handle.close()
        class FailedDisk:
            closed = False
            def write(self, _data):
                raise OSError('Disk full')
            def close(self):
                self.closed = True
        capture.handle = FailedDisk()
        capture.write(b'first output')
        capture.write(b'more output')
        capture.finish(True, '', 0)
        metadata = json.loads(capture.meta_path.read_text())
        self.assertEqual(metadata['status'], 'success')
        self.assertEqual(metadata['coverage'], 'partial')
        self.assertIn('Disk full', metadata['capture_error'])

    def test_huge_line_has_a_byte_limit_and_full_download(self):
        content = 'X' * 300000
        self.capture(text=content)
        files = ConsoleFiles(str(self.job))
        result = read_console(files, self.payload)
        self.assertLessEqual(len(result['text']), 65536)
        self.assertTrue(result['byte_limited'])
        self.assertEqual(result['hidden_lines'], 0)
        target = self.root / 'long.log'
        export_console(files, dict(self.payload, target_file=str(target)))
        self.assertIn(content, target.read_text())

    def test_old_scheduler_attempt_records_are_read_without_writing_database(self):
        db = self.job / 'neuroflow_workspace.sqlite'
        with sqlite3.connect(db) as connection:
            connection.executescript('''
                CREATE TABLE tasks(task_id TEXT, image_id TEXT, metadata_json TEXT);
                CREATE TABLE attempts(attempt_id TEXT, task_id TEXT, result_id TEXT,
                    attempt_number INTEGER, started_at TEXT, finished_at TEXT, created_at TEXT, state TEXT);
                CREATE TABLE results(result_id TEXT, exit_code INTEGER, error_message TEXT, status TEXT);
            ''')
            connection.execute('INSERT INTO tasks VALUES(?,?,?)', ('A:seg', 'A', json.dumps({'pipeline_stage': 'segmentation', 'pipeline_tool_key': 'synthseg'})))
            connection.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?)', ('attempt-1', 'A:seg', 'r1', 1, '2026-10-26T00:00:00Z', '2026-10-26T00:01:00Z', '2026-10-26T00:00:00Z', 'FAILED'))
            connection.execute('INSERT INTO results VALUES(?,?,?,?)', ('r1', 137, 'Process exited', 'FAILED'))
        connection.close()
        before = db.read_bytes()
        result = read_console(ConsoleFiles(str(self.job)), dict(self.payload, mode='summary'),
                              lambda subject: scheduler_records(str(self.job), subject))
        self.assertIn('Attempt 1', result['text'])
        self.assertIn('Exit code: 137', result['text'])
        self.assertEqual(before, db.read_bytes())
        self.assertFalse(Path(str(db) + '-wal').exists())
        self.assertFalse(Path(str(db) + '-shm').exists())


if __name__ == '__main__':
    unittest.main()
