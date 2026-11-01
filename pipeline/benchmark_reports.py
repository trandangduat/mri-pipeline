"""Native Scheduler benchmark exports, including every recorded attempt."""
import collections
import csv
from datetime import datetime, timezone
from decimal import Decimal
import io
import json
from pathlib import Path
import re
import sqlite3
import statistics

from .hardware import _host_info
from .registry import tool_display_name

STEP_FIELDS = 'experiment,job_id,image_id,subject_id,runtime_subject_id,input_file,subject_dir,stage_id,stage,tool,tool_label,attempt_id,attempt_number,retry_ordinal,configuration_id,execution_mode,cpu_threads,job_cpu_limit_threads,ram_percent,gpu_id,reserved_ram_mib,reserved_gpu_memory_mib,reserved_disk_mib,estimated_runtime_ms,observed_runtime_ms,runtime_source,run_sec,build_pull_sec,started_at,finished_at,status,success,exit_code,validation_passed,error_category,error,peak_ram_bytes,avg_ram_bytes,p95_ram_bytes,peak_ram_mib,avg_ram_mib,p95_ram_mib,peak_cpu_pct,avg_cpu_pct,p95_cpu_pct,cpu_sample_count,ram_sample_count,container_name,hostname,logical_cores,total_ram_bytes,cpu_vendor,cpu_model,physical_cores,source_attempts,source_results,source_metrics,source_stage_log'.split(',')
SUMMARY_FIELDS = 'experiment,job_id,record_type,image_id,subject_id,stage_id,stage,tool,final_status,started_at,finished_at,elapsed_wall_sec,wall_time_definition,images,completed_stages,failed_stages,skipped_stages,attempts,successful_attempts,failed_attempts,retries,total_run_sec,final_attempt_run_sec,nonfinal_attempt_run_sec,retry_run_sec,total_build_pull_sec,avg_run_sec,median_run_sec,min_run_sec,max_run_sec,max_attempt_peak_ram_bytes,avg_attempt_peak_ram_mib,max_attempt_peak_cpu_pct,avg_attempt_peak_cpu_pct,attempt_scope,source_status,source_steps'.split(',')


def _write(path, fields, records):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter='\t', lineterminator='\n')
    writer.writeheader()
    writer.writerows({key: 'NA' if r.get(key) is None or r.get(key) == '' else r[key] for key in fields} for r in records)
    temporary = path.with_suffix('.tsv.tmp')
    temporary.write_text(stream.getvalue(), encoding='utf-8')
    temporary.replace(path)


def _utc(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    return value


def _total(records, field):
    values = [r[field] for r in records]
    return str(sum((Decimal(str(v)) for v in values), Decimal(0))) if all(v is not None for v in values) else None


def _summary(kind, records, tasks, status, job_id):
    first = records[0]
    result = dict.fromkeys(SUMMARY_FIELDS)
    result.update(experiment=first['experiment'], job_id=job_id, record_type=kind,
                  image_id=first['image_id'] if kind == 'SCAN' else 'ALL',
                  subject_id=first['subject_id'] if kind == 'SCAN' else 'ALL',
                  stage_id=first['stage_id'] if kind == 'STAGE_TOOL' else 'ALL',
                  stage=first['stage'] if kind == 'STAGE_TOOL' else 'ALL',
                  tool=first['tool'] if kind == 'STAGE_TOOL' else 'ALL',
                  final_status=status.get('state', 'running') if kind == 'JOB' else (
                      'COMPLETED' if all(t['state'] in ('COMPLETED', 'SKIPPED') for t in tasks) else 'INCOMPLETE'),
                  images=len({r['image_id'] for r in records}),
                  completed_stages=sum(t['state'] == 'COMPLETED' for t in tasks),
                  failed_stages=sum(t['state'] == 'FAILED' for t in tasks),
                  skipped_stages=sum(t['state'] == 'SKIPPED' for t in tasks),
                  attempts=len(records), successful_attempts=sum(r['success'] for r in records),
                  failed_attempts=sum(not r['success'] for r in records),
                  retries=sum(r['retry_ordinal'] > 0 for r in records),
                  total_run_sec=_total(records, 'run_sec'), total_build_pull_sec=_total(records, 'build_pull_sec'),
                  attempt_scope='ALL_RECORDED_ATTEMPTS', source_status='job_status.json', source_steps='benchmark_steps.tsv')
    latest = {}
    for record in records:
        key = (record['runtime_subject_id'], record['stage_id'])
        if key not in latest or record['attempt_number'] > latest[key]['attempt_number']:
            latest[key] = record
    final_ids = {r['attempt_id'] for r in latest.values()}
    for name, subset in [('final_attempt_run_sec', [r for r in records if r['attempt_id'] in final_ids]),
                         ('nonfinal_attempt_run_sec', [r for r in records if r['attempt_id'] not in final_ids]),
                         ('retry_run_sec', [r for r in records if r['retry_ordinal'] > 0])]:
        result[name] = _total(subset, 'run_sec')
    starts = [r['started_at'] for r in records if r['started_at']]
    finishes = [r['finished_at'] for r in records if r['finished_at']]
    result['started_at'] = _utc(status.get('started_at')) if kind == 'JOB' else min(starts, default=None)
    result['finished_at'] = _utc(status.get('finished_at')) if kind == 'JOB' else max(finishes, default=None)
    result['wall_time_definition'] = 'RECORDED_JOB_WALL_TIME' if kind == 'JOB' else 'FIRST_ATTEMPT_START_TO_LAST_ATTEMPT_FINISH'
    if kind == 'JOB':
        result['elapsed_wall_sec'] = status.get('duration_sec')
    elif result['started_at'] and result['finished_at']:
        result['elapsed_wall_sec'] = (datetime.fromisoformat(result['finished_at']) - datetime.fromisoformat(result['started_at'])).total_seconds()
    runtimes = [float(r['run_sec']) for r in records if r['run_sec'] is not None]
    if runtimes:
        result.update(avg_run_sec=statistics.mean(runtimes), median_run_sec=statistics.median(runtimes),
                      min_run_sec=min(runtimes), max_run_sec=max(runtimes))
    ram = [r['peak_ram_bytes'] for r in records if r['peak_ram_bytes'] is not None]
    cpu = [r['peak_cpu_pct'] for r in records if r['peak_cpu_pct'] is not None]
    result.update(max_attempt_peak_ram_bytes=max(ram) if ram else None,
                  avg_attempt_peak_ram_mib=statistics.mean(ram) / 1048576 if ram else None,
                  max_attempt_peak_cpu_pct=max(cpu) if cpu else None,
                  avg_attempt_peak_cpu_pct=statistics.mean(cpu) if cpu else None)
    return result


def write_scheduler_benchmarks(job_dir, config):
    job_dir = Path(job_dir)
    database = job_dir / 'neuroflow_workspace.sqlite'
    if not database.exists():
        return
    with sqlite3.connect('file:' + database.resolve().as_posix() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        tasks = {r['task_id']: dict(r) for r in conn.execute('select * from tasks')}
        results = {r['attempt_id']: dict(r) for r in conn.execute('select * from results')}
        images = {r['image_id']: json.loads(r['canonical_spec_json'])['metadata'] for r in conn.execute('select * from images')}
        attempts = [dict(r) for r in conn.execute('select * from attempts order by started_at, attempt_id')]
    status_path = job_dir / 'job_status.json'
    status = json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else {}
    host = _host_info()
    records = []
    for attempt in attempts:
        if attempt['attempt_id'] not in results:
            continue
        result = results[attempt['attempt_id']]
        task = tasks[attempt['task_id']]
        metadata = json.loads(task['metadata_json'])
        image = images[task['image_id']]
        measured = json.loads(result['metrics_json'])
        step = json.loads(result['metadata_json']).get('application_step') or {}
        scan_ids = set(re.findall(r'I\d+', image['input_file']))
        row = dict.fromkeys(STEP_FIELDS)
        row.update(experiment=config.get('experiment_label', config.get('neuroflow_policy')), job_id=job_dir.name,
                   image_id=next(iter(scan_ids)) if len(scan_ids) == 1 else task['image_id'],
                   subject_id=image['subject_id'], runtime_subject_id=task['image_id'], input_file=image['input_file'],
                   subject_dir=str(Path(config.get('effective_output_dir', config.get('output_dir', ''))) / image['subject_id']),
                   stage_id=task['stage_id'], stage=metadata.get('pipeline_stage'), tool=metadata.get('pipeline_tool_key'),
                   attempt_id=attempt['attempt_id'], attempt_number=attempt['attempt_number'], retry_ordinal=attempt['retry_ordinal'],
                   configuration_id=attempt['configuration_id'], execution_mode=attempt['execution_mode'], cpu_threads=attempt['cpu_threads'],
                   job_cpu_limit_threads=config.get('threads'), ram_percent=config.get('ram_percent'), gpu_id=attempt['gpu_id'],
                   reserved_ram_mib=attempt['reserved_ram_mib'], reserved_gpu_memory_mib=attempt['reserved_gpu_memory_mib'],
                   reserved_disk_mib=attempt['reserved_disk_mib'], estimated_runtime_ms=attempt['estimated_runtime_ms'],
                   observed_runtime_ms=measured.get('runtime_ms'), runtime_source='application_step.duration_sec' if step.get('duration_sec') is not None else 'results.metrics_json.runtime_ms',
                   run_sec=step.get('duration_sec') if step.get('duration_sec') is not None else (
                       str(Decimal(measured['runtime_ms']) / 1000) if measured.get('runtime_ms') is not None else None),
                   build_pull_sec=step.get('build_duration_sec'), started_at=attempt['started_at'], finished_at=attempt['finished_at'],
                   status=result['status'], success=result['status'] == 'SUCCEEDED', exit_code=result['exit_code'],
                   validation_passed=result['validation_passed'], error_category=result['error_category'], error=result['error_message'],
                   container_name=step.get('container_name'), source_attempts='neuroflow_workspace.sqlite#attempts',
                   source_results='neuroflow_workspace.sqlite#results', source_metrics='metrics.jsonl')
        row['tool_label'] = tool_display_name(row['tool']) if row['tool'] else None
        row['source_stage_log'] = str(Path(row['subject_dir']) / 'logs' / (row['tool'] + '.log')) if row['tool'] else None
        for name in ['peak_ram_bytes', 'avg_ram_bytes', 'p95_ram_bytes', 'peak_cpu_pct', 'avg_cpu_pct', 'p95_cpu_pct']:
            row[name] = step.get(name)
        row['cpu_sample_count'] = step.get('cpu_sample_count')
        row['ram_sample_count'] = step.get('ram_sample_count')
        for name in ['peak', 'avg', 'p95']:
            raw = row[name + '_ram_bytes']
            row[name + '_ram_mib'] = str(Decimal(raw) / 1048576) if raw is not None else None
        for key in ['hostname', 'logical_cores', 'total_ram_bytes', 'cpu_vendor', 'cpu_model', 'physical_cores']:
            row[key] = host.get(key)
        records.append(row)
    summaries = []
    if records:
        summaries.append(_summary('JOB', records, list(tasks.values()), status, job_dir.name))
        for image in sorted({r['runtime_subject_id'] for r in records}):
            summaries.append(_summary('SCAN', [r for r in records if r['runtime_subject_id'] == image],
                [t for t in tasks.values() if t['image_id'] == image], status, job_dir.name))
        groups = collections.defaultdict(list)
        for record in records:
            groups[(record['stage_id'], record['tool'])].append(record)
        for (stage_id, _), group in sorted(groups.items()):
            summaries.append(_summary('STAGE_TOOL', group, [t for t in tasks.values() if t['stage_id'] == stage_id], status, job_dir.name))
    _write(job_dir / 'benchmark_steps.tsv', STEP_FIELDS, records)
    _write(job_dir / 'benchmark_summary.tsv', SUMMARY_FIELDS, summaries)
