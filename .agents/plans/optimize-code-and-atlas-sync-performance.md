# Optimize Code and Atlas Synchronization Performance

## Goal

Eliminate the 3-5 minute delay and continuous OpenVPN upload traffic during the "Checking code changes" pipeline start step by separating static reference atlases from Python code hashing, adding delta-skipping (file size matching) to SFTP directory uploads, and making manifest signature verification direct and resilient.

## User-Visible Requirements

- Pipeline preflight step "Checking code changes" completes within 1-2 seconds when code is unchanged or slightly modified.
- Unchanged static atlas files (~605 MB) are not re-uploaded over OpenVPN on every pipeline run.
- Missing or newly added atlas files are still uploaded properly on first-time setup or when size differs.
- Code changes in Python/configs sync quickly (< 1 MB transfer).

## Implementation Plan

### 1. SFTP Upload Optimization in `remote/ssh_client.py`

In `RemoteSSHClient.upload_dir()`:
- Add parameter `skip_existing_matching_size: bool = False`.
- In the file upload loop:
  ```python
  if skip_existing_matching_size:
      try:
          attr = self.sftp.stat(remote_file)
          if attr.st_size == local_file.stat().st_size:
              continue
      except (OSError, IOError):
          pass
  ```
- This skips re-uploading large atlas files (605 MB) when they already exist with the same size on the remote host.

### 2. Code Signature Separation in `remote/remote_runner.py`

In `_local_code_signature()`:
- Remove `PROJECT_ROOT / "assets" / "atlases" / "mni"` and `PROJECT_ROOT / "assets" / "atlases" / "surface"` from the hasher.
- The signature now focuses strictly on runnable code and configurations:
  - `pipeline_runner.py`
  - `requirements.txt`
  - `normalize_volumes.py`
  - `pipeline/**/*.py`
  - `info/**/*.txt`
  - `NeuroFLOW-private/src/**`
  - `configs/neuroflow/**`
- Changes to Python files will now only re-sync Python code, without forcing a complete re-upload of 605 MB of atlases.

### 3. Direct Manifest Verification in `remote/remote_runner.py`

In `_ensure_shared_code()`:
- Replace `manifest_probe` and `ready_cmd` (which executed `python3 -c`) with direct verification:
  - Check file existence with `test -f`: `pipeline_runner.py`, `pipeline/job_worker.py`, `code_manifest.json`.
  - Read `code_manifest.json` directly using `ssh.read_text(f"cat {shlex.quote(manifest_path)} 2>/dev/null")` or SFTP read.
  - Parse JSON locally and compare `"signature"` with `_local_code_signature()`.
- In `_upload_code()`:
  - Pass `skip_existing_matching_size=True` when calling `ssh.upload_dir` for atlas directories and code packages.

### 4. Automated Unit Tests

In `tests/test_remote_code_sync.py`:
- Test that `_local_code_signature()` produces consistent hashes for code and ignores atlas changes.
- Test that `RemoteSSHClient.upload_dir()` with `skip_existing_matching_size=True` skips existing files with identical size.
- Test that `_ensure_shared_code()` parses manifest directly and skips upload when signature matches.
