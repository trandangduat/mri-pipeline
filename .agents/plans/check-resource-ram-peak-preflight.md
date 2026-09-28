# Check Resource RAM Peak in Remote Preflight

## Goal

Add a server resource check step to the remote preflight pipeline immediately following the SSH connection step:
- Compute the allocated RAM on the remote server (`total_ram_bytes * ram_percent / 100`).
- Compare allocated RAM against the peak memory requirement (`ram peak`) of the selected pipeline profile (e.g. FreeSurfer 7, FreeSurfer 8, FastSurfer presets or custom profiles).
- If allocated RAM is insufficient:
  - Fail the preflight at step `resources`.
  - Display an actionable error message on the UI listing the pipeline presets that CAN run within the allocated RAM for FreeSurfer 7, FreeSurfer 8, and FastSurfer.
  - Halt preflight before validating/staging later steps.
- If allocated RAM is sufficient:
  - Mark step `resources` as done with a summary of allocated vs peak RAM.
  - Continue to subsequent preflight steps.

## Profile Peak Memory Reference

From `configs/neuroflow/profiles/*.yaml`:
- **FreeSurfer 7 + Volume**: 2,083 MiB (~2.0 GiB)
- **FastSurfer + Volume**: 6,830 MiB (~6.7 GiB)
- **FreeSurfer 7 + Cortical Thickness**: 11,878 MiB (~11.6 GiB)
- **FastSurfer + Cortical Thickness**: 11,878 MiB (~11.6 GiB)
- **FreeSurfer 7 + Volume + Cortical Thickness**: 13,660 MiB (~13.3 GiB)
- **FastSurfer + Volume + Cortical Thickness**: 13,660 MiB (~13.3 GiB)
- **FreeSurfer 8 + Cortical Thickness**: 14,900 MiB (~14.6 GiB)
- **FreeSurfer 8 + Volume + Cortical Thickness**: 14,900 MiB (~14.6 GiB)
- **FreeSurfer 8 + Volume**: 16,507 MiB (~16.1 GiB)

## Implementation Plan

1. **Profile Memory Helper (`pipeline/profile_memory.py`)**:
   - `get_profile_peak_ram_mib(profile_path_or_mode: str) -> int`
   - `get_all_standard_profile_peaks() -> dict[str, int]`
   - `get_runnable_profiles(allocated_ram_mib: int) -> list[tuple[str, int]]`
   - `format_resource_check_failure(allocated_ram_mib: int, required_peak_mib: int, mode_name: str, total_ram_mib: int, ram_percent: int) -> str`

2. **Backend Remote Preflight Integration (`app_backend/remote.py`)**:
   - In `RemoteJobService.stream_start_job()`:
   - Immediately after `yield step_event("ssh", "done", ...)`:
   - Yield `step_event("resources", "running", "Checking server resources...")`
   - Query `runner.remote_hardware_info()` to obtain `total_ram_bytes`.
   - Calculate allocated RAM in MiB: `allocated_ram_mib = (total_ram_bytes * ram_percent) // (100 * 1024 * 1024)`.
   - Determine `required_peak_mib` for the chosen pipeline mode or custom profile file.
   - If `allocated_ram_mib < required_peak_mib`:
     - Generate clear error message listing runnable FreeSurfer 7, FreeSurfer 8, and FastSurfer options.
     - Yield `step_event("resources", "failed", error_message)`.
     - Yield `complete_event(False, error=error_message)`.
     - Return early.
   - If sufficient:
     - Yield `step_event("resources", "done", detail_message)`.
     - Proceed to `validate` step.

3. **Frontend Integration (`tauri-app`)**:
   - `tauri-app/src/hooks/useStartPipelineStream.ts`:
     - Add `{id: 'resources', label: 'Checking server resources', status: 'pending'}` to `REMOTE_STEPS` right after `ssh`.
   - `tauri-app/src/components/StartPipelineDialog.tsx`:
     - Add `whitespace-pre-line` to `step.detail` and `errorMessage` to properly render multi-line recommendation lists.

4. **Testing**:
   - Unit tests in `tests/test_profile_memory.py`:
     - Accurate extraction of peak RAM from YAML profiles.
     - Filtering of runnable profiles based on allocated RAM.
     - Clear formatting of failure messages.
   - Backend remote preflight tests in `tests/test_app_backend_remote.py`:
     - Insufficient RAM causes step `resources` to fail with recommendation list and halts stream.
     - Sufficient RAM allows step `resources` to pass and continues to `validate`.
   - Frontend tests in `tauri-app/test/useStartPipelineStream.test.tsx`:
     - Verify step list order (`ssh` -> `resources` -> `validate` -> ...).
     - Verify failure at `resources` leaves later steps pending.
