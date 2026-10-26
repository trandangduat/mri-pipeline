"""Durable, bounded-memory tool output capture for UI jobs."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
import uuid

log = logging.getLogger(__name__)


def subject_key(subject: str) -> str:
    return hashlib.sha256(subject.encode('utf-8')).hexdigest()[:32]


class ToolOutputCapture:
    def __init__(self, config, stage: str, tool: str):
        directory = Path(config.console_job_dir) / 'console' / subject_key(config.subject_id)
        directory.mkdir(parents=True, exist_ok=True)
        self.record_id = uuid.uuid4().hex
        self.path = directory / (self.record_id + '.log')
        self.meta_path = directory / (self.record_id + '.json')
        self.handle = self.path.open('xb')
        self.lock = threading.Lock()
        self.last_save = 0.0
        attempt = config.console_attempt_id
        match = re.search(r':attempt:(\d+)$', attempt or '')
        self.meta = {
            'version': 1, 'record_id': self.record_id, 'job_id': Path(config.console_job_dir).name,
            'subject_id': config.subject_id, 'input_file': config.input_file,
            'stage': stage, 'tool': tool, 'attempt_id': attempt or self.record_id,
            'attempt_number': int(match[1]) if match else (1 if not attempt else None),
            'started_at': time.time(), 'finished_at': None, 'status': 'running',
            'exit_code': None, 'error': '', 'bytes': 0, 'newlines': 0,
            'ends_with_newline': False, 'coverage': 'complete', 'capture_error': '',
            'stream': 'stdout and stderr combined',
        }
        self._save()

    def _save(self):
        try:
            temp = self.meta_path.with_suffix('.tmp')
            temp.write_text(json.dumps(self.meta, ensure_ascii=False), encoding='utf-8')
            os.replace(temp, self.meta_path)
            self.last_save = time.monotonic()
        except OSError as exc:
            self.meta['coverage'] = 'partial'
            self.meta['capture_error'] = str(exc)
            log.warning('Could not save console metadata: %s', exc)

    def write(self, data: bytes):
        with self.lock:
            try:
                if self.handle.closed:
                    return
                self.handle.write(data)
                self.handle.flush()
                self.meta['bytes'] += len(data)
                self.meta['newlines'] += data.count(b'\n')
                self.meta['ends_with_newline'] = data.endswith(b'\n')
                if time.monotonic() - self.last_save >= 1:
                    self._save()
            except OSError as exc:
                self.meta['coverage'] = 'partial'
                self.meta['capture_error'] = str(exc)
                try:
                    self.handle.close()
                except OSError:
                    pass
                self._save()

    def finish(self, success: bool, error: str, exit_code: int | None):
        with self.lock:
            if not self.handle.closed:
                try:
                    self.handle.close()
                except OSError as exc:
                    self.meta['coverage'] = 'partial'
                    self.meta['capture_error'] = str(exc)
            self.meta.update(status='success' if success else ('stopped' if error == 'stopped by request' else 'failed'),
                             finished_at=time.time(), error=error, exit_code=exit_code)
            self._save()


def create_capture(config, stage: str, tool: str):
    if not config.console_job_dir:
        return None
    try:
        return ToolOutputCapture(config, stage, tool)
    except OSError as exc:
        log.warning('Tool output capture unavailable: %s', exc)
        return None


def record_scheduler_result(job_dir, subject, attempt_id, response):
    """Add the scheduler's actual retry decision after it commits a result."""
    state = getattr(response, 'task_state', None)
    if state is None:
        return
    directory = Path(job_dir) / 'console' / subject_key(subject)
    for path in directory.glob('*.json'):
        try:
            meta = json.loads(path.read_text(encoding='utf-8'))
            if meta.get('attempt_id') != str(attempt_id):
                continue
            retry = getattr(response, 'retry_eligible_at', None)
            meta['retry_state'] = str(getattr(state, 'value', state))
            meta['retry_eligible_at'] = retry.timestamp() if retry is not None else None
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
            os.replace(temp, path)
        except (OSError, ValueError, AttributeError, TypeError) as exc:
            log.warning('Could not save scheduler retry details: %s', exc)
