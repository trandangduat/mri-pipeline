# Runtime GPU Detection And Toggle

## Goal

Put RAM and CPU inputs on the same row in the Runtime panel, probe GPU presence automatically when a runtime target becomes available (Server connect or Local environment load), show GPU info plus a binary On/Off GPU toggle only when GPUs exist, and remove the `auto` gpuMode everywhere.

## User-Visible Requirements

- RAM allocation (%) and CPU threads inputs sit side-by-side on one row of the Core Compute Grid.
- Selecting `Server` and pressing Connect probes the server for NVIDIA GPUs; if present, GPU info (name, VRAM total/free) appears next to the resource inputs together with an Enable/Disable GPU toggle.
- If no GPU is detected, the entire GPU section is hidden (no toggle, no placeholder).
- The Local runtime target gets the same GPU probe from `/environment/local`, so the UI behaves identically for both targets.
- GPU mode is binary On/Off only. No "Auto" option exists anywhere; On maps to backend `device: cuda`, Off to `device: cpu`.
- Old workspaces saved with `device: cuda` load as On; everything else loads as Off.

## Investigation Summary

All line numbers verified against current code.

- Grid: `tauri-app/src/components/RuntimeSection.tsx` — `<div className="grid gap-2.5 grid-cols-2">` at line 138; cells: Runtime target select 139–167, RAM % 168–184, CPU threads 185–201, GPU select Auto/Enabled/Disabled 202–214. Warnings block 218–230 uses `runtimeWarnings` computed at 128–133 from `currentTargetHardware` (127).
- Connect flow: `connectRemote()` RuntimeSection.tsx:96–108 → POST `/remote/validate` (`app_backend/server.py:167–168`) → `RemoteJobService.validate_config` (`app_backend/remote.py:42–76`, hardware call at line 60) → `RemoteRunner.remote_hardware_info` (`remote/remote_runner.py:187–210`, single SSH round-trip via `ssh.read_text`, key=value parsing at 197–201). Result lands in zustand `remoteStore.hardware` (`tauri-app/src/stores/remoteStore.ts:4–22`) through `renderRemoteResult` (RuntimeSection.tsx:48–92); disconnect resets `hardware: null`.
- GPU enforcement already end-to-end (do not redesign): `device` → `pipeline/neuroflow_adapter._gpu_resources` (136–171; runs local `nvidia-smi --query-gpu=memory.free,memory.total,name --format=csv,noheader,nounits` at 142–147) → scheduler limits `gpus` list (205–221, also line 301); `pipeline/runner.py:201` sets `gpus=(config.device == "gpu" or config.device == "cuda")`; `pipeline/executor.py:33` + 93–94 add `--gpus all`. Registry tools branch on `ctx.device` (e.g. registry.py:690–693).
- No GPU probing exists today in `remote_hardware_info` (remote_runner.py:187–210), `/environment/local` (`app_backend/environment.py::_hardware_status` 40–47), or `pipeline/hardware.py::_host_info` (65–79).
- gpuMode state: type `tauri-app/src/api/runConfig.ts:13` (loose `string`), default `'auto'` :48, run payload mapping `device: gpuMode === 'enabled' ? 'cuda' : 'cpu'` :102 (note: `'auto'` silently falls back to `cpu`). Workspace save: `AppHeader.tsx:161` (same mapping). Workspace load: `stores/pipelineFormStore.ts:95` maps `cuda|gpu → 'enabled'` else `'disabled'` — legacy workspaces already store `device: cuda|cpu`, so no workspace-format migration is needed.
- Frontend schemas/types: `remoteHardwareSchema` (`src/api/schemas.ts:130–134`), `hardwareSchema` :18–23, `environmentSchema` :25–31, `remoteValidateResponseSchema` :136–144; re-exported types in `src/types/backend.ts:32–47`; `RemoteResultState` backend.ts:63–71; `TargetHardware` `src/lib/runtime.ts:9–14` with `currentTargetHardware` 16–45 and `runtimeWarnings` 47–71.
- Tests: `tests/test_app_backend_remote.py` FakeRunner returns hardware without `gpus` (:20–21) and `test_validate_remote_config_connects_and_redacts_secrets` asserts the exact response dict (:58–70). `tests/test_remote_runner.py` mocks SSH via mocker/dummy_ssh fixtures. `tests/test_app_backend_environment.py` covers `LocalEnvironmentService.status`. Frontend has vitest configured (`tauri-app/package.json`: `"test": "vitest run"`, `"typecheck": "tsc --noEmit"`) with an existing suite (`tauri-app/test/`: `runtime.test.ts` already exercises `currentTargetHardware`, plus `AppHeader.test.tsx`, `uiClasses.test.ts`, etc.) — extend, don't create from scratch.
- DESIGN.md: defines `button-primary` / `button-secondary` / `badge-pill` conventions (Sections "Buttons", "Forms & Tags"); no switch or segmented-control component is defined, so a compact two-segment pill pair built from existing Button variants is the convention-consistent choice.

## Implementation Plan

### 1. Server-side GPU probe in `remote_hardware_info`

Update `remote/remote_runner.py::remote_hardware_info` (187–210):

- Append one more shell fragment to the existing single `ssh.read_text(...)` command so no extra round-trip is added:

```python
code, text = ssh.read_text(
    "printf 'hostname='; hostname; "
    "printf '\nlogical_cores='; getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || printf 0; "
    "printf '\nphys_pages='; getconf _PHYS_PAGES 2>/dev/null || printf 0; "
    "printf '\npage_size='; getconf PAGE_SIZE 2>/dev/null || printf 0; "
    "printf '\ngpus='; nvidia-smi --query-gpu=memory.free,memory.total,name "
    "--format=csv,noheader,nounits 2>/dev/null | tr '\n' '|'; printf '\n';"
)
```

- Parse `gpus=` after the existing key=value loop. Each segment split on `|`, then each row split on `,` into `(free_mib, total_mib, name)` — same field order as `neuroflow_adapter._gpu_resources` (free,total,name) for consistency. Non-integer or missing rows are skipped.
- Graceful absence handling:
  - `nvidia-smi` not installed ⇒ shell emits nothing between `gpus=` and the newline ⇒ `gpus == []` (command-not-found ⇒ no GPU).
  - `ssh.read_text` non-zero exit code ⇒ return the existing degraded dict plus `"gpus": []`.
- New return shape (additive, optional key):

```python
{
    "hostname": str,
    "logical_cores": int | None,
    "total_ram_bytes": int | None,
    "gpus": [ {"name": str, "total_memory_mib": int, "free_memory_mib": int}, ... ],  # [] when absent
}
```

- Add a module-level parser `_parse_gpu_rows(raw: str) -> list[dict[str, object]]` so it is unit-testable without SSH.

### 2. Pass GPUs through `_hardware_summary`

Update `app_backend/remote.py::_hardware_summary` (844–849):

```python
def _hardware_summary(hardware: dict[str, object]) -> dict[str, JsonValue]:
    gpus = hardware.get("gpus")
    summary: dict[str, JsonValue] = {
        "hostname": str(hardware.get("hostname", "") or ""),
        "logical_cores": _int_or_none(hardware.get("logical_cores")),
        "total_ram_bytes": _int_or_none(hardware.get("total_ram_bytes")),
    }
    if isinstance(gpus, list):
        summary["gpus"] = [
            {
                "name": str(g.get("name", "")),
                "total_memory_mib": _int_or_none(g.get("total_memory_mib")),
                "free_memory_mib": _int_or_none(g.get("free_memory_mib")),
            }
            for g in gpus if isinstance(g, dict)
        ]
    return summary
```

Key stays optional so fake runners in tests that omit `gpus` keep working; `validate_config` itself needs no change (line 60 already passes the whole dict).

### 3. Local GPU probe for `/environment/local`

Add to `pipeline/hardware.py`:

```python
def _gpu_info() -> list[dict]:
    import subprocess
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free,memory.total,name",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    gpus = []
    for index, line in enumerate(result.stdout.splitlines()):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            free_mib, total_mib = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        gpus.append({
            "name": parts[2] if len(parts) > 2 else f"gpu_{index}",
            "total_memory_mib": total_mib,
            "free_memory_mib": free_mib,
        })
    return gpus
```

Then in `app_backend/environment.py::_hardware_status` (40–47) add `"gpus": _gpu_info(),` to the returned dict. This intentionally mirrors (not refactors) `neuroflow_adapter._gpu_resources` — see Risks.

### 4. Frontend schema/type updates

`tauri-app/src/api/schemas.ts`:

```ts
export const gpuInfoSchema = z.object({
  name: z.string(),
  total_memory_mib: z.number().nullable(),
  free_memory_mib: z.number().nullable(),
});

// hardwareSchema (18–23): add
gpus: z.array(gpuInfoSchema).optional(),

// remoteHardwareSchema (130–134): add
gpus: z.array(gpuInfoSchema).optional(),
```

Both stay optional so older backends (no `gpus` key) still validate.

`src/lib/runtime.ts::TargetHardware` (9–14):

```ts
export interface TargetHardware {
  label: RuntimeTarget;
  connected: boolean;
  logicalCores: number | null;
  totalRamBytes: number | null;
  gpus: GpuInfo[];
}
```

Extend `currentTargetHardware` (16–45): Server branch reads `remoteResult?.hardware?.gpus ?? []`; Local branch reads `hardware.gpus ?? []`. `runtimeWarnings` (47–71) is unchanged apart from this additive field.

### 5. Remove `auto` from gpuMode state

- `src/api/runConfig.ts:13`: `gpuMode: 'on' | 'off';`
- `runConfig.ts:48` default: `gpuMode: 'off'` (Off preserves today's effective behavior — old `'auto'` silently fell through to `cpu`).
- `runConfig.ts:102`: `device: formValues.gpuMode === 'on' ? 'cuda' : 'cpu',`
- `AppHeader.tsx:161` (workspace save): `device: fv.gpuMode === 'on' ? 'cuda' : 'cpu',`
- `pipelineFormStore.ts:95` (workspace load): `nextFormValues.gpuMode = workspace.device === 'cuda' || workspace.device === 'gpu' ? 'on' : 'off';`
- Legacy migration: saved workspaces already persist `device: cuda|cpu` (never `'auto'`), so every legacy file maps cleanly; anything unexpected maps to `'off'`, matching the pre-change default. No version bump required.
- Grep-check afterwards: no remaining occurrences of `'auto'` tied to `gpuMode` anywhere under `tauri-app/src`.

### 6. UI: grid reorder + conditional GPU section

Rewrite the Core Compute Grid in `RuntimeSection.tsx` (138–215):

- Row 1: Runtime target label gets `col-span-2` (it currently wastes half a cell next to RAM).
- Row 2: RAM (%) then CPU threads — adjacent, satisfying "same row".
- GPU block: rendered ONLY when `hardware.gpus.length > 0`, as a `col-span-2` sub-card below the grid (before Warnings), showing per-GPU name + VRAM (`formatBytes(total_memory_mib * 1024 * 1024)` total / free) and an Off/On segmented control:

```tsx
{hardware.gpus.length > 0 && (
  <div className="col-span-2 rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3">
    <div className="mb-2 flex items-center justify-between text-xs font-semibold text-cursor-ink">
      <span>GPU acceleration</span>
      <div className="inline-flex overflow-hidden rounded-md border border-cursor-hairline-strong">
        {(['off', 'on'] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            onClick={() => setFormField('gpuMode', mode)}
            className={`px-3 py-1 text-xs font-medium ${
              formValues.gpuMode === mode
                ? 'bg-cursor-primary text-white'
                : 'bg-cursor-surface-card text-cursor-muted'
            }`}
          >
            {mode === 'on' ? 'On' : 'Off'}
          </button>
        ))}
      </div>
    </div>
    {hardware.gpus.map((gpu, i) => (
      <div key={i} className="text-2xs text-cursor-muted">
        {gpu.name} — {formatBytes((gpu.total_memory_mib || 0) * 1024 * 1024)} VRAM
        ({formatBytes((gpu.free_memory_mib || 0) * 1024 * 1024)} free)
      </div>
    ))}
  </div>
)}
```

Segmented control justification: DESIGN.md defines `button-primary` (active segment) vs `button-secondary` styling and `badge-pill`, but no switch component; a two-segment pill pair reuses those tokens exactly and matches the compact grid density better than a native checkbox-style switch.

Disconnected behavior decision: **hide while disconnected**. For Server target, `remoteStore` resets `hardware: null` on failed/unconfirmed connect (RuntimeSection.tsx:58–82), so `currentTargetHardware` yields `gpus: []` and the section hides automatically — stale GPU claims are never shown for a host we cannot reach, and Connect completes in seconds so hiding costs nothing. For Local target the probe rides the existing `useEnvironment()` query, so the section appears as soon as `/environment/local` responds.

Also update the connected summary line (RuntimeSection.tsx:358) to append `, N GPU(s)` when `remoteResult.hardware?.gpus?.length`.

### 7. Warnings integration

No behavioral change to `runtimeWarnings` (lib/runtime.ts:47–71). Only the additive `gpus` field on `TargetHardware` (step 4). Optionally, later follow-up (out of scope here): warn when GPU is On but probe found none — impossible by construction since the toggle only renders when `gpus.length > 0`.

## Tests

Backend (pytest):

- `tests/test_remote_runner.py`: new tests mocking `RemoteSSHClient.read_text` output strings — (a) full probe text including two GPU CSV lines ⇒ parsed `gpus` list correct; (b) probe text with empty `gpus=` (nvidia-smi missing) ⇒ `gpus == []`; (c) malformed GPU rows skipped; (d) non-zero exit code ⇒ degraded dict with `gpus: []`.
- `tests/test_app_backend_remote.py`: update FakeRunner (:20–21) to include `gpus` and extend the strict assertion in `test_validate_remote_config_connects_and_redacts_secrets` (:58–70); add a case where FakeRunner omits `gpus` to prove `_hardware_summary` tolerates absence.
- `tests/test_app_backend_environment.py`: monkeypatch `pipeline.hardware._gpu_info` (or `subprocess.run`) — with GPU rows ⇒ `status()["hardware"]["gpus"]` populated; raising/FileNotFoundError ⇒ `[]`.

Frontend (vitest configured in `tauri-app/package.json`, `"test": "vitest run"`; existing suite in `tauri-app/test/`):

- Unit-test `currentTargetHardware` in the existing `tauri-app/test/runtime.test.ts` for Local/Server branches incl. `gpus` passthrough and defaults when schema fields absent.
- Schema parse tests (new `test/schemas.test.ts` or extend an existing suite) for `remoteValidateResponseSchema` with and without `gpus`.
- Run `npm run typecheck` (workdir `tauri-app/`), `npm run lint`, and `npm run test`.

Manual smoke checks:

- Local: machine with/without nvidia-smi ⇒ GPU section appears/hides; toggle persists to run payload (`device: cuda|cpu` in job config).
- Server: Connect to GPU host ⇒ section appears after connect; Disconnect/re-fail ⇒ section hides; saved workspace with `device: cuda` reloads with toggle On.

## Risks & Open Questions

- `tr '\n' '|'` inside the remote probe assumes a POSIX shell on the server (already assumed by existing `getconf`/`nproc` pipeline); verify against the dummy SSH fixture.
- Duplicated nvidia-smi parsing (new `_parse_gpu_rows`/`_gpu_info` vs `neuroflow_adapter._gpu_resources`): acceptable for now; optional follow-up could extract a shared helper, but touching the execution path adds risk out of scope for this task.
- Probing runs `nvidia-smi` on every `/environment/local` poll; confirm `useEnvironment` has adequate `staleTime` (currently default refetch behavior) or add `staleTime: 30_000` mirroring `useHealth` to avoid frequent subprocess spawns.
- Multi-GPU hosts show N rows; confirm desired UX (list all vs summarize first GPU) during implementation.
- If the backend serving `/remote/validate` is older than the frontend, `gpus` will be absent ⇒ section hidden — acceptable degradation, matches optional schema.
