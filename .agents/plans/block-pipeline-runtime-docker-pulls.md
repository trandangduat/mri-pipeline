# Block Pipeline Runtime Docker Pulls

## Goal

Enforce a strict separation between pipeline execution and Docker image management:

- Start Pipeline must only validate and run the pipeline.
- Start Pipeline must never download or build Docker images.
- If any Docker image required by selected tools is missing, block immediately during preflight.
- Users must use Tools Configuration to download missing images.

## Current Behavior

Remote start preflight checks selected tool images in `app_backend/remote.py`, but missing images are reported as an `images` step with status `done` and the stream continues to `start_remote_detached()`.

During actual execution, selected tools can still trigger image downloads because `pipeline.runner` calls `ensure_image()` before each stage. `ensure_image()` in `pipeline/docker_ops.py` pulls images automatically if `docker image inspect` fails.

Known automatic pull/runtime paths:

- `app_backend/remote.py:213-238`: advisory remote image check; currently does not block.
- `pipeline/runner.py:260`: `run_pipeline()` stage execution calls `ensure_image()`.
- `pipeline/runner.py:535`: batch/sequential stage execution calls `ensure_image()`.
- `pipeline/export.py:51`: export format conversion calls `ensure_image("mri_convert_fs7")`.
- `remote/remote_runner.py:466-492`: `ensure_tool_images()` shells into `ensure_image()` on the remote server.
- `pipeline/cli.py:122-136`: `--ensure-images-only` currently pulls/builds selected images. This is not pipeline execution, but review whether it is still desired or redundant with Tools Configuration.
- `pipeline/docker_ops.py:123-177`: `_try_pull()` and `ensure_image()` implement automatic pull/build behavior.

Explicit Tools Configuration pull paths that should remain:

- `app_backend/tools.py:_pull_image_local()` uses `docker pull` for the Tools Configuration flow.
- `app_backend/tools.py:_pull_image_server()` uses `RemoteRunner.start_remote_image_pull()` for Tools Configuration server pulls.
- `remote/remote_runner.py:start_remote_image_pull()` and related pull-status helpers support server Tools Configuration downloads.

## Implementation Plan

### 1. Add Non-Downloading Image Check Helper

In `pipeline/docker_ops.py`, add or expose a helper that validates a tool image without pulling/building:

```python
def require_image(tool_key: str) -> tuple[bool, str]:
    tool = TOOL_DEFS.get(tool_key)
    if not tool:
        return False, f"Unknown tool: {tool_key}"
    if not is_tool_enabled(tool_key):
        return False, f"Tool is disabled because image is disabled: {tool_display_name(tool_key)} ({tool.get('image', '')})"
    image = str(tool.get("image", "") or "")
    if not image:
        return False, f"Tool has no Docker image configured: {tool_display_name(tool_key)}"
    if not image_exists(image):
        return False, f"Docker image missing: {image}. Download it from Tools Configuration before starting the pipeline."
    base_image = tool.get("base_image")
    if base_image and not image_exists(str(base_image)):
        return False, f"Docker base image missing: {base_image}. Download it from Tools Configuration before starting the pipeline."
    return True, ""
```

Keep `image_exists()`, `image_size_bytes()`, `remove_image()`, `build_image()`, and formatting helpers.

Preferred cleanup:

- Remove `_try_pull()` if no remaining code needs automatic pull.
- Remove `ensure_image()` if all call sites are migrated.
- If `ensure_image()` cannot be removed because external imports/tests expect it, change it to no longer pull/build and mark it as a check-only compatibility wrapper, but prefer removal unless tests reveal a concrete dependency.

### 2. Block Remote Start Preflight On Missing Images

Update `RemoteJobService.stream_start_job()` in `app_backend/remote.py`:

- Keep resolving selected tool keys to image names via `TOOL_DEFS`.
- Keep using `runner.check_image_statuses(image_names)`.
- If any image is missing:
  - Yield `step_event("images", "failed", message)`.
  - Yield `complete_event(False, error=message)`.
  - `return` immediately before code upload, venv checks, config upload, or `start_remote_detached()`.
- Message should direct user to Tools Configuration, not say Tools tab if product naming is now Tools Configuration.

Suggested message:

```text
1 Docker image missing. Download it from Tools Configuration before starting the pipeline: duattran05/cat12_26_glibc:latest
```

For multiple images:

```text
N Docker images missing. Download them from Tools Configuration before starting the pipeline: image1, image2, image3
```

Do not mark missing images as `done`.

### 3. Replace Runtime Auto-Pull In Pipeline Runner

Update `pipeline/runner.py`:

- Replace import `ensure_image` with `require_image` or the new check-only helper.
- Replace calls at current lines around `260` and `535`.
- Preserve failure behavior, but error text should say image is missing and must be downloaded via Tools Configuration.
- Build duration should be removed or set to `0.0` because no runtime build/pull happens.
- Remove or adjust progress/build log messaging so it does not imply downloading/building.

Expected behavior:

- If image exists, stage runs normally.
- If image is missing, stage fails quickly without running `docker pull` or `docker build`.

### 4. Replace Export Runtime Auto-Pull

Update `pipeline/export.py`:

- Replace `ensure_image("mri_convert_fs7")` with the check-only helper.
- If missing, return an error instructing the user to download the image from Tools Configuration.
- Do not pull/build during export conversion.

### 5. Remove Remote Runtime Ensure Helper If Unused

Update `remote/remote_runner.py`:

- Search for `ensure_tool_images(`.
- If unused, delete the `ensure_tool_images()` method entirely because it exists solely to pull selected tool images outside Tools Configuration.
- If used by a Tools Configuration endpoint, do not use `ensure_image()` there; route explicit downloads through `start_remote_image_pull()` instead.

### 6. Review CLI Ensure-Images Flow

`pipeline/cli.py --ensure-images-only` is a non-pipeline command, but it still performs image pull/build through `ensure_image()`.

Choose the smallest consistent change:

- If this CLI is not used by the GUI Tools Configuration, remove `--ensure-images-only` and its import/use of `ensure_image()`.
- If tests or docs rely on it as an explicit image-management command, keep it but route through explicit pull/build helpers whose name makes the action clear, for example `pull_or_build_image_for_tool()`. It must not be called by Start Pipeline.

Do not leave `ensure_image()` as an ambiguous helper that can be accidentally reintroduced into pipeline execution.

### 7. Tests

Update/add backend tests:

- In `tests/test_app_backend_remote.py`, add a test where `FakeRunner.check_image_statuses()` returns one selected image as `False`.
- Assert the final event is `complete` with `ok is False`.
- Assert an `images` step has status `failed`.
- Assert `start_remote_detached()` was not called. Add a flag/counter to `FakeRunner` or use a specialized fake.
- Assert message contains `Tools Configuration`.

Update runner tests:

- Existing `tests/test_runner_executor_integration.py` patches `pipeline.runner.ensure_image`. Replace with patching the new check helper, or adjust tests so local Docker is not required.
- Add a test that the check helper returning `(False, "Docker image missing...")` causes no executor request and returns a failed `StepResult`.

Update export tests if existing coverage exists, or add minimal coverage for `_copy_or_convert_export()` missing converter image if practical.

Update remote runner tests:

- If deleting `ensure_tool_images()`, remove/adjust any tests that target it.
- Add a grep-based or unit test only if there is already a pattern for preventing runtime `docker pull`; otherwise rely on code review and targeted grep.

### 8. Verification

Run targeted tests:

```bash
pytest tests/test_app_backend_remote.py tests/test_runner_executor_integration.py tests/test_remote_runner.py
```

Also run a source search to ensure runtime paths do not call automatic pull/build:

```bash
rg "ensure_image|_try_pull|docker pull" pipeline remote app_backend tests
```

Expected remaining `docker pull` references should be limited to explicit Tools Configuration pull flows, remote image pull management, docs/tests for those flows, or explicit CLI image-management if retained.

## Acceptance Criteria

- Starting a remote pipeline with a missing selected-tool Docker image stops at the Docker image preflight step.
- Missing image preflight emits `images` status `failed`, not `done`.
- The remote job is not uploaded or started when selected-tool images are missing.
- Local pipeline execution does not pull or build Docker images.
- Batch pipeline execution does not pull or build Docker images.
- Export conversion does not pull or build Docker images.
- Any remaining Docker download code is only reachable through explicit Tools Configuration or a clearly named explicit image-management command, not Start Pipeline.
- User-facing messages direct users to Tools Configuration.

## Notes

- Do not remove Tools Configuration download capability.
- Do not alter unrelated Docker image status UI behavior except message wording if necessary.
- Prefer deleting ambiguous automatic-download helpers over keeping compatibility wrappers unless the test suite or documented public API shows a concrete need.
