# Fix Server Download Status UX

## Problem

User reports that after clicking `Download Image` for a server image, the UI shows a log/status like:

```text
mkdayyyy/mri-fs7-all:latest
Done
Server pull status for mkdayyyy/mri-fs7-all:latest
Server pull started/attached.
Dismiss
```

This is wrong because the server Docker pull is only started/attached, not completed.

User also reports that the card goes from `Downloading...` back to active `Download Image` immediately. That implies the follow-up image status refresh is not detecting the `/tmp` active pull record, or the frontend does not hold a pending server state long enough.

## Likely Root Causes Found

1. `tauri-app/src/query/useTools.ts` maps server `complete` with `data.status === 'pulling'` to frontend `status: 'success'` and appends `Server pull started/attached.`. `ToolsPage.tsx` then renders `success` as `Done`.

2. `remote/remote_runner.py` currently writes the initial JSON track file using a single-quoted heredoc:

```sh
cat > file.tmp <<'JSONEOF'
{"pid": $pid, "started_at": $started, ...}
JSONEOF
```

Because the heredoc is quoted, `$pid` and `$started` are not expanded, producing invalid JSON. Then `_check_single_image_state()` fails JSON parsing and returns `Missing`, causing the button to revert to active `Download Image` after refresh.

## Required Behavior

- Starting or attaching to a detached server pull must never render as `Done`.
- The progress/status panel should say something like `Started` or `Running in background`, not `Done`.
- The card should remain `Downloading...` immediately after clicking, even before the next refresh.
- After refresh, `/tools/local/images` for `Server` should return that image with status `Downloading` and `pull_status: 'pulling'` while the remote process is alive.
- Duplicate clicks should be blocked for active server pulls.
- `Done` should only be used when the image is actually installed, i.e. after `docker image inspect <image>` succeeds and the card moves to `Available Images`.

## Implementation Plan

### 1. Fix Remote Tracking JSON

File: `remote/remote_runner.py`

Fix `start_remote_image_pull()` shell script generation around the first JSON write.

Current initial JSON heredoc must not contain unexpanded `$pid`/`$started` inside a quoted heredoc.

Acceptable fixes:

- Use an unquoted heredoc for JSON containing shell variables, while keeping Python-provided string values pre-escaped via `json.dumps`.
- Or better, use `printf` with `%s` placeholders for shell variables.
- Or write JSON with a tiny inline Python command on the remote host if `python3` can be assumed; if not, keep POSIX shell.

Example shape:

```sh
cat > "$json.tmp" <<JSONEOF
{"image": "...", "status": "pulling", "pid": $pid, "started_at": $started, "updated_at": $started, "exit_code": null, "error": null, "log_path": "..."}
JSONEOF
mv "$json.tmp" "$json"
```

Also verify the final JSON write is valid for both success and failure.

Add/adjust tests so invalid JSON regression is caught. A unit test can inspect the generated fake remote commands or use a fake SSH client if available. At minimum add a test around state parsing behavior if command-level test is too invasive.

### 2. Do Not Convert Server `pulling` Response To `success`

File: `tauri-app/src/query/useTools.ts`

Current behavior:

```ts
if (target === 'Server' && data.status === 'pulling') {
  setState((s) => ({...s, status: 'success', logs: [...s.logs, 'Server pull started/attached.']}));
}
```

Change it so server `data.status === 'pulling'` remains a non-terminal state.

Options:

- Extend `PullStreamState.status` to include `background` or `attached`.
- Or keep `status: 'pulling'` and add a log like `Server pull is running in the background.`.

Recommended minimal path:

- Keep `status: 'pulling'` for server detached pulls.
- Add a boolean or target check in UI to label it `Running in background`.
- Do not show `Dismiss` for this state unless the card remains disabled via persisted image status. If a dismiss button is kept, it must not imply cancellation.

### 3. Update ToolsPage Pull Panel Copy

File: `tauri-app/src/pages/ToolsPage.tsx`

Change the inline pull status panel so:

- For `pullStream.target === 'Server' && pullStream.status === 'pulling'`, pill text is `Running in background` or `Downloading`.
- It must not display `Done` unless `pullStream.status === 'success'` and target is local, or unless actual image status says installed.
- The log line should say `Server pull is running in the background.` or `Attached to existing server pull.`
- Avoid repeating noisy logs every refresh. Only show logs for the explicit click/start action, not every background status refresh.

### 4. Keep The Card Disabled Immediately

Files:

- `tauri-app/src/query/useTools.ts`
- `tauri-app/src/pages/ToolsPage.tsx`
- `tauri-app/src/components/ImageCard.tsx`

Ensure `MissingImageCard` sees `downloading=true` immediately after click:

- `pullStream.status` should remain `pulling` for server background pulls.
- `pullStream.image` should remain the clicked image.
- `isFrontendPulling={pullStream.status === 'pulling' && pullStream.image === image.image}` should keep button disabled until server status refresh returns `pull_status='pulling'`.
- Do not reset `pullStream` automatically after server pull start.

### 5. Ensure Server Status Refresh Detects Pulling

Files:

- `remote/remote_runner.py`
- `app_backend/tools.py`

After fixing JSON, verify `_check_single_image_state()`:

- Missing image + valid pulling track + live marker PID returns:

```py
{
  "status": "Downloading",
  "pull_status": "pulling",
  ...
}
```

Then `LocalToolService.image_status(target='Server')` should emit `ToolImage` with:

```json
{
  "image": "...",
  "status": "Downloading",
  "pull_status": "pulling"
}
```

Frontend `isImageDownloading()` already checks this; confirm it works.

### 6. Tests

Run and/or add focused tests.

Backend:

```bash
pytest tests/test_app_backend_tools.py tests/test_app_backend_server.py
```

Frontend:

```bash
cd tauri-app
npm run typecheck
npm run test -- tools
```

If full frontend tests still fail due pre-existing missing helper tests, report clearly.

## Acceptance Criteria

- Clicking server `Download Image` never shows `Done` immediately.
- The missing image card stays disabled and labeled `Downloading...` or equivalent after click.
- Reopening/reconnecting while pull is active shows `Downloading...` based on `/tmp/neuroflow-image-pulls` state.
- `Done` appears only after image is actually installed and appears under `Available Images`.
- Invalid JSON is no longer written to `/tmp/neuroflow-image-pulls/<sha>.json`.
