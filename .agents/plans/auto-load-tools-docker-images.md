# Auto Load Tools Docker Images

## Goal

On the Tools Configuration page, users should see Docker image availability without having to click `Refresh` first.

Required behavior:

- Load all Docker images by default, not only images for the currently selected preset/custom pipeline tools.
- For `Local`, begin checking image status automatically when the Tools page opens or when the runtime target changes back to local.
- For `Server`, do not block the SSH connect flow. Once SSH connects successfully (`remoteResult.connected === true`), lazily kick off the server Docker image status check in the background.
- Keep the manual `Refresh` button as an explicit retry, but the empty state must not tell the user to click it before any automatic check has run.

## Relevant Existing Code

- `tauri-app/src/pages/ToolsPage.tsx`
  - Contains the current `refreshTools` function and UI text.
  - Uses `useToolsStore.latestImages` as the rendered source of truth.
  - Currently builds `selectedTools` from `metadata`/form selections, then calls `localImageStatusMutation.mutateAsync` only when the user clicks `Refresh`.
  - Blocks server checks if `target === 'Server' && !remoteResult.connected`.
- `tauri-app/src/stores/toolsStore.ts`
  - Only stores `latestImages`; no loading metadata.
- `tauri-app/src/components/RuntimeSection.tsx`
  - Sets `remoteResult.connected` to `true` after successful SSH validation.
- `tauri-app/src/api/client.ts`
  - `BackendClient.localImageStatus(selectedTools, options)` posts to `/tools/local/images`.
- `app_backend/tools.py`
  - `_image_tools(selected_tools)` uses all `TOOL_DEFS` when `selected_tools` is empty or omitted, so no backend change is needed for “all docker images.”

## Implementation Plan

1. Update `tauri-app/src/pages/ToolsPage.tsx` imports.
   - Replace `useState` import with `useCallback`, `useEffect`, `useMemo`, `useRef`, and `useState` as needed.

2. Stop deriving image status checks from selected pipeline tools.
   - Remove the metadata-only usage for image refresh, unless still used elsewhere in the component.
   - In `refreshTools`, pass an empty object as `selectedTools`, e.g. `const selectedTools: Record<string, string> = {};`.
   - This causes the backend to return all Docker images via existing `app_backend/tools.py` behavior.

3. Make `refreshTools` reusable for auto/background checks.
   - Wrap it in `useCallback` with dependencies on `formValues`, `remoteResult.connected`, `localImageStatusMutation`, `setBusyKey`, and `setLatestImages`.
   - Add an optional parameter such as `{manual?: boolean}`.
   - For server when not connected:
     - If manual, set `Connect SSH before checking server Docker images.`.
     - If automatic, silently return.
   - Set `busy.refreshTools` during both automatic and manual checks so the existing spinner/button reflects background work.
   - Use `buildRemotePayload(formValues)` only for `Server`.
   - On success, preserve the existing `setLatestImages(imgs)` behavior and update the message to mention all images, e.g. `Found ${imgs.length} Docker images ...`.
   - On failure, keep current error handling.

4. Auto-trigger checks from `ToolsPage`.
   - Add a `useEffect` that runs when the effective runtime target changes and when `remoteResult.connected` changes.
   - For local target, call `refreshTools({manual: false})` on page mount.
   - For server target, call `refreshTools({manual: false})` only after `remoteResult.connected` is true.
   - Avoid duplicate calls in React StrictMode and repeated rerenders by tracking a request key in a `useRef`.
   - Recommended key shape: `${target}:${target === 'Server' ? remoteResult.config host/port/username/workspace or buildRemotePayload fields : 'local'}`.
   - Reset naturally when the target or server config changes so a new server connection can trigger a fresh background check.
   - Do not auto-run server checks while disconnected.

5. Avoid stale local/server image lists.
   - Because `latestImages` is global and not keyed by target, clear or replace it when switching target before the new automatic status check completes.
   - Minimal option: in the auto-effect, when the request key changes and before calling `refreshTools`, call `setLatestImages([])` and set a neutral loading message like `Checking ${target} Docker images...`.
   - This prevents local statuses from appearing under the server target while the server check is pending.

6. Update empty-state copy.
   - Replace both `Click "Refresh" to check Docker image status.` messages.
   - Suggested text while no images have loaded: `Checking Docker image status...` when `busy.refreshTools` is true.
   - Suggested text when no images have loaded and not busy:
     - Local: `Docker image status will load automatically.`
     - Server disconnected: `Connect SSH to load server Docker image status.`
     - Server connected but failed/empty: keep the `refreshMessage` error/status visible and use `No Docker image status is available yet.`
   - The important requirement is that initial UI must not instruct users to click `Refresh` as the primary path.

7. Keep manual `Refresh`.
   - Update `onClick={refreshTools}` to `onClick={() => void refreshTools({manual: true})}`.
   - Keep disabled state based on `busy.refreshTools`.

8. Add tests if the existing test setup supports page rendering.
   - Search existing React tests first. If there are page-level tests, add a `ToolsPage` test that mocks the image status mutation/client and verifies a status call is made on render with `{}` selected tools.
   - Add or adapt a test for server behavior if straightforward: with `runtimeTarget: 'Server'` and `remoteResult.connected: true`, verify the automatic call includes `target: 'Server'` and a remote payload.
   - If page testing is not practical in this codebase, add a small extracted helper only if it remains minimal; otherwise rely on typecheck and existing unit tests.

## Verification

Run these from `tauri-app`:

```bash
npm run typecheck
npm run test
```

If tests are slow or environment-limited, at minimum run:

```bash
npm run typecheck
npm run test -- tools
```

## Notes And Constraints

- Do not add a backend endpoint; the backend already returns all images for empty `selected_tools`.
- Do not move this behavior into the SSH connect button unless necessary. The requested lazy background behavior is naturally driven by `remoteResult.connected` in `ToolsPage`.
- Preserve existing Zustand stores unless a minimal status flag is clearly needed.
- Keep the change localized; likely only `ToolsPage.tsx` and tests need edits.
