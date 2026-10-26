"""Measure a manual Operator Console review. Never start or modify MRI jobs."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shlex
import statistics
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit


# This program runs through SSH stdin. It creates no server files.
# Keep remote dependencies limited to the Python standard library.
REMOTE_PROBE = r'''
import json, os, pathlib, shutil, sys, time
started = time.monotonic()
request = json.load(sys.stdin)
job = pathlib.Path(request['job_dir'])
read_bytes = 0
errors = []

def text(path, limit=1048576):
    global read_bytes
    with open(str(path), 'rb') as handle:
        data = handle.read(limit + 1)
    read_bytes += len(data)
    if len(data) > limit:
        raise ValueError('Read limit exceeded: ' + str(path))
    return data.decode('utf-8', errors='replace')

def document(path):
    try:
        value = json.loads(text(path))
        return value if isinstance(value, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        errors.append(str(exc))
        return {}

status = document(job / 'job_status.json')
config = document(job / 'job_config.json')
recent_metrics = {}
try:
    with open(str(job / 'metrics.jsonl'), 'rb') as handle:
        handle.seek(0, 2)
        offset = max(0, handle.tell() - 65536)
        handle.seek(offset)
        data = handle.read(65536)
    read_bytes += len(data)
    lines = data.splitlines()
    for line in (lines[1:] if offset else lines):
        try:
            event = json.loads(line)
            key = event.get('container_name')
            if key:
                recent_metrics[key] = {k: event.get(k) for k in
                    ('time', 'stage', 'tool', 'cpu_pct', 'ram_bytes', 'elapsed',
                     'container_name', 'subject_id', 'input_file', 'attempt_id', 'task_id')}
        except (ValueError, AttributeError):
            pass
except FileNotFoundError:
    pass
except Exception as exc:
    errors.append('metrics tail: ' + str(exc))
stat_lines = text('/proc/stat').splitlines()
cpu = [int(v) for v in stat_lines[0].split()[1:9]]
memory = {}
for line in text('/proc/meminfo').splitlines():
    key, value = line.split(':', 1)
    if key in ('MemTotal', 'MemAvailable'):
        memory[key] = int(value.split()[0]) * 1024
network = {}
for line in text('/proc/net/dev').splitlines()[2:]:
    key, values = line.split(':', 1)
    fields = values.split()
    network[key.strip()] = {'received_bytes': int(fields[0]), 'sent_bytes': int(fields[8])}

worker = None
pid = status.get('pid') or status.get('process_pid')
state = str(status.get('state') or status.get('status') or '').lower()
if pid and state not in ('completed', 'failed', 'stopped', 'success', 'interrupted'):
    try:
        command = text('/proc/%s/cmdline' % int(pid)).replace('\x00', ' ')
        if str(job) not in command:
            raise ValueError('Worker PID does not identify this job; it may have been reused')
        fields = text('/proc/%s/stat' % int(pid)).rsplit(')', 1)[1].split()
        io = {}
        try:
            io = dict((k, int(v.strip())) for k, v in
                      (line.split(':', 1) for line in text('/proc/%s/io' % int(pid)).splitlines()))
        except (PermissionError, FileNotFoundError):
            pass
        worker = {'pid': int(pid), 'start_ticks': int(fields[19]),
                  'cpu_seconds': (int(fields[11]) + int(fields[12])) / os.sysconf('SC_CLK_TCK'),
                  'rss_bytes': int(fields[21]) * os.sysconf('SC_PAGE_SIZE'), 'io': io}
    except FileNotFoundError:
        pass
    except Exception as exc:
        errors.append('worker: ' + str(exc))

roots = [job / 'logs', job / 'tool_logs', job / 'console']
roots += [pathlib.Path(p) for p in request.get('log_roots', [])]
output = config.get('effective_output_dir') or config.get('output_dir')
if output and pathlib.Path(output).is_absolute():
    output = pathlib.Path(output)
    roots.append(output / 'logs')
    subjects = set(str(v) for v in (config.get('subject_id_map') or {}).values())
    if config.get('subject_id'):
        subjects.add(str(config['subject_id']))
    if subjects:
        roots += [output / s / 'logs' for s in subjects
                  if s not in ('.', '..') and '/' not in s and '\\' not in s]
    elif output.is_dir() and not output.is_symlink():
        with os.scandir(str(output)) as entries:
            for index, entry in enumerate(entries):
                if index >= 500:
                    errors.append('Output subject discovery reached 500 entries')
                    break
                if entry.is_dir(follow_symlinks=False):
                    roots.append(pathlib.Path(entry.path) / 'logs')
inventory = []
seen = set()
capped = False
for name in ('events.jsonl', 'metrics.jsonl', 'run.log', 'launcher.log'):
    roots.append(job / name)
for root in roots:
    if capped:
        break
    try:
        if root.is_symlink() or not root.exists():
            continue
        candidates = []
        if root.is_file():
            candidates = [root]
        else:
            for folder, dirs, files in os.walk(str(root), followlinks=False):
                dirs[:] = [d for d in dirs if not pathlib.Path(folder, d).is_symlink()]
                if len(pathlib.Path(folder).relative_to(root).parts) >= 8:
                    dirs[:] = []
                candidates.extend(pathlib.Path(folder, n) for n in files
                                  if n.endswith(('.log', '.jsonl', '.json')))
                if len(candidates) >= request['max_files']:
                    candidates = candidates[:request['max_files']]
                    capped = True
                    break
        for path in candidates:
            if str(path) in seen or path.is_symlink():
                continue
            seen.add(str(path))
            info = path.stat()
            inventory.append({'path': str(path), 'bytes': info.st_size, 'mtime_ns': info.st_mtime_ns})
            if len(inventory) >= request['max_files']:
                capped = True
                break
    except Exception as exc:
        errors.append('inventory: ' + str(exc))
if capped:
    errors.append('Log inventory limit reached; totals are partial')
disk = None
if job.is_dir():
    usage = shutil.disk_usage(str(job))
    disk = {'total_bytes': usage.total, 'free_bytes': usage.free}
print(json.dumps({'server_epoch': time.time(), 'job_exists': job.is_dir(),
    'status': {k: status.get(k) for k in
               ('state', 'status', 'pid', 'process_pid', 'started_at', 'finished_at', 'exit_code', 'duration_sec')},
    'cpu_ticks': cpu, 'memory': memory, 'network': network, 'worker': worker,
    'recent_task_metrics': sorted(recent_metrics.values(), key=lambda r: r.get('time') or 0)[-20:],
    'disk': disk, 'log_files': inventory if request.get('include_inventory') else None,
    'log_file_count': len(inventory), 'log_bytes': sum(p['bytes'] for p in inventory),
    'inventory_partial': capped, 'errors': errors,
    'probe': {'cpu_seconds': time.process_time(), 'elapsed_seconds': time.monotonic() - started,
              'file_bytes_read': read_bytes}}))
'''


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def append(path: Path, value: dict) -> None:
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + '\n')


def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    result = []
    with path.open(encoding='utf-8-sig') as handle:
        for line in handle:
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    result.append(value)
            except json.JSONDecodeError:
                pass  # A running writer can leave its final line incomplete.
    return result


def last_mark(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open('rb') as handle:
        handle.seek(max(0, path.stat().st_size - 65536))
        tail = handle.read().decode('utf-8', errors='replace').splitlines()
    for line in reversed(tail):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return {}


def dependencies(remote: bool = False):
    try:
        import psutil
        if remote:
            import paramiko
        return psutil
    except ImportError as exc:
        raise SystemExit('Use .venv/Scripts/python.exe. Required packages: psutil and paramiko.') from exc


def connect(config: dict):
    import paramiko
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    known_hosts = Path(config['known_hosts']).expanduser()
    if known_hosts.exists():
        client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(config['host'], port=config['port'], username=config['user'],
                       key_filename=str(Path(config['key']).expanduser()), timeout=10,
                       banner_timeout=10, auth_timeout=10, allow_agent=False, look_for_keys=False)
    except Exception:
        client.close()
        raise
    client.get_transport().set_keepalive(30)
    return client


def remote_sample(client, config: dict) -> dict:
    started = time.monotonic()
    command = shlex.quote(config['remote_python']) + ' -B -c ' + shlex.quote(REMOTE_PROBE)
    stdin, stdout, stderr = client.exec_command(command, timeout=15)
    stdin.write(json.dumps({'job_dir': config['job_dir'], 'log_roots': config['remote_log_root'],
                            'max_files': config['max_log_files'], 'include_inventory': config.get('include_inventory', False)}))
    stdin.flush()
    stdin.channel.shutdown_write()
    payload = stdout.read(4 * 1024 * 1024 + 1)
    error = stderr.read(16384)
    code = stdout.channel.recv_exit_status()
    if len(payload) > 4 * 1024 * 1024:
        raise RuntimeError('Remote response exceeded the monitor limit')
    if code:
        raise RuntimeError('Remote probe failed: ' + error.decode('utf-8', errors='replace')[:2000])
    result = json.loads(payload)
    result['request_seconds'] = time.monotonic() - started
    result['response_payload_bytes'] = len(payload)
    return result


class LocalSampler:
    def __init__(self, pids: list[int], backend_pids: list[int]):
        self.psutil = dependencies()
        self.pids = pids
        self.backend_pids = backend_pids
        self.previous: dict[tuple, tuple] = {}
        self.last_network = None
        self.psutil.cpu_percent(None)

    def sample(self) -> dict:
        p = self.psutil
        stamp = time.monotonic()
        selected: dict[int, str] = {}
        discovery_errors = []
        for process in p.process_iter(['pid', 'name']):
            try:
                name = (process.info['name'] or '').lower()
                role = None
                if process.pid in self.backend_pids:
                    role = 'backend'
                elif process.pid in self.pids or name in ('neuroflow.exe', 'neuroflow', 'mri-pipeline-tauri.exe', 'mri-pipeline-tauri'):
                    role = 'ui'
                elif name.startswith('neuroflow-backend'):
                    role = 'backend'
                elif name.startswith(('python', 'pypy')):
                    if any('app_backend.server' in arg for arg in process.cmdline()):
                        role = 'backend'
                if role:
                    selected[process.pid] = role
                    for child in process.children(recursive=True):
                        selected.setdefault(child.pid, role)
            except p.Error as exc:
                if process.pid in self.pids:
                    discovery_errors.append(type(exc).__name__ + ': PID ' + str(process.pid))
        # Keep backend children out of UI totals when both roots were discovered.
        for process in p.process_iter(['pid', 'name']):
            if (process.info['name'] or '').lower().startswith('neuroflow-backend'):
                selected[process.pid] = 'backend'
                try:
                    for child in process.children(recursive=True):
                        selected[child.pid] = 'backend'
                except p.Error:
                    pass
        selected[os.getpid()] = 'monitor'
        records = []
        active_keys = set()
        for pid, role in selected.items():
            try:
                process = p.Process(pid)
                with process.oneshot():
                    key = (pid, process.create_time())
                    active_keys.add(key)
                    cpu = process.cpu_times()
                    cpu_seconds = cpu.user + cpu.system
                    previous = self.previous.get(key)
                    percent = (max(0, cpu_seconds - previous[1]) / (stamp - previous[0]) * 100
                               if previous and stamp > previous[0] else None)
                    self.previous[key] = (stamp, cpu_seconds)
                    try:
                        io = process.io_counters()._asdict()
                    except (p.Error, AttributeError):
                        io = None
                    records.append({'pid': pid, 'role': role, 'name': process.name(),
                                    'cpu_pct_one_core': percent, 'rss_bytes': process.memory_info().rss,
                                    'threads': process.num_threads(), 'io': io})
            except p.Error as exc:
                discovery_errors.append(type(exc).__name__ + ': PID ' + str(pid))
        self.previous = {k: v for k, v in self.previous.items() if k in active_keys}
        counters = p.net_io_counters(pernic=True)
        network = {}
        for interface, value in counters.items():
            data = {'received_bytes': value.bytes_recv, 'sent_bytes': value.bytes_sent}
            old = self.last_network[1].get(interface) if self.last_network else None
            elapsed = stamp - self.last_network[0] if self.last_network else 0
            if old and elapsed > 0:
                for direction, field in (('received', 'bytes_recv'), ('sent', 'bytes_sent')):
                    delta = getattr(value, field) - getattr(old, field)
                    data[direction + '_bytes_per_second'] = delta / elapsed if delta >= 0 else None
            network[interface] = data
        self.last_network = (stamp, counters)
        return {'host_cpu_pct_all_cores': p.cpu_percent(None),
                'host_memory': {'total_bytes': p.virtual_memory().total, 'available_bytes': p.virtual_memory().available},
                'processes': records, 'network': network, 'errors': discovery_errors}


def mark(args) -> None:
    session = Path(args.session)
    if not (session / 'session.json').exists():
        raise SystemExit('Session not found. Start capture first.')
    record = {'time': now(), 'epoch': time.time(), 'phase': args.phase,
              'subject': args.subject, 'stage': args.stage, 'attempt': args.attempt,
              'check': args.check, 'result': args.result, 'note': args.note,
              'evidence': args.evidence}
    append(session / 'marks.jsonl', record)
    print('Checkpoint saved: ' + args.phase)


def capture(args) -> None:
    if args.interval < 1 or args.remote_interval < 10:
        raise SystemExit('Local interval must be at least 1 second. Remote interval must be at least 10 seconds.')
    if args.duration < 0 or args.finish_grace < 0 or not 1 <= args.max_log_files <= 5000:
        raise SystemExit('Invalid duration, finish grace, or log file limit.')
    if not args.local_only:
        if not args.job_dir or not PurePosixPath(args.job_dir).is_absolute() or args.job_dir == '/':
            raise SystemExit('Provide the exact absolute server job directory with --job-dir.')
        for root in args.remote_log_root:
            if not PurePosixPath(root).is_absolute() or root == '/':
                raise SystemExit('Log roots must be specific absolute server directories.')
    dependencies(not args.local_only)
    session = Path(args.session).resolve()
    session.mkdir(parents=True, exist_ok=True)
    if (session / 'session.json').exists():
        raise SystemExit('This session already exists. Use a new session directory.')
    config = vars(args).copy()
    config.pop('handler', None)
    config.update({'version': 1, 'started_at': now(), 'monitor_pid': os.getpid(),
                   'cpu_basis': '100 percent is one logical core for process samples',
                   'network_scope': 'Interface totals include unrelated traffic and this monitor',
                   'source': str(Path(__file__).resolve()),
                   'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    write_json(session / 'session.json', config)
    append(session / 'marks.jsonl', {'time': now(), 'epoch': time.time(), 'phase': 'unmarked'})
    sampler = LocalSampler(args.app_pid, args.backend_pid)
    client = None
    started = time.monotonic()
    next_local = started
    next_remote = started
    terminal_since = None
    previous_remote = None
    last_inventory = float('-inf')
    print('Recording to ' + str(session))
    print('Run the MRI job through the UI. Use mark commands in another terminal.')
    print('Press Ctrl+C to stop and create the report.')
    try:
        while True:
            tick = time.monotonic()
            if args.duration and tick - started >= args.duration:
                break
            if tick >= next_local:
                point = sampler.sample()
                point.update({'time': now(), 'epoch': time.time(),
                              'phase': last_mark(session / 'marks.jsonl').get('phase', 'unmarked')})
                append(session / 'local_samples.jsonl', point)
                next_local = tick + args.interval
            if not args.local_only and tick >= next_remote:
                try:
                    if client is None:
                        client = connect(config)
                    details_due = time.monotonic() - last_inventory >= 300
                    sample = remote_sample(client, dict(config, include_inventory=details_due))
                    if details_due:
                        last_inventory = time.monotonic()
                    sample.update({'time': now(), 'epoch': time.time(),
                                   'phase': last_mark(session / 'marks.jsonl').get('phase', 'unmarked')})
                    try:
                        sockets = sampler.psutil.net_connections(kind='tcp')
                        sample['ssh_connections'] = [
                            {'pid': s.pid, 'state': s.status, 'monitor_connection': s.pid == os.getpid()}
                            for s in sockets if s.raddr and s.raddr.ip == args.host and s.raddr.port == args.port]
                    except sampler.psutil.Error as exc:
                        sample['ssh_connections'] = None
                        sample['errors'].append('Connection counts: ' + type(exc).__name__)
                    if previous_remote:
                        elapsed = sample['epoch'] - previous_remote['epoch']
                        old = previous_remote['cpu_ticks']
                        new = sample['cpu_ticks']
                        delta = sum(new) - sum(old)
                        idle = new[3] + new[4] - old[3] - old[4]
                        sample['host_cpu_pct_all_cores'] = (delta - idle) / delta * 100 if delta > 0 else None
                        worker, old_worker = sample.get('worker'), previous_remote.get('worker')
                        if worker and old_worker and elapsed > 0:
                            if (worker['pid'], worker['start_ticks']) == (old_worker['pid'], old_worker['start_ticks']):
                                worker['cpu_pct_one_core'] = max(0, worker['cpu_seconds'] - old_worker['cpu_seconds']) / elapsed * 100
                    previous_remote = sample
                    append(session / 'remote_samples.jsonl', sample)
                    state = str(sample['status'].get('state') or sample['status'].get('status') or '').lower()
                    print(now() + '  job=' + (state or 'waiting') + '  saved-log-bytes=' + str(sample['log_bytes']))
                    if state in ('completed', 'failed', 'stopped', 'success', 'interrupted'):
                        terminal_since = terminal_since or time.monotonic()
                    else:
                        terminal_since = None
                    if terminal_since is not None and time.monotonic() - terminal_since >= args.finish_grace:
                        break
                except Exception as exc:
                    append(session / 'remote_errors.jsonl', {'time': now(), 'error': str(exc)[:2000]})
                    print('Remote sample unavailable: ' + type(exc).__name__)
                    if client is not None:
                        client.close()
                    client = None
                next_remote = time.monotonic() + args.remote_interval
            time.sleep(min(0.2, max(0.01, next_local - time.monotonic())))
    except KeyboardInterrupt:
        print('\nStopping monitor.')
    finally:
        if client is not None:
            client.close()
        config['finished_at'] = now()
        write_json(session / 'session.json', config)
        summarize(argparse.Namespace(session=str(session), har=[]))


def stats(values) -> dict:
    valid = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    if not valid:
        return {'count': 0, 'mean': None, 'p95': None, 'max': None, 'first': None, 'last': None}
    ordered = sorted(valid)
    return {'count': len(valid), 'mean': statistics.mean(valid),
            'p95': ordered[max(0, math.ceil(len(valid) * .95) - 1)], 'max': max(valid),
            'first': valid[0], 'last': valid[-1]}


def har_summary(paths: list[str], marks: list[dict]) -> dict:
    result = {}
    for name in paths:
        with Path(name).open(encoding='utf-8-sig') as handle:
            entries = json.load(handle).get('log', {}).get('entries', [])
        for entry in entries:
            url = urlsplit(entry.get('request', {}).get('url', ''))
            if url.hostname not in ('localhost', '127.0.0.1', '::1'):
                continue
            if not url.path.startswith(('/jobs', '/remote/jobs')):
                continue
            # Never retain tokens, headers, request bodies, response bodies, or query parameters.
            key = entry.get('request', {}).get('method', '?') + ' ' + url.path
            phase = 'unmarked'
            try:
                stamp = datetime.fromisoformat(entry['startedDateTime'].replace('Z', '+00:00'))
                if stamp.tzinfo is not None:
                    eligible = [m for m in marks if m.get('epoch', float('inf')) <= stamp.timestamp()]
                    if eligible:
                        phase = max(eligible, key=lambda m: m['epoch']).get('phase', 'unmarked')
            except (KeyError, TypeError, ValueError):
                pass
            item = result.setdefault(phase, {}).setdefault(key, {'requests': 0, 'errors': 0, 'times_ms': [],
                                          'response_body_bytes': 0, 'known_body_sizes': 0})
            item['requests'] += 1
            response = entry.get('response', {})
            code = response.get('status', 0)
            item['errors'] += int(not code or code >= 400)
            duration = entry.get('time')
            if isinstance(duration, (int, float)) and duration >= 0:
                item['times_ms'].append(duration)
            size = response.get('bodySize')
            if isinstance(size, (int, float)) and size >= 0:
                item['known_body_sizes'] += 1
                item['response_body_bytes'] += size
    for group in result.values():
        for item in group.values():
            item['duration_ms'] = stats(item.pop('times_ms'))
    return result


def summarize(args) -> None:
    session = Path(args.session)
    if not (session / 'session.json').exists():
        raise SystemExit('Session not found.')
    local = rows(session / 'local_samples.jsonl')
    remote = rows(session / 'remote_samples.jsonl')
    marks = rows(session / 'marks.jsonl')
    phases = {}
    for phase in sorted(set(r.get('phase', 'unmarked') for r in local)):
        samples = [r for r in local if r.get('phase', 'unmarked') == phase]
        groups = {}
        for role in ('ui', 'backend', 'monitor'):
            cpu, ram = [], []
            for sample in samples:
                processes = [p for p in sample['processes'] if p['role'] == role]
                known = [p['cpu_pct_one_core'] for p in processes if p['cpu_pct_one_core'] is not None]
                if processes:
                    ram.append(sum(p['rss_bytes'] for p in processes))
                # Do not report a partial process group as a complete CPU total.
                if processes and len(known) == len(processes):
                    cpu.append(sum(known))
            groups[role] = {'cpu_pct_one_core': stats(cpu), 'rss_bytes': stats(ram)}
        interfaces = sorted(set(k for s in samples for k in s['network']))
        network = {name: {direction: stats(s['network'].get(name, {}).get(direction + '_bytes_per_second')
                                          for s in samples) for direction in ('received', 'sent')}
                   for name in interfaces}
        phases[phase] = {'samples': len(samples), 'process_groups': groups, 'interface_bytes_per_second': network}
    requests = har_summary(args.har, marks)
    result = {'version': 1, 'generated_at': now(), 'local_samples': len(local), 'remote_samples': len(remote),
              'phases': phases, 'ui_requests_from_har': requests,
              'observed_processes': [dict(zip(('pid', 'role', 'name'), item)) for item in sorted(
                  set((p['pid'], p['role'], p['name']) for sample in local for p in sample['processes']))],
              'remote': {'host_cpu_pct_all_cores': stats(r.get('host_cpu_pct_all_cores') for r in remote),
                         'probe_seconds': stats(r['probe']['elapsed_seconds'] for r in remote),
                         'probe_cpu_seconds': stats(r['probe']['cpu_seconds'] for r in remote),
                         'sample_round_trip_seconds': stats(r['request_seconds'] for r in remote),
                         'monitor_response_payload_bytes': sum(r['response_payload_bytes'] for r in remote),
                         'first_log_bytes': remote[0]['log_bytes'] if remote else None,
                         'last_log_bytes': remote[-1]['log_bytes'] if remote else None,
                         'inventory_partial': any(r['inventory_partial'] for r in remote)},
              'manual_checks': [r for r in marks if r.get('check')],
              'download_checks': rows(session / 'download_checks.jsonl'),
              'local_sample_gap_seconds': stats(b['epoch'] - a['epoch'] for a, b in zip(local, local[1:])),
              'remote_errors': rows(session / 'remote_errors.jsonl'),
              'limits': ['Interface totals include other programs, VPN traffic, and this monitor.',
                         'Monitor SSH response bytes are not UI request bytes or complete SSH wire bytes.',
                         'Worker measurements exclude container processes.',
                         'Recent task metrics reuse existing job samples; their timestamps can be older than the probe.',
                         'Missing log roots and inventory limits can reduce log size totals.',
                         'Process RSS sums can count shared pages more than once.',
                         'UI correctness checks are manual observations, not automatic verification.',
                         'HAR request measurements require a manual network export.',
                         'No frame timing or exact per-process network bandwidth is measured.',
                         'Different MRI stages prevent causal overhead conclusions from phase averages alone.']}
    write_json(session / 'summary.json', result)
    def fmt(value):
        return 'Not measured' if value is None else f'{value:.2f}'
    lines = ['# Operator Console monitoring report', '', 'Generated: ' + result['generated_at'], '',
             '| Phase | Samples | UI CPU mean, % | UI RAM peak, MiB | Backend CPU mean, % | Monitor CPU mean, % |',
             '|---|---:|---:|---:|---:|---:|']
    for phase, data in phases.items():
        groups = data['process_groups']
        memory = groups['ui']['rss_bytes']['max']
        lines.append('| ' + ' | '.join((phase, str(data['samples']),
            fmt(groups['ui']['cpu_pct_one_core']['mean']), fmt(memory / 1048576 if memory is not None else None),
            fmt(groups['backend']['cpu_pct_one_core']['mean']), fmt(groups['monitor']['cpu_pct_one_core']['mean']))) + ' |')
    lines += ['', 'Process CPU: 100% means one logical core.', '',
              '## Server records', '', f"- Successful samples: {len(remote)}.",
              '- Remote sample errors: ' + str(len(result['remote_errors'])) + '.',
              '- Mean probe duration, seconds: ' + fmt(result['remote']['probe_seconds']['mean']) + '.',
              '- Mean probe round trip, seconds: ' + fmt(result['remote']['sample_round_trip_seconds']['mean']) + '.',
              '- First saved-log bytes: ' + str(result['remote']['first_log_bytes']) + '.',
              '- Last saved-log bytes: ' + str(result['remote']['last_log_bytes']) + '.',
              '- These totals cover discovered log files, not all output data.', '',
              '## UI request measurements', '']
    if requests:
        lines += ['| Phase | Endpoint | Requests | Errors | Mean, ms | P95, ms | Known body bytes |',
                  '|---|---|---:|---:|---:|---:|---:|']
        for phase, group in sorted(requests.items()):
            for key, value in sorted(group.items()):
                lines.append(f"| {phase} | {key} | {value['requests']} | {value['errors']} | {fmt(value['duration_ms']['mean'])} | "
                             f"{fmt(value['duration_ms']['p95'])} | {value['response_body_bytes']} |")
        lines += ['', 'Body byte totals exclude unknown sizes, headers, and transport overhead.']
    else:
        lines += ['Not measured. Add a manual browser HAR export with the summarize command.']
    lines += ['', '## Manual UI checks', '']
    checks = result['manual_checks']
    lines += [f"- {r['time']}: {r['check']} = {r['result']}. Subject: {r.get('subject') or 'unspecified'}."
              for r in checks] or ['No manual checks recorded.']
    lines += ['', '## Exact raw download comparisons', '']
    lines += [f"- {r['download']}: saved output bytes match = {r.get('all_output_bytes_match', r.get('exact_bytes_match'))}."
              for r in result['download_checks']] or ['No raw download comparisons recorded.']
    lines += ['', '## Measurement limits', ''] + ['- ' + limit for limit in result['limits']]
    (session / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Report: ' + str((session / 'report.md').resolve()))


def compare_download(args) -> None:
    """Compare an exact raw UI download with its known server source, read-only."""
    session = Path(args.session)
    config = json.loads((session / 'session.json').read_text(encoding='utf-8'))
    if config['local_only']:
        raise SystemExit('This command needs a server capture session.')
    source = PurePosixPath(args.remote_source)
    job = PurePosixPath(config['job_dir'])
    roots = [job] + [PurePosixPath(r) for r in config['remote_log_root']]
    if '..' in source.parts or not any(source.is_relative_to(root) for root in roots):
        raise SystemExit('Source must be inside the job directory or an explicit remote log root.')
    path = Path(args.download)
    local_hash = hashlib.sha256()
    local_before = path.stat()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            local_hash.update(chunk)
    local_after = path.stat()
    client = connect(config)
    try:
        with client.open_sftp() as sftp:
            resolved = PurePosixPath(sftp.normalize(str(source)))
            resolved_roots = [PurePosixPath(sftp.normalize(str(root))) for root in roots]
            if not any(resolved.is_relative_to(root) for root in resolved_roots):
                raise SystemExit('Resolved source is outside the allowed log roots.')
            before = sftp.stat(str(resolved))
            remote_hash = hashlib.sha256()
            received = 0
            with sftp.open(str(resolved), 'rb') as handle:
                while True:
                    chunk = handle.read(65536)
                    if not chunk:
                        break
                    received += len(chunk)
                    remote_hash.update(chunk)
            after = sftp.stat(str(resolved))
    finally:
        client.close()
    stable = (before.st_size, before.st_mtime) == (after.st_size, after.st_mtime)
    local_stable = (local_before.st_size, local_before.st_mtime_ns) == (local_after.st_size, local_after.st_mtime_ns)
    record = {'time': now(), 'download': str(path.resolve()), 'remote_source': str(source),
              'local_sha256': local_hash.hexdigest(), 'remote_sha256': remote_hash.hexdigest(),
              'remote_bytes_read': received, 'source_stable_during_read': stable,
              'download_stable_during_read': local_stable,
              'exact_bytes_match': stable and local_stable and local_hash.digest() == remote_hash.digest(),
              'scope': 'Exact raw file only; generated combined files and ZIP files need their own manifest comparison.'}
    append(session / 'download_checks.jsonl', record)
    print(json.dumps(record, indent=2))


def verify_export(args) -> None:
    """Check a combined console export against independently read server logs."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from pipeline.console_reader import ConsoleFiles, EXPORT_TRAILER, read_console
    session = Path(args.session)
    config = json.loads((session / 'session.json').read_text(encoding='utf-8'))
    if config['local_only']:
        raise SystemExit('This command needs a server capture session.')
    path = Path(args.download)
    before = path.stat()
    with path.open('rb') as handle:
        start = max(0, before.st_size - 262144)
        handle.seek(start)
        end = handle.read()
        marker = end.rfind(EXPORT_TRAILER)
        if marker < 0:
            raise SystemExit('This file has no combined console export manifest.')
        manifest_start = start + marker
        manifest = json.loads(end[marker + len(EXPORT_TRAILER):])
        job_id = PurePosixPath(config['job_dir']).name
        if manifest.get('version') != 1 or manifest.get('job_id') != job_id:
            raise SystemExit('Export version or job identity does not match this session.')
        if manifest.get('subject_id') != args.subject:
            raise SystemExit('Export subject does not match the selected subject.')
        client = connect(config)
        checks = []
        try:
            with client.open_sftp() as sftp:
                files = ConsoleFiles(config['job_dir'], sftp, config['host'])
                catalog = read_console(files, {'subject_id': manifest['subject_id'],
                    'input_file': manifest['input_file'], 'mode': 'summary'})
                sources = {r['record_id']: r for r in catalog['_records']}
                entries = manifest.get('records', [])
                if len(entries) > 500:
                    raise SystemExit('Export manifest record limit exceeded.')
                for entry in entries:
                    identifier = entry['record_id']
                    source = sources.get(identifier)
                    offset, count = int(entry['offset']), int(entry['bytes'])
                    if not source or offset < 0 or count < 0 or offset + count > manifest_start:
                        checks.append({'record_id': identifier, 'match': False, 'reason': 'Invalid source or byte range'})
                        continue
                    handle.seek(offset)
                    local_digest = hashlib.sha256()
                    remaining = count
                    while remaining:
                        block = handle.read(min(65536, remaining))
                        if not block:
                            break
                        local_digest.update(block)
                        remaining -= len(block)
                    source_before = files.info(source['_path'])
                    remote_digest = hashlib.sha256()
                    remote_remaining = count
                    with files.open(source['_path']) as remote:
                        while remote_remaining:
                            block = remote.read(min(65536, remote_remaining))
                            if not block:
                                break
                            remote_digest.update(block)
                            remote_remaining -= len(block)
                    source_after = files.info(source['_path'])
                    stable = (source_before.st_size, source_before.st_mtime) == (source_after.st_size, source_after.st_mtime)
                    match = (not remaining and not remote_remaining and stable and entry.get('read_complete') is True
                             and local_digest.hexdigest() == entry['sha256'] == remote_digest.hexdigest())
                    checks.append({'record_id': identifier, 'match': bool(match),
                                   'source_stable': stable, 'source_bytes': source_after.st_size,
                                   'exported_bytes': count, 'matches_current_length': source_after.st_size == count})
                same_records = len(entries) == len(sources) and {e['record_id'] for e in entries} == set(sources)
        finally:
            client.close()
    after = path.stat()
    local_stable = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    record = {'time': now(), 'kind': 'combined_export', 'download': str(path.resolve()),
              'subject_id': manifest['subject_id'], 'all_saved_records_included': same_records,
              'download_stable_during_read': local_stable, 'records': checks,
              'all_output_bytes_match': bool(checks) and local_stable and same_records and all(c['match'] for c in checks),
              'matches_current_server_output': same_records and all(c.get('matches_current_length') for c in checks),
              'scope': 'Saved tool output only. Missing historical output and visual UI correctness are not reconstructed.'}
    append(session / 'download_checks.jsonl', record)
    print(json.dumps(record, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    watch = sub.add_parser('capture', help='Measure a job started manually through the UI.')
    watch.add_argument('--session', required=True)
    watch.add_argument('--job-dir', help='Exact server job directory. The monitor can wait for it to appear.')
    watch.add_argument('--host', default='10.8.0.1')
    watch.add_argument('--port', type=int, default=19622)
    watch.add_argument('--user', default='catcd1')
    watch.add_argument('--key', default=str(Path.home() / '.ssh' / 'duat'))
    watch.add_argument('--known-hosts', default=str(Path.home() / '.ssh' / 'known_hosts'))
    watch.add_argument('--remote-python', default='python3')
    watch.add_argument('--remote-log-root', action='append', default=[])
    watch.add_argument('--max-log-files', type=int, default=1000)
    watch.add_argument('--interval', type=float, default=5)
    watch.add_argument('--remote-interval', type=float, default=30)
    watch.add_argument('--duration', type=float, default=0, help='Maximum seconds. Zero means no fixed limit.')
    watch.add_argument('--finish-grace', type=float, default=120, help='Seconds to continue after terminal job state.')
    watch.add_argument('--app-pid', action='append', type=int, default=[], help='Additional UI root process. Include children.')
    watch.add_argument('--backend-pid', action='append', type=int, default=[], help='Additional backend root process. Include children.')
    watch.add_argument('--local-only', action='store_true', help='Record local resources without SSH.')
    watch.set_defaults(handler=capture)
    checkpoint = sub.add_parser('mark', help='Record a manual UI phase or correctness check.')
    checkpoint.add_argument('--session', required=True)
    checkpoint.add_argument('--phase', required=True,
                            choices=('closed', 'console', 'summary', 'detailed', 'scroll_paused', 'download', 'finished'))
    for name in ('subject', 'stage', 'attempt', 'check', 'note', 'evidence'):
        checkpoint.add_argument('--' + name, default='')
    checkpoint.add_argument('--result', choices=('pass', 'fail', 'unknown'), default='unknown')
    checkpoint.set_defaults(handler=mark)
    report = sub.add_parser('summarize', help='Create a report from saved measurements.')
    report.add_argument('--session', required=True)
    report.add_argument('--har', action='append', default=[], help='Optional manual DevTools HAR export. Never copied into reports.')
    report.set_defaults(handler=summarize)
    download = sub.add_parser('compare-download', help='Compare an exact downloaded raw file with its server source.')
    download.add_argument('--session', required=True)
    download.add_argument('--download', required=True)
    download.add_argument('--remote-source', required=True)
    download.set_defaults(handler=compare_download)
    combined = sub.add_parser('verify-export', help='Verify a combined console export against saved server output.')
    combined.add_argument('--session', required=True)
    combined.add_argument('--download', required=True)
    combined.add_argument('--subject', required=True, help='Expected subject selected in the UI.')
    combined.set_defaults(handler=verify_export)
    args = parser.parse_args()
    args.handler(args)


if __name__ == '__main__':
    main()
