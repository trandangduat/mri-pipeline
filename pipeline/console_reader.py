"""Read-only console access for new captures and legacy job records."""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import stat
import threading
from datetime import datetime, timezone

from .tool_output import subject_key

MAX_TEXT = 65536
EXPORT_TRAILER = b'\nCONSOLE_EXPORT_MANIFEST '
_cache = OrderedDict()
_lock = threading.RLock()

# Executed locally, or through SSH stdin for old remote jobs. No private imports.
SCHEDULER_READER = r'''
import json, os, pathlib, sqlite3
result = []
db = pathlib.Path(request['job_dir']) / 'neuroflow_workspace.sqlite'
if db.is_file() and not db.is_symlink() and not (os.path.exists(str(db)+'-wal') and os.path.getsize(str(db)+'-wal')):
    connection = sqlite3.connect(db.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        query = ''' + '"""' + '''SELECT a.*, t.image_id, t.metadata_json AS task_metadata,
                   r.exit_code, r.error_message, r.status AS result_status
                   FROM attempts a JOIN tasks t ON a.task_id=t.task_id
                   LEFT JOIN results r ON a.result_id=r.result_id
                   WHERE t.image_id=? ORDER BY a.created_at LIMIT 500''' + '"""' + r'''
        for row in connection.execute(query, (request['subject_id'],)):
            item = dict(row)
            metadata = json.loads(item.pop('task_metadata') or '{}')
            item['stage'] = metadata.get('pipeline_stage', '')
            item['tool'] = metadata.get('pipeline_tool_key', '')
            result.append(item)
    finally:
        connection.close()
'''


def scheduler_records(job_dir: str, subject: str) -> list:
    namespace = {'request': {'job_dir': job_dir, 'subject_id': subject}}
    exec(SCHEDULER_READER, namespace)
    return namespace['result']


class ConsoleFiles:
    """Restrict source reads to the job and its saved output directory."""
    def __init__(self, job_dir: str, sftp=None, namespace='local'):
        self.sftp = sftp
        self.join = posixpath.join if sftp else os.path.join
        self.namespace = namespace
        self.history_trimmed = False
        self.job = self.real(job_dir)
        self.roots = [self.job]
        self.config = self.document(self.join(self.job, 'job_config.json'))
        output = str(self.config.get('effective_output_dir') or self.config.get('output_dir') or '')
        self.output = ''
        if output:
            try:
                root = self.real(output)
                if root not in ('/', '\\', '') and len(root.rstrip('/\\').split('/' if sftp else os.sep)) > 2:
                    self.output = root
                    self.roots.append(root)
            except OSError:
                pass

    def real(self, path):
        return self.sftp.normalize(path) if self.sftp else str(Path(path).resolve())

    def safe(self, path):
        path = self.real(path)
        sep = '/' if self.sftp else os.sep
        if not any(path == r or path.startswith(r.rstrip(sep) + sep) for r in self.roots):
            raise ValueError('Console source is outside the job output roots')
        return path

    def info(self, path):
        path = self.safe(path)
        return self.sftp.stat(path) if self.sftp else os.stat(path)

    def open(self, path):
        path = self.safe(path)
        return self.sftp.open(path, 'rb') if self.sftp else open(path, 'rb')

    def names(self, path):
        try:
            path = self.safe(path)
            return self.sftp.listdir(path) if self.sftp else os.listdir(path)
        except OSError:
            return []

    def document(self, path):
        try:
            with self.open(path) as handle:
                raw = handle.read(131073)
            if len(raw) > 131072:
                return {}
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def events(self):
        path = self.join(self.job, 'events.jsonl')
        try:
            info = self.info(path)
        except OSError:
            return [], False
        key = (self.namespace, self.job, 'events')
        # Incremental reads prevent repeatedly transferring a large shared log.
        with _lock:
            value = _cache.get(key)
            if value is None or info.st_size < value['offset']:
                value = {'offset': 0, 'pending': b'', 'events': [], 'sizes': [], 'bytes': 0, 'trimmed': False}
            if info.st_size > value['offset']:
                with self.open(path) as handle:
                    handle.seek(value['offset'])
                    raw = handle.read(min(4 * 1024 * 1024, info.st_size - value['offset']))
                value['offset'] += len(raw)
                lines = (value['pending'] + raw).split(b'\n')
                value['pending'] = lines.pop()[-262144:]
                for line in lines:
                    try:
                        event = json.loads(line)
                        if isinstance(event, dict) and event.get('kind') != 'metrics':
                            value['events'].append(event)
                            value['sizes'].append(len(line))
                            value['bytes'] += len(line)
                    except (ValueError, UnicodeDecodeError):
                        pass
                cut = max(0, len(value['events']) - 20000)
                removed = sum(value['sizes'][:cut])
                while value['bytes'] - removed > 4 * 1024 * 1024 and cut < len(value['sizes']):
                    removed += value['sizes'][cut]
                    cut += 1
                if cut:
                    del value['events'][:cut]
                    del value['sizes'][:cut]
                    value['bytes'] -= removed
                    value['trimmed'] = True
            _cache[key] = value
            _cache.move_to_end(key)
            while len(_cache) > 16:
                _cache.popitem(last=False)
            self.history_trimmed = value['trimmed']
            return list(value['events']), value['offset'] < info.st_size


def _epoch(value):
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError):
        return None


def _clock(value):
    stamp = _epoch(value)
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec='seconds') if stamp else 'Time unavailable'


def subject_events(events: list, subject: str, input_file: str, single: bool):
    active = set()
    result = []
    for event in events:
        kind = event.get('kind')
        file = str(event.get('input_file') or '')
        identity = str(event.get('subject_id') or '')
        message = str(event.get('msg') or event.get('message') or '')
        prefix = re.match(r'^\[([^\]]+)\]', message)
        if kind == 'image_start' and file:
            active.add(file)
        match = (identity == subject and (not file or file == input_file)) if identity else (
            file == input_file if file else (prefix[1] == subject if prefix else
                (single or (len(active) == 1 and input_file in active))))
        if match and kind in ('progress', 'step', 'stage', 'image_start', 'image_done'):
            result.append(event)
        if kind == 'image_done' and file:
            active.discard(file)
    return result


def subject_activity(events: list, subject: str, input_file: str, single: bool):
    result = []
    for event in subject_events(events, subject, input_file, single):
        kind = event.get('kind')
        message = re.sub(r'^\[[^\]]+\]\s*', '', str(event.get('msg') or event.get('message') or ''))
        status = str(event.get('status') or ('running' if kind == 'image_start' else ''))
        if kind == 'image_done':
            message = 'Subject processing finished'
            status = str(event.get('status') or ('success' if event.get('success') else 'failed'))
        if kind == 'image_start':
            message = 'Subject processing started'
        result.append(f"[{_clock(event.get('time'))}] {status.upper()} {event.get('stage', '')}: {message}")
    return result


def records(files: ConsoleFiles, subject: str, input_file: str):
    directory = files.join(files.job, 'console', subject_key(subject))
    found = []
    for name in [n for n in files.names(directory) if re.fullmatch(r'[a-f0-9]{32}\.json', n)][:500]:
        if not re.fullmatch(r'[a-f0-9]{32}\.json', name):
            continue
        item = files.document(files.join(directory, name))
        if item.get('subject_id') != subject or item.get('input_file') != input_file:
            continue
        if item.get('job_id') != files.job.rstrip('/\\').replace('\\', '/').split('/')[-1]:
            continue
        identifier = name[:-5]
        if item.get('record_id') != identifier:
            continue
        item['_path'] = files.join(directory, identifier + '.log')
        found.append(item)
    if found:
        return sorted(found, key=lambda r: r.get('started_at') or 0)
    if files.config.get('console_log_version') == 1:
        return []
    # Legacy tool logs belong to a subject, but may combine several attempts.
    if files.output and subject not in ('.', '..') and not re.search(r'[/\\]', subject):
        directory = files.join(files.output, subject, 'logs')
        tools = dict(files.config.get('selected_tools') or {})
        for name in files.names(directory)[:500]:
            if not re.fullmatch(r'[A-Za-z0-9_.-]+\.log', name) or name == 'pipeline_metrics.log':
                continue
            tool = name[:-4].removesuffix('_pipeline')
            stage = next((s for s, t in tools.items() if t == tool), '')
            if not stage:
                continue
            found.append({'record_id': 'legacy-' + hashlib.sha256(name.encode()).hexdigest()[:24],
                          'subject_id': subject, 'input_file': input_file, 'stage': stage, 'tool': tool,
                          'attempt_id': '', 'attempt_number': None, 'started_at': None,
                          'status': 'saved', 'exit_code': None, 'coverage': 'partial_or_unknown',
                          'error': '', '_path': files.join(directory, name)})
    order = ('reorientation', 'brain_extraction', 'segmentation', 'template_registration', 'bias_correction',
             'white_matter_segmentation', 'surface_reconstruction', 'surface_registration', 'stats_extraction')
    return sorted(found, key=lambda item: (order.index(item['stage']) if item['stage'] in order else len(order), item['tool']))


def cached_native(files, subject, reader):
    path = files.join(files.job, 'neuroflow_workspace.sqlite')
    try:
        info = files.info(path)
        key = (files.namespace, files.job, subject, info.st_size, info.st_mtime)
    except OSError:
        return []
    with _lock:
        value = _cache.get(key)
    if value is not None:
        return value
    value = reader(subject)
    with _lock:
        _cache[key] = value
        while len(_cache) > 16:
            _cache.popitem(last=False)
    return value


def tail(files, record, max_bytes=MAX_TEXT, max_lines=200):
    try:
        size = files.info(record['_path']).st_size
        complete = record.get('version') == 1 and record.get('status') != 'interrupted'
        size = min(size, int(record.get('bytes', size))) if complete else size
        start = max(0, size - max_bytes)
        with files.open(record['_path']) as handle:
            handle.seek(start)
            raw = handle.read(size - start)
        if start and b'\n' in raw:
            raw = raw.split(b'\n', 1)[1]
        text = raw.decode('utf-8', errors='replace')
        lines = text.split('\n')
        if lines and lines[-1] == '':
            lines.pop()
        visible = lines[-max_lines:]
        total = None
        if complete:
            total = int(record.get('newlines', 0)) + int(size > 0 and not record.get('ends_with_newline'))
        elif not start:
            total = len(lines)
        return '\n'.join(visible), max(0, total - len(visible)) if total is not None else None, bool(start)
    except OSError:
        return '', None, False


def combined_text(files, items, activity, warnings):
    """Show every stage in one bounded text stream, including its output tail."""
    from .registry import STAGE_LABELS, tool_display_name
    notes = '\n'.join('[Note] ' + warning for warning in warnings)
    if not items:
        return (notes + '\n\n' + '\n'.join(activity[-200:])).strip().encode('utf-8')[-MAX_TEXT:].decode('utf-8', errors='replace')
    headers = []
    for item in items:
        stage = STAGE_LABELS.get(item['stage'], item['stage'])
        tool = tool_display_name(item['tool']) or item['tool']
        attempt = f"Attempt {item['attempt_number']}" if item.get('attempt_number') else 'Saved output'
        lines = [f'=== {stage} · {tool} · {attempt} ===',
                 f"Started: {_clock(item.get('started_at'))} | Status: {item['status'].upper()}"]
        if item.get('exit_code') is not None:
            lines[-1] += f" | Exit code: {item['exit_code']}"
        if item.get('finished_at'):
            lines.append('Finished: ' + _clock(item['finished_at']))
        if item.get('error'):
            lines.append('Error: ' + str(item['error'])[:2000])
        if item.get('retry_eligible_at'):
            lines.append('Retry scheduled: ' + _clock(item['retry_eligible_at']))
        elif item.get('retry_state') and item['status'] == 'failed':
            lines.append('Task state: ' + str(item['retry_state']))
        headers.append('\n'.join(lines))
    stages = {item['stage'] for item in items}
    extra = []
    for line in activity:
        match = re.search(r'\] \S+ ([a-z_]+)(?: ·|:)', line)
        if match and match[1] not in stages:
            extra.append(line)
    prefix = '\n\n'.join(part for part in (notes, '\n'.join(extra)) if part)
    header_bytes = sum(len(header.encode('utf-8')) + 150 for header in headers) + len(prefix.encode('utf-8'))
    budget = max(1, (MAX_TEXT - header_bytes) // len(items))
    blocks = [prefix] if prefix else []
    for item, header in zip(items, headers):
        output, hidden, limited = tail(files, item, max_bytes=budget)
        if hidden:
            header += f'\n{hidden} earlier lines hidden.'
        if limited:
            header += '\n[Output shortened to fit this view.]'
        if not output:
            output = 'Waiting for tool output...' if item['status'] == 'running' else 'No saved stdout/stderr is available.'
        blocks.append(header + '\n\n' + output)
    return '\n\n'.join(blocks).encode('utf-8')[-MAX_TEXT:].decode('utf-8', errors='replace')


def read_console(files: ConsoleFiles, payload: dict, native_reader=None):
    mode = payload.get('mode', 'summary')
    if mode not in ('summary', 'detailed', 'combined'):
        raise ValueError('Unsupported console mode. Reload the current NeuroFlow backend.')
    subject, input_file = str(payload.get('subject_id') or ''), str(payload.get('input_file') or '')
    if not subject or not input_file:
        raise ValueError('A subject and its input file are required')
    config = files.config
    known = dict(config.get('subject_id_map') or {})
    configured_files = list(config.get('input_files') or [])
    if config.get('input_file'):
        configured_files.append(config['input_file'])
    events, loading = files.events()
    verified = input_file in configured_files or input_file in known or any(
        e.get('input_file') == input_file and (not e.get('subject_id') or e['subject_id'] == subject) for e in events)
    event_subjects = {str(e['subject_id']) for e in events if e.get('input_file') == input_file and e.get('subject_id')}
    if not verified or (input_file in known and str(known[input_file]) != subject):
        raise ValueError('Subject does not match the selected job input')
    if event_subjects and subject not in event_subjects:
        raise ValueError('Subject does not match the recorded job events')
    items = records(files, subject, input_file)
    warnings = ['Some earlier activity is outside the console history limit. Saved tool output remains available.'] if files.history_trimmed else []
    lines = subject_activity(events, subject, input_file, len(set(configured_files)) == 1)
    if items and items[0].get('version') == 1:
        job_status = files.document(files.join(files.job, 'job_status.json'))
        state = str(job_status.get('state') or '').lower()
        lines = []
        for item in items:
            if item['status'] == 'running' and state in ('completed', 'failed', 'stopped'):
                item['status'] = 'interrupted'
                item['error'] = 'No final capture state was saved.'
                item['coverage'] = 'partial'
            label = f"{item['stage']} · {item['tool']} · Attempt {item.get('attempt_number') or item['attempt_id']}"
            lines.append(f"[{_clock(item.get('started_at'))}] RUNNING {label}")
            if item.get('finished_at'):
                lines.append(f"[{_clock(item['finished_at'])}] {item['status'].upper()} {label}"
                             + (f" · Exit code: {item['exit_code']}" if item.get('exit_code') is not None else '')
                             + (f" · {item['error']}" if item.get('error') else ''))
                if item.get('retry_eligible_at'):
                    lines.append(f"[{_clock(item['finished_at'])}] Retry scheduled: {_clock(item['retry_eligible_at'])}")
            if item.get('capture_error'):
                warnings.append('Some tool output was not saved: ' + item['capture_error'])
        captured_stages = {item['stage'] for item in items}
        lines.extend(subject_activity([e for e in events if e.get('stage') and e.get('stage') not in captured_stages],
                                      subject, input_file, len(set(configured_files)) == 1))
    elif native_reader:
        try:
            native = cached_native(files, subject, native_reader)
            if native:
                lines = []
                for item in native:
                    label = f"{item.get('stage') or 'Stage'} · {item.get('tool') or 'Tool'} · Attempt {item.get('attempt_number', '?')}"
                    lines.append(f"[{_clock(item.get('started_at'))}] STARTED {label}")
                    if item.get('finished_at'):
                        lines.append(f"[{_clock(item['finished_at'])}] {item.get('state', 'UNKNOWN')} {label}"
                                     + (f" · Exit code: {item['exit_code']}" if item.get('exit_code') is not None else '')
                                     + (f" · {item['error_message']}" if item.get('error_message') else ''))
                for record in items:
                    matching = [r for r in native if r.get('stage') == record['stage'] and r.get('tool') == record['tool']]
                    if matching:
                        record['started_at'] = min((_epoch(r.get('started_at')) for r in matching if _epoch(r.get('started_at')) is not None), default=None)
                        last = matching[-1]
                        record['status'] = str(last.get('result_status') or last.get('state') or 'unknown').lower()
                        record['exit_code'] = last.get('exit_code')
                        record['metadata_scope'] = 'stage'
        except Exception:
            warnings.append('Older scheduler attempt details are unavailable. Available activity is shown.')
    scoped = subject_events(events, subject, input_file, len(set(configured_files)) == 1)
    for item in items:
        if item.get('version') == 1 or item.get('metadata_scope'):
            continue
        related = [e for e in scoped if e.get('stage') == item['stage']]
        starts = [_epoch(e.get('time')) for e in related if str(e.get('status')).lower() in ('running', 'start', 'started')]
        item['started_at'] = min((s for s in starts if s is not None), default=None)
        states = [str(e.get('status')).lower() for e in related if str(e.get('status')).lower()
                  in ('running', 'success', 'completed', 'failed', 'error', 'stopped', 'skipped')]
        if states:
            item['status'] = states[-1]
            item['metadata_scope'] = 'stage'
    if any(i.get('coverage') != 'complete' for i in items):
        warnings.append('Only saved output is available. Older logs may combine attempts or omit earlier output.')
    selected = next((i for i in items if i['record_id'] == payload.get('record_id')), None)
    selected = selected or (items[-1] if items else None)
    hidden, byte_limited = None, False
    if mode == 'combined':
        text = combined_text(files, items, lines, warnings)
    elif mode == 'detailed' and selected:
        text, hidden, byte_limited = tail(files, selected)
    elif mode == 'summary':
        text = '\n'.join(lines[-200:]).encode('utf-8')[-MAX_TEXT:].decode('utf-8', errors='replace')
    else:
        text = ''
    fields = {'record_id', 'stage', 'tool', 'attempt_id', 'attempt_number', 'started_at', 'finished_at',
              'status', 'exit_code', 'error', 'coverage', 'metadata_scope', 'retry_state', 'retry_eligible_at'}
    public = [{k: v for k, v in item.items() if k in fields} for item in items]
    return {'ok': True, 'supported_modes': ['summary', 'detailed', 'combined'],
            'records': public, 'selected_record_id': selected['record_id'] if selected else '',
            'text': text, 'hidden_lines': hidden, 'byte_limited': byte_limited,
            'warnings': warnings, 'loading_older': loading, 'download_available': bool(items or lines),
            '_records': items, '_summary': '\n'.join(lines)}


def public_response(value):
    return {k: v for k, v in value.items() if not k.startswith('_')}


def export_console(files: ConsoleFiles, payload: dict, native_reader=None):
    value = read_console(files, dict(payload, mode='summary'), native_reader)
    if value['loading_older']:
        raise ValueError('Older activity is still loading. Retry the download shortly.')
    if not value['download_available']:
        raise ValueError('No subject log is available')
    target = Path(str(payload.get('target_file') or '')).expanduser()
    if not target.is_absolute() or target.suffix.lower() not in ('.log', '.txt') or not target.parent.is_dir():
        raise ValueError('Select a local .log or .txt file in an existing directory')
    # Exclusive creation protects existing job outputs and user files.
    created = False
    manifest = {'version': 1, 'job_id': files.job.rstrip('/\\').replace('\\', '/').split('/')[-1],
                'subject_id': payload['subject_id'], 'input_file': payload['input_file'], 'records': []}
    try:
        with target.open('xb') as output:
            created = True
            header = (f"Subject: {payload['subject_id']}\nInput: {payload['input_file']}\n"
                      f"Exported: {datetime.now(timezone.utc).isoformat()}\n"
                      + '\n'.join(value['warnings']) + '\n\nACTIVITY\n' + value['_summary'] + '\n')
            output.write(header.encode('utf-8'))
            for item in value['_records']:
                output.write((f"\n\n=== {item['stage']} | {item['tool']} | Attempt: "
                              f"{item.get('attempt_number') or item.get('attempt_id') or 'not recorded'} ===\n"
                              f"Coverage: {item['coverage']}\n").encode('utf-8'))
                try:
                    remaining = files.info(item['_path']).st_size
                    offset = output.tell()
                    digest = hashlib.sha256()
                    copied = 0
                    with files.open(item['_path']) as source:
                        while remaining:
                            block = source.read(min(65536, remaining))
                            if not block:
                                break
                            output.write(block)
                            digest.update(block)
                            copied += len(block)
                            remaining -= len(block)
                    manifest['records'].append({'record_id': item['record_id'], 'stage': item['stage'],
                                                'attempt_id': item.get('attempt_id'), 'offset': offset,
                                                'bytes': copied, 'sha256': digest.hexdigest(),
                                                'coverage': item['coverage'], 'read_complete': remaining == 0})
                except OSError:
                    output.write(b'\nSaved output file is unavailable.\n')
            output.write(EXPORT_TRAILER + json.dumps(manifest, ensure_ascii=False).encode('utf-8') + b'\n')
        return {'ok': True, 'path': str(target), 'bytes': target.stat().st_size}
    except Exception:
        if created:
            target.unlink(missing_ok=True)
        raise
