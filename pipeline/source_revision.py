"""Record deployed source bytes independently of checkout line endings."""
import hashlib
import json
from pathlib import Path
import subprocess

# These removed helpers can remain in a reused deployment directory. They are
# not imported by the current runtime and must not be mistaken for edited code.
_REMOVED_GPU_HELPERS = {'pipeline/gpu_readiness.py', 'pipeline/gpu_setup.py'}


def source_manifest(root):
    root = Path(root)
    files = sorted((root / 'pipeline').glob('*.py'))
    files += [root / 'pipeline_runner.py', root / 'normalize_volumes.py']
    files += [root / 'info/cat12_tissue_flags.txt', root / 'info/cat12_roi_mapping.txt']
    records = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
    revision = None
    try:
        result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            revision = result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {'git_commit': revision, 'source_file_sha256': records,
            'source_digest': hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()}


def record_job_source(job_dir):
    root = Path(__file__).resolve().parents[1]
    actual = source_manifest(root)
    declared_path = root / 'source_revision.json'
    if declared_path.is_file():
        declared = json.loads(declared_path.read_text(encoding='utf-8'))
        actual['declared_git_commit'] = declared.get('git_commit')
        expected = declared.get('source_file_sha256')
        if not isinstance(expected, dict) or not expected:
            raise RuntimeError('Deployed source revision manifest has no source file hashes')
        measured = actual['source_file_sha256']
        missing = sorted(expected.keys() - measured.keys())
        changed = sorted(name for name in expected.keys() & measured.keys() if expected[name] != measured[name])
        extra = measured.keys() - expected.keys()
        legacy = sorted(extra & _REMOVED_GPU_HELPERS)
        unexpected = sorted(extra - _REMOVED_GPU_HELPERS)
        actual['declared_source_files_match'] = not missing and not changed
        actual['legacy_unlisted_source_files'] = {name: measured[name] for name in legacy}
        actual['unexpected_source_files'] = unexpected
        actual['missing_source_files'] = missing
        actual['changed_source_files'] = changed
        actual['deployed_source_matches_manifest'] = not missing and not changed and not unexpected
        # Preserve diagnostics even when validation stops the worker.
        (Path(job_dir) / 'source_revision.json').write_text(json.dumps(actual, indent=2) + '\n', encoding='utf-8')
        if not actual['deployed_source_matches_manifest']:
            details = '; '.join(label + ': ' + ', '.join(names) for label, names in
                                [('missing', missing), ('changed', changed), ('unexpected', unexpected)] if names)
            raise RuntimeError('Deployed pipeline source differs from its recorded revision manifest (' + details + ')')
    else:
        (Path(job_dir) / 'source_revision.json').write_text(json.dumps(actual, indent=2) + '\n', encoding='utf-8')
