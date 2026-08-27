# Redesign NeuroFLOW Advanced Settings UI & Policy Integration

## Goal

Redesign and streamline the **Advanced Settings (NeuroFLOW Settings)** panel on the pipeline configuration UI. 

Per user and architectural requirements:
1. Remove internal hyperparameter fields that the autonomous adaptive scheduler manages automatically (`Scheduling risk`, `Max Retries`, `Max I/O-Heavy Tasks`, `Preserve OOM limits`, `Machine profile ID`, and detailed warm-up numerical inputs).
2. Retain essential user-facing controls in a clean, symmetrical 2x2 grid:
   - **`Max parallel tasks`** (`neuroflowMaxConcurrentTasks`)
   - **`Policy`** (`neuroflowPolicy` with flat 8 options: `B0` to `B7`, featuring interactive hover preview tooltips for each policy)
   - **`Preset configuration`** (`neuroflowPresetFile` with Browse file picker)
   - **`Profile configuration`** (`neuroflowProfileFile` with Browse file picker)
   - **`Start safely then scale up`** (`neuroflowWarmupEnabled` single checkbox toggle)
3. Ensure every field has a native `(i)` `<InfoTooltip />` explaining its purpose.
4. Connect the selected `Policy` (`B0`–`B7`) through the frontend form store, run request validation, and backend `neuroflow_adapter.py` `SchedulerConfig.policy`.

---

## Files to Modify

1. **Frontend UI & Components:**
   - `tauri-app/src/pages/PipelinePage.tsx`:
     - Refactor the `Advanced Settings` panel inside `PipelinePage`.
     - Remove cluttered algorithm inputs (`Scheduling risk`, `Max Retries`, `Max I/O`, `Preserve OOM`, and detailed warm-up step numbers).
     - Add `Policy` dropdown with 8 flat options (`B0: Sequential FIFO` through `B7: HEFT Family`) and an interactive floating hover preview tooltip explaining each policy on mouseover.
     - Keep `Preset configuration` and `Profile configuration` text inputs with `[Browse]` buttons.
     - Keep `[✓] Start safely then scale up (Warm-up mode)` checkbox.
     - Ensure each field label includes `<InfoTooltip content="..." />`.
2. **Frontend Form State & Request Builder:**
   - `tauri-app/src/api/runConfig.ts`:
     - Add `neuroflowPolicy?: string` to `PipelineFormValues` (default: `'B6'`).
     - In `buildRunConfig()`, map `neuroflow_policy: String(formValues.neuroflowPolicy || 'B6')`.
   - `tauri-app/src/stores/pipelineFormStore.ts`:
     - Persist `neuroflow_policy` when saving/loading workspace configs.
3. **Backend Request Validation:**
   - `app_backend/run_request.py`:
     - Add `neuroflow_policy: str = 'B6'` to `RunRequestInput` / validation schema.
4. **Backend Scheduler Adapter:**
   - `pipeline/neuroflow_adapter.py`:
     - In `_scheduler_config(req)`:
       - Read `policy_id = str(req.get("neuroflow_policy", "B6")).strip()`.
       - Pass resolved `policy = {"name": policy_id, "algorithm_version": "1.0.0"}` (or `"neuroflow"` if B6).
       - Maintain safe production defaults for all hidden parameters (`max_retries=3`, `preserve_oom=True`, `estimation_mode="balanced"`, `max_io_tasks=2`).
5. **Tests:**
   - `tests/test_neuroflow_adapter.py`:
     - Verify `_scheduler_config()` parses `neuroflow_policy` and sets policy name correctly.
   - `tauri-app/test/AppHeader.test.tsx` and `tauri-app/test/workspaceRunConfig.test.ts`:
     - Update workspace persistence tests to match updated form fields.

---

## Detailed Step-by-Step Implementation

### Step 1: Update Frontend Types & Form Store
- In `tauri-app/src/api/runConfig.ts`:
  - Add `neuroflowPolicy?: string;` to `PipelineFormValues`.
  - Set `neuroflowPolicy: 'B6'` in `DEFAULT_FORM_VALUES`.
  - In `buildRunConfig()`:
    - Pass `neuroflow_policy: String(formValues.neuroflowPolicy || 'B6')`.
- In `tauri-app/src/stores/pipelineFormStore.ts`:
  - Load `workspace.neuroflow_policy` into `nextFormValues.neuroflowPolicy` (defaulting to `'B6'`).

### Step 2: Redesign `Advanced Settings` in `PipelinePage.tsx`
- Define the metadata dictionary for the 8 policies:
  ```typescript
  const NEUROFLOW_POLICIES = [
    { id: 'B0', label: 'B0: Sequential FIFO', desc: 'Chạy lần lượt từng tác vụ đơn luồng theo thứ tự nạp vào (cho máy cấu hình rất yếu).' },
    { id: 'B1', label: 'B1: Parallel FIFO First-Fit', desc: 'Chạy song song theo thứ tự nạp ảnh, vừa tài nguyên trống thì chạy trước.' },
    { id: 'B2', label: 'B2: Shortest Processing Time First-Fit', desc: 'Ưu tiên các tác vụ có thời gian chạy ngắn nhất để giải phóng hàng đợi nhanh nhất.' },
    { id: 'B3', label: 'B3: Static Critical-Path First-Fit', desc: 'Ưu tiên các tác vụ nằm trên đường găng dài nhất dựa theo hồ sơ tĩnh ban đầu.' },
    { id: 'B4', label: 'B4: Static Critical-Path Protected Backfill', desc: 'Ưu tiên đường găng tĩnh, cho phép tác vụ nhẹ chen ngang mà không làm trễ tác vụ chính.' },
    { id: 'B5', label: 'B5: Adaptive FIFO Resource Scheduler', desc: 'Thứ tự nạp trước chạy trước (FIFO) kết hợp tự động ước lượng và co giãn RAM/CPU.' },
    { id: 'B6', label: 'B6: Full NeuroFLOW', desc: 'Tối ưu đường găng động, tự thích ứng tài nguyên, chống đói và chen ngang thông minh (Mặc định).' },
    { id: 'B7', label: 'B7: HEFT Family', desc: 'Lập lịch theo thời gian hoàn thành sớm nhất cho hệ thống đa phần cứng (CPU & GPU).' },
  ];
  ```
- Build a custom hover tooltip / popover for policy items when hovering in the dropdown.
- Render the 2x2 grid:
  - **Row 1:** `Max parallel tasks` (with `<InfoTooltip />`) & `Policy` (with `<InfoTooltip />` and hover popover).
  - **Row 2:** `Preset configuration` (input + Browse + `<InfoTooltip />`) & `Profile configuration` (input + Browse + `<InfoTooltip />`).
  - **Row 3:** `[✓] Start safely then scale up (Warm-up mode)` with `<InfoTooltip />`.

### Step 3: Update Backend Request Handler & Adapter
- In `app_backend/run_request.py`:
  - Support `neuroflow_policy: str = 'B6'` in request validation and payload normalization.
- In `pipeline/neuroflow_adapter.py`:
  - In `_scheduler_config(req)`:
    - Extract `policy_choice = str(req.get("neuroflow_policy", "B6")).strip()`
    - Configure policy object: `{"name": "neuroflow" if policy_choice in ("B6", "neuroflow") else policy_choice, "algorithm_version": "1"}`.

### Step 4: Verification & Testing
- Run backend pytest:
  ```bash
  pytest tests/test_neuroflow_adapter.py
  ```
- Run frontend vitest:
  ```bash
  npm run test --prefix tauri-app
  ```
- Check build syntax and TypeScript typing across the project.
