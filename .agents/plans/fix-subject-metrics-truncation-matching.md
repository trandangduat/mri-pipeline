# Fix Subject CPU/RAM Metrics Matching and Truncation

## User Review Required
> [!NOTE]
> This fix handles both backward compatibility (historical jobs on server like `job_20260828_104109`) and forward compatibility (future runs with explicit `subject_id` and `input_file` emitted in `events.jsonl`).

## Proposed Changes

### Frontend Layer: [tauri-app](file:///c:/Users/ADMIN/Desktop/mri-pipeline/tauri-app)

#### [MODIFY] [jobs.ts](file:///c:/Users/ADMIN/Desktop/mri-pipeline/tauri-app/src/lib/jobs.ts)
- Update `isEventForImage(event, image)`:
  - First, check direct match on `event.subject_id === image.subject_id` or `event.input_file === image.input_file`.
  - For container name matching:
    - Strip prefix `mri-` and trailing hex `-<uuid8>` to extract `core`.
    - Support prefix/core matching: if `image.subject_id` starts with `core` or `core` starts with `image.subject_id` (min length 6), or if `sanitizedSubj` starts with `core`.
    - Check if a prefix of `image.subject_id` (first 30 characters) is contained in `container_name`.
- Update `deriveMetricsSeries(events, image)`:
  - Track `currentActiveFile` across `image_start` and `image_done`.
  - Add fallback matching when metrics events have no targeting metadata `(!event.input_file && !event.subject_id && !event.container_name && (currentActiveFile ? currentActiveFile === image.input_file : true))` matching `deriveImageSteps()`.

#### [MODIFY] [jobs.test.ts](file:///c:/Users/ADMIN/Desktop/mri-pipeline/tauri-app/test/jobs.test.ts)
- Add unit tests for:
  - Long ADNI subject IDs (98 characters) matching truncated container names.
  - Matching events with explicit `subject_id` / `input_file`.
  - `deriveMetricsSeries` extracting non-empty CPU/RAM series from truncated container names.

---

### Backend Layer: [pipeline](file:///c:/Users/ADMIN/Desktop/mri-pipeline/pipeline)

#### [MODIFY] [config.py](file:///c:/Users/ADMIN/Desktop/mri-pipeline/pipeline/config.py)
- Extend `MetricsCallback` type signature to accept optional `subject_id: str | None = None` and `input_file: str | None = None`.

#### [MODIFY] [runner.py](file:///c:/Users/ADMIN/Desktop/mri-pipeline/pipeline/runner.py)
- In `_metrics_relay` inside `run_pipeline_stage` and `run_pipeline_batch`: pass `subject_id=config.subject_id, input_file=config.input_file` to `on_metrics`.

#### [MODIFY] [job_worker.py](file:///c:/Users/ADMIN/Desktop/mri-pipeline/pipeline/job_worker.py)
- In `metrics_cb`: accept `subject_id: str | None = None, input_file: str | None = None` and emit them directly in `"metrics"` event payload.

#### [MODIFY] [cli.py](file:///c:/Users/ADMIN/Desktop/mri-pipeline/pipeline/cli.py)
- In `metrics_cb`: accept and emit `subject_id` and `input_file` in the JSON event.

---

## Verification Plan

### Automated Tests
- Run `npm test -- --run` in `tauri-app` to verify all test suites pass.
- Run `pytest` to verify pipeline and backend tests pass.

### Manual Verification
- Test with real data from `job_20260828_104109` to confirm all 4 subjects display CPU/RAM series and metrics.
