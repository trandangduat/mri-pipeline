"""Record deployed source bytes independently of checkout line endings."""
import hashlib
import json
from pathlib import Path
import subprocess


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
        actual['deployed_source_matches_manifest'] = actual['source_file_sha256'] == declared.get('source_file_sha256')
        if not actual['deployed_source_matches_manifest']:
            raise RuntimeError('Deployed pipeline source differs from its recorded revision manifest')
    (Path(job_dir) / 'source_revision.json').write_text(json.dumps(actual, indent=2) + '\n', encoding='utf-8')
