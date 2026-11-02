"""Focused requirement-5 evidence. Docker process and stats are mocked; no MRI runs."""
import csv
import json
import sqlite3
import subprocess
import threading
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pipeline import executor
from pipeline import neuroflow_adapter as adapter
from pipeline.config import StepResult


def sampled_execution(monkeypatch, scenario):
    """Run the actual sampler thread and parser against a controlled Docker reply."""
    ready = threading.Event()
    replies = {
        'missing_ram': (0, '25%|--'),
        'empty_reply': (0, ''),
        'stats_failure': (1, ''),
        'one_byte': (0, '25%|1 B / 4 GiB'),
        'two_mib': (0, '25%|2 MiB / 4 GiB'),
    }

    def stats(command, **kwargs):
        assert command[:2] == ['docker', 'stats']
        if scenario == 'stats_timeout':
            ready.set()
            raise subprocess.TimeoutExpired(command, 5)
        code, text = replies[scenario]
        if code or not text:
            ready.set()
        return SimpleNamespace(returncode=code, stdout=text)

    def communicate(**kwargs):
        assert ready.wait(5), 'Sampler did not complete its controlled read'
        return 'mock tool completed', None

    process = Mock(returncode=0)
    process.communicate.side_effect = communicate
    with monkeypatch.context() as isolated:
        isolated.setattr(executor.subprocess, 'Popen', lambda *args, **kwargs: process)
        isolated.setattr(executor.subprocess, 'run', stats)
        result = executor.LocalDockerExecutor().execute(executor.ExecutionRequest(
            image='mock-image', args=[], mounts=[], container_name='mock-ram-evidence'),
            on_metrics=lambda *args: ready.set())
    assert result.success and result.return_code == 0
    return result


@pytest.mark.parametrize('scenario,expected', [
    ('missing_ram', None), ('empty_reply', None), ('stats_failure', None),
    ('stats_timeout', None), ('one_byte', 1), ('two_mib', 2 * 1024**2),
])
def test_real_docker_sampler_preserves_missing_and_measured_ram(monkeypatch, scenario, expected):
    result = sampled_execution(monkeypatch, scenario)
    metrics = result.metrics
    assert metrics.peak_ram_bytes == metrics.avg_ram_bytes == metrics.p95_ram_bytes == expected
    assert metrics.ram_sample_count == (0 if expected is None else 1)
    if scenario == 'missing_ram':
        assert metrics.peak_cpu_pct == 25 and metrics.cpu_sample_count == 1


@pytest.mark.parametrize('policy', ['B0', 'B1', 'B6', 'B7'])
@pytest.mark.parametrize('scenario,expected_bytes', [
    ('missing_ram', None), ('one_byte', 1), ('two_mib', 2 * 1024**2),
])
def test_sampler_ram_reaches_scheduler_without_fabricated_profile(
        tmp_path, monkeypatch, policy, scenario, expected_bytes):
    adapter._ensure_neuroflow_import_path()
    from tests.test_baseline_runtime import documents
    import neuroflow.configuration as configuration

    pipeline, profiles, _ = documents([('root', [], [(1, 100, 100)])], policy)
    monkeypatch.setattr(configuration, 'load_pipeline_file', lambda path: pipeline)
    monkeypatch.setattr(configuration, 'load_profile_set_file', lambda path: profiles)
    monkeypatch.setattr(adapter, 'write_batch_reports', lambda context: None)
    monkeypatch.setattr(adapter, 'StatsGenerator', lambda config: SimpleNamespace(
        generate=lambda *args: SimpleNamespace(files=[], warnings=[])))
    measured = []

    def stage(config, name, **kwargs):
        execution = sampled_execution(monkeypatch, scenario)
        measured.append(execution)
        metrics = asdict(execution.metrics)
        return StepResult(stage=name, tool='stub', success=execution.success,
            duration_sec=execution.duration_sec, return_code=execution.return_code,
            **metrics), None

    monkeypatch.setattr(adapter, 'run_pipeline_stage', stage)
    source = tmp_path/'input.nii.gz'
    source.write_text('mock input; not MRI data', encoding='utf-8')
    job = tmp_path/'job'
    results = adapter.run_neuroflow_batch(
        job_dir=job,
        req={'pipeline_mode':'FreeSurfer 8 + Volume', 'effective_output_dir':str(tmp_path/'output'),
             'threads':4, 'runtime_ram_bytes':16*1024**3, 'device':'cpu',
             'neuroflow_policy':policy, 'neuroflow_max_retries':0,
             'neuroflow_max_concurrent_tasks':1, 'neuroflow_warmup_enabled':False,
             'neuroflow_default_configurations':{'root':'cpu_1'}, 'selected_tools':{'root':'stub'}},
        input_files=[str(source)], subject_id_map={str(source):'first'})
    assert len(measured) == 1
    expected_mib = None if expected_bytes is None else (expected_bytes + 1024**2 - 1)//1024**2
    assert results[0].success == (expected_bytes is not None)
    observations = [json.loads(line) for line in (job/'neuroflow_observations.jsonl').read_text().splitlines()]
    assert len(observations) == 1
    observation = observations[0]
    assert observation['peak_ram_mib'] == expected_mib
    with (job/'neuroflow_observations.tsv').open(newline='') as stream:
        row = next(csv.DictReader(stream, delimiter='\t'))
    assert row['peak_ram_mib'] == ('' if expected_mib is None else str(expected_mib))
    with sqlite3.connect(job/'neuroflow_workspace.sqlite') as database:
        status, category, raw, metadata = database.execute('select status,error_category,metrics_json,metadata_json from results').fetchone()
        assert json.loads(metadata)['processing_success'] is True
        assert json.loads(raw)['peak_ram_mib'] == expected_mib
        if expected_bytes is None:
            assert status == 'FAILED' and category == 'VALIDATION_FAILURE'
            assert 'RAM' in observation['error']
            assert database.execute('select count(*) from profile_observations where accepted=1').fetchone()[0] == 0
        else:
            assert status == 'SUCCEEDED' and category is None
