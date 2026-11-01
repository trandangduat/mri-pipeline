import csv
from dataclasses import asdict
import json
import sqlite3
from types import SimpleNamespace

import pytest

from pipeline.benchmark_reports import STEP_FIELDS, SUMMARY_FIELDS, write_scheduler_benchmarks
from pipeline.config import BatchImageResult, StepResult
from pipeline.executor import ExecutionRequest, LocalDockerExecutor
from pipeline.reports import _write_batch_benchmark_reports


def table(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream, delimiter='\t'))


def test_scheduler_exports_attempts_retries_raw_metrics_and_final_status(tmp_path, monkeypatch):
    monkeypatch.setattr('pipeline.benchmark_reports._host_info', lambda: {'hostname': 'worker'})
    database = tmp_path / 'neuroflow_workspace.sqlite'
    with sqlite3.connect(database) as c:
        c.execute('create table images(image_id text, canonical_spec_json text)')
        c.execute('insert into images values (?,?)', ('subject', json.dumps({'metadata': {'input_file': '/input/I7054.nii', 'subject_id': 'subject'}})))
        c.execute('create table tasks(task_id text,image_id text,stage_id text,state text,metadata_json text)')
        c.execute('insert into tasks values (?,?,?,?,?)', ('task', 'subject', 'segmentation', 'COMPLETED', json.dumps({'pipeline_stage': 'segmentation', 'pipeline_tool_key': 'fastsurfer_segmentation'})))
        c.execute('create table attempts(attempt_id text,task_id text,attempt_number integer,retry_ordinal integer,configuration_id text,execution_mode text,cpu_threads integer,gpu_id text,reserved_ram_mib integer,reserved_gpu_memory_mib integer,reserved_disk_mib integer,estimated_runtime_ms integer,started_at text,finished_at text)')
        c.execute('create table results(attempt_id text,status text,exit_code integer,validation_passed integer,error_category text,error_message text,metrics_json text,metadata_json text)')
        for index, success in [(1, False), (2, True)]:
            started, finished = f'2026-11-01T00:00:0{index}+00:00', f'2026-11-01T00:00:0{index+1}+00:00'
            c.execute('insert into attempts values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (str(index), 'task', index, index-1, 'cpu_4', 'cpu', 4, None, 100, None, None, 1000, started, finished))
            step = StepResult('segmentation', 'fastsurfer_segmentation', success, 1.123456 * index,
                              peak_ram_bytes=1048577 if success else None, container_name=f'container-{index}',
                              cpu_sample_count=3, ram_sample_count=3 if success else 0)
            c.execute('insert into results values (?,?,?,?,?,?,?,?)', (str(index), 'SUCCEEDED' if success else 'FAILED',
                0 if success else 1, int(success), None, None, json.dumps({'runtime_ms': 1123 * index}), json.dumps({'application_step': asdict(step)})))
    (tmp_path / 'job_status.json').write_text(json.dumps({'state': 'completed', 'started_at': 100, 'finished_at': 110, 'duration_sec': 10}))
    write_scheduler_benchmarks(tmp_path, {'threads': 50, 'ram_percent': 90, 'output_dir': '/output', 'neuroflow_policy': 'B6'})
    steps, summaries = table(tmp_path / 'benchmark_steps.tsv'), table(tmp_path / 'benchmark_summary.tsv')
    assert list(steps[0]) == STEP_FIELDS and len(STEP_FIELDS) == 58
    assert list(summaries[0]) == SUMMARY_FIELDS and len(SUMMARY_FIELDS) == 37
    assert len(steps) == 2 and steps[0]['peak_ram_bytes'] == 'NA'
    assert steps[1]['run_sec'] == '2.246912' and steps[1]['peak_ram_bytes'] == '1048577'
    assert steps[1]['cpu_threads'] == '4' and steps[1]['retry_ordinal'] == '1'
    assert steps[1]['cpu_sample_count'] == '3' and steps[0]['ram_sample_count'] == '0'
    job = next(r for r in summaries if r['record_type'] == 'JOB')
    assert job['attempts'] == '2' and job['retries'] == '1'
    assert job['successful_attempts'] == '1' and job['failed_attempts'] == '1'
    assert job['elapsed_wall_sec'] == '10' and job['final_status'] == 'completed'
    assert len(summaries) == 3


def test_standard_runner_headers_export_recorded_values(tmp_path, monkeypatch):
    monkeypatch.setattr('pipeline.reports._host_info', lambda: {'hostname': 'worker'})
    step = StepResult('segmentation', 'fastsurfer_segmentation', True, 12.5, peak_ram_bytes=1048576)
    _write_batch_benchmark_reports(str(tmp_path), [BatchImageResult('/input/I7054.nii', 'subject', '/out/subject', True, 13, [step])], {'threads': 4})
    records = table(tmp_path / 'benchmark/benchmark_steps.tsv')
    summary = table(tmp_path / 'benchmark/benchmark_summary.tsv')
    assert records[0]['run_sec'] == '12.5' and records[0]['input_file']
    assert records[0]['peak_ram_bytes'] == '1048576'
    assert summary[0]['avg_run_sec'] == '12.5' and summary[0]['images'] == '1'


def test_executor_records_and_runs_immutable_image(tmp_path, mocker):
    digest = 'sha256:' + 'a' * 64
    query = mocker.patch('pipeline.image_identity.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps([{'Id': digest, 'RepoDigests': ['repo@sha256:registry']}]), stderr=''))
    process = mocker.MagicMock()
    process.communicate.return_value = ('ok', '')
    process.returncode = 0
    popen = mocker.patch('pipeline.executor.subprocess.Popen', return_value=process)
    mocker.patch('pipeline.executor.threading.Thread.start')
    mocker.patch('pipeline.executor.threading.Thread.join')
    path = tmp_path / 'container_images' / 'stage.json'
    result = LocalDockerExecutor().execute(ExecutionRequest('repo:latest', [], [], container_name='stage', image_receipt_path=str(path)))
    assert digest in popen.call_args.args[0] and 'repo:latest' not in popen.call_args.args[0]
    assert result.image_identity['image_id'] == digest
    assert json.loads(path.read_text())['status'] == 'SUCCEEDED'
    assert digest in (tmp_path / 'container_images.txt').read_text()


def test_unknown_image_identity_does_not_launch_container(tmp_path, mocker):
    mocker.patch('pipeline.image_identity.subprocess.run', return_value=SimpleNamespace(returncode=1, stdout='', stderr='not found'))
    popen = mocker.patch('pipeline.executor.subprocess.Popen')
    with pytest.raises(RuntimeError, match='Cannot record Docker image identity'):
        LocalDockerExecutor().execute(ExecutionRequest('missing:latest', [], [], image_receipt_path=str(tmp_path / 'container_images/stage.json')))
    popen.assert_not_called()


@pytest.mark.parametrize('changed', [False, True])
def test_job_records_deployed_source_and_rejects_mismatch(tmp_path, monkeypatch, changed):
    from pipeline import source_revision
    runtime = tmp_path / 'runtime'
    package = runtime / 'pipeline'
    package.mkdir(parents=True)
    source = package / 'job_worker.py'
    source.write_text('original source')
    monkeypatch.setattr(source_revision, '__file__', str(package / 'source_revision.py'))
    manifest = source_revision.source_manifest(runtime)
    (runtime / 'source_revision.json').write_text(json.dumps(manifest))
    job = tmp_path / 'job'
    job.mkdir()
    if changed:
        source.write_text('changed source')
        with pytest.raises(RuntimeError, match='differs'):
            source_revision.record_job_source(job)
    else:
        source_revision.record_job_source(job)
        record = json.loads((job / 'source_revision.json').read_text())
        assert record['deployed_source_matches_manifest'] is True
