# Fix Stage Timeline Not Reported Metrics and Run Telemetry Peak Truncation

## Goal

Fix two related telemetry bugs in the Subject Detail Modal (`Stage Timeline` and `Run Telemetry`) in `JobsPage`:

1. **Completed stages showing `CPU: Not reported` and `RAM: Not reported`**:
   - When opening the Subject Detail Modal for a subject with more than `1,200` metric samples in `metrics.jsonl` (such as FreeSurfer 7/8 full cortical + subcortical runs with ~2,500–3,000 samples per subject), `JobsPage.tsx` fetches up to `5,000` metric events from the backend/server and passes them into `appendBoundedEvents(prev, newMetrics, MAX_MODAL_METRICS_EVENTS)` where `MAX_MODAL_METRICS_EVENTS = 1_200`.
   - `appendBoundedEvents` slices only the last `1,200` events (`incoming.slice(-1200)`), discarding all earlier stage metric samples before `deriveImageSteps` can aggregate per-stage `cpu_pct` and `ram_bytes` peaks.
   - Additionally, `pipeline/job_worker.py` (`image_done_cb`) only writes stage `duration_sec` into `image_done.log_text` and does not persist `step.peak_cpu_pct` or `step.peak_ram_bytes` in `events.jsonl`.

2. **`Run Telemetry` sparkline header showing a low peak (`peak: 1.0 GB` RAM / `peak: 402.4%` CPU) instead of the true subject peak (`~14.4–16 GB` RAM / `2267.3%` CPU)**:
   - `deriveMetricsSeries` in `tauri-app/src/lib/jobs.ts` slices `cpuSeries` and `ramSeries` to the last `180` samples (`.slice(-180)`) without recording the all-time subject `peakCpu` and `peakRam` across all samples.
   - `MetricSparkline` in `tauri-app/src/pages/JobsPage.tsx` computes `peakVal = Math.max(...safePoints)` over only those last `180` samples (the tail of the final stages).

---

## Architecture & File Changes

### 1. `tauri-app/src/lib/jobs.ts`
- **Extend `MetricsSeries`**:
  - Add `peakCpu?: number`, `peakRam?: number`, and `peakGpu?: number` to `MetricsSeries`.
- **Add `appendModalMetricsEvents(current, incoming, limit)`**:
  - When bounding modal metric events to `limit` (`1,200`), preserve durable per-stage peak summaries (`compacted: true`) for any older/evicted metric events keyed by `(input_file, subject_id, stage)` before slicing the recent raw time-series window to `limit`.
  - Each compacted stage summary retains the maximum `cpu_pct`, `ram_bytes`, `gpu_pct`, and `elapsed`, plus the stage's `tool` and `container_name`.
- **Update `deriveImageSteps`**:
  - When processing `metrics` events (including compacted stage summaries), aggregate `cpu_pct`, `ram_bytes`, `gpu_pct`, and `elapsed_sec = Math.max(step.elapsed_sec || 0, event.elapsed)`.
  - When processing `image_done` events, also read structured `event.steps` entries (`peak_cpu_pct`, `peak_ram_bytes`, `duration_sec`, `tool`, `status`) if present, while maintaining full backward compatibility with `event.log_text`.
- **Update `deriveMetricsSeries`**:
  - Track all-time subject `peakCpu` (`%`), `peakRam` (`MB`), and `peakGpu` (`%`) across all matching `metrics` events (both compacted stage summaries and raw samples) and `image_done.steps` before slicing `cpuSeries`, `ramSeries`, and `gpuSeries` to the last `180` raw (non-compacted) samples.

### 2. `tauri-app/src/pages/JobsPage.tsx`
- Import `appendModalMetricsEvents` from `../lib/jobs` and use it in place of `appendBoundedEvents` when updating `modalMetricsEvents` (both remote and local metrics branches).
- Update `MetricSparkline` to accept an optional `peak?: number` prop and compute `peakVal = Math.max(peak ?? 0, ...safePoints)`.
- Pass `peak={modalMetricsSeries.peakCpu}` and `peak={modalMetricsSeries.peakRam}` to the CPU and RAM `MetricSparkline` components in `Run Telemetry`.

### 3. `pipeline/job_worker.py`
- In `image_done_cb`, include a structured `steps` list on the `image_done` event payload containing `stage`, `tool`, `status`, `duration_sec`, `peak_cpu_pct`, and `peak_ram_bytes` from each `StepResult` (while keeping `log_text` unchanged for backward compatibility).

### 4. Critical Tests
- **`tauri-app/test/jobs.test.ts`**:
  - Test `appendModalMetricsEvents` + `deriveImageSteps` + `deriveMetricsSeries` with `> 1,200` metric events across 9 stages to verify that stages 1–6 retain their exact `cpu_pct` and `ram_bytes` peaks even after bounding to `1,200` raw events, and that `deriveMetricsSeries` reports the true all-time `peakCpu` and `peakRam` while keeping `cpuSeries` and `ramSeries` bounded to `180` points.
  - Test `deriveImageSteps` and `deriveMetricsSeries` reading `peak_cpu_pct` and `peak_ram_bytes` from `image_done.steps`.
- **`tests/test_job_worker.py`**:
  - Test that `_run_job` emits `steps` with `peak_cpu_pct` and `peak_ram_bytes` in the `image_done` event inside `events.jsonl`.
