# Server Image Download And Tools UI Redesign

## Goal

Implement server-aware Docker image downloads and redesign the Tools Configuration page using the provided mock as layout reference while following `DESIGN.md` tokens/principles.

User-approved behavior:

- When runtime target is `Server`, `Download Image` downloads the Docker image on the connected server, not locally.
- Server downloads continue in the background if the GUI is closed.
- Server pull tracking is host-level and stored under `/tmp`, not under a selected workspace.
- Reopening the GUI and connecting to the same server should detect active pulls and render those cards as downloading instead of allowing duplicate pulls.
- Clicking `Download Image` for an already-running server pull should be idempotent: return/attach to the existing pull status, not start another pull.
- Redesign the Tools Configuration page based on the supplied mock image, especially the distinct card layout for `Available Images` versus `Not Available`.

## Existing Context

- `tauri-app/src/pages/ToolsPage.tsx`
  - Already auto-loads all Docker images by calling `/tools/local/images` with `{}` selected tools.
  - Currently `handleDownload` always calls `usePullImageStream().pull(image)`.
  - Current download endpoint is local-only.
- `tauri-app/src/query/useTools.ts`
  - `usePullImageStream()` fetches `/tools/local/pull` and assumes one local SSE stream.
- `tauri-app/src/components/ImageCard.tsx`
  - One card component currently serves both installed and missing images; mock requires different layouts.
- `app_backend/server.py`
  - `/tools/local/images` already supports `target` and `remote` for server image status.
  - `/tools/local/pull` only runs local `docker pull` in the request/SSE handler.
- `app_backend/tools.py`
  - `LocalToolService.image_status(... target='Server')` uses `RemoteRunner.check_image_statuses()`.
- `remote/remote_runner.py`
  - Has `check_image_statuses`, `check_image_details`, and `remove_images` using `RemoteSSHClient`.
  - Has direct SSH primitives via `ssh.run()` and `ssh.read_text()`.
- `DESIGN.md`
  - Use warm cream canvas, white cards, hairline borders, no shadows.
  - Use Sea Blue sparingly for primary CTAs.
  - Use semantic success/error for status.
  - Avoid using timeline pastel colors as general system colors.

## Backend Plan: Server Pull Tracking In `/tmp`

### Tracking Location

Use this directory on the target host:

```text
/tmp/neuroflow-image-pulls
```

For each image, derive a stable key with SHA-256 of the exact image string:

```text
/tmp/neuroflow-image-pulls/<sha256>.json
/tmp/neuroflow-image-pulls/<sha256>.log
```

Do not store SSH config, passwords, key paths, or workspace paths in these files. Store only host-level image pull state.

Suggested JSON fields:

```json
{
  "image": "mkdayyyy/mri-fs7-all:latest",
  "status": "pulling",
  "pid": 12345,
  "started_at": 1720000000,
  "updated_at": 1720000030,
  "exit_code": null,
  "error": null,
  "log_path": "/tmp/neuroflow-image-pulls/<sha256>.log"
}
```

Statuses:

- `pulling`
- `success`
- `failed`
- `stale`
- `missing` only as computed API status, not necessarily persisted

### Remote Runner Additions

Add methods to `remote/remote_runner.py` or a small helper module used by `RemoteRunner`:

- `image_pull_key(image: str) -> str`
- `remote_pull_paths(image: str) -> dict[str, str]`
- `remote_image_pull_status(image: str) -> dict[str, object]`
- `start_remote_image_pull(image: str) -> dict[str, object]`
- Optionally `check_image_states(images: list[str]) -> dict[str, dict[str, object]]`

Implementation rules:

- Always run `docker image inspect <image>` first; installed image state is the source of truth.
- If installed, return `status='installed'` regardless of stale tracking files.
- If not installed, read `/tmp/neuroflow-image-pulls/<key>.json` if it exists.
- If JSON says `pulling`, validate it before trusting it:
  - `kill -0 <pid>` must succeed.
  - `ps -p <pid> -o args=` should contain a unique marker such as `neuroflow-image-pull-<key>`.
- If validation succeeds, return `status='pulling'`.
- If validation fails, return `status='stale'` or `status='failed'` depending on the persisted exit/error, and allow retry.
- If the track file is missing, return `status='missing'`.

Start command requirements:

- Start the remote pull detached from the SSH request so closing the GUI or closing the HTTP/SSE stream does not cancel it.
- Use `nohup` or `setsid` with a shell wrapper.
- Include the unique marker in the process args for PID validation.
- Write logs to the `.log` path.
- Write JSON atomically when possible: write to `*.tmp` and `mv` into place.
- Quote image names with `shlex.quote` in Python when building shell commands.

Suggested shape, not exact code:

```sh
mkdir -p /tmp/neuroflow-image-pulls
chmod 1777 /tmp/neuroflow-image-pulls || true
nohup sh -c '
  pid=$$
  started=$(date +%s)
  write_json pulling "$pid" "$started" null null
  docker pull "$IMAGE" >> "$LOG" 2>&1
  code=$?
  updated=$(date +%s)
  if [ "$code" -eq 0 ]; then
    write_json success "$pid" "$started" "$updated" null
  else
    write_json failed "$pid" "$started" "$updated" "Pull failed (exit $code)"
  fi
' neuroflow-image-pull-<key> >/dev/null 2>&1 &
```

The actual implementation can use a generated shell script uploaded/written to `/tmp/neuroflow-image-pulls/<key>.sh` if that is cleaner and safer than deeply nested shell quoting.

### Service/API Changes

Update `app_backend/tools.py`:

- Add a target-aware pull method, for example:
  - `pull_image(image: str, target: str = 'Local', remote: dict[str, object] | None = None) -> dict[str, JsonValue]`
- For `Local`, preserve current local pull behavior or delegate to existing code.
- For `Server`:
  - Parse/validate remote config with `parse_remote_config`.
  - Instantiate `RemoteRunner`.
  - If image installed, return `{ok: true, target: 'Server', image, status: 'installed'}`.
  - If active pull exists, return `{ok: true, target: 'Server', image, status: 'pulling', already_running: true}`.
  - Otherwise start detached pull and return `{ok: true, target: 'Server', image, status: 'pulling', already_running: false, pid}`.

Update `LocalToolService.image_status(... target='Server')`:

- Prefer a new `RemoteRunner.check_image_states(images)` if added.
- Returned `ToolImage` entries should support these status strings:
  - `Installed`
  - `Missing`
  - `Downloading`
  - optionally `Failed`
- Add optional fields when available:
  - `pull_status`
  - `pull_started_at`
  - `pull_updated_at`
  - `pull_pid`
  - `pull_error`
  - `pull_log_tail`
- If `docker image inspect` succeeds, status must be `Installed` even if the track file says `success` or `pulling`.
- If missing and validated active pull exists, status should be `Downloading` and `pull_status='pulling'`.
- If missing and stale/failed track exists, status should remain `Missing` or `Failed`; keep it in the not-available section and allow retry.

Update `app_backend/server.py`:

- Extend `/tools/local/pull` payload validation to accept:
  - `image`
  - `target`, default `Local`
  - `remote`, object required for `Server`
- Preserve local SSE behavior for `Local` if feasible.
- For `Server`, respond quickly after starting/attaching to the detached pull. It can still use SSE for frontend consistency:
  - `step`: `Server pull is running for <image>`
  - `complete`: `{ok: true, target: 'Server', image, status: 'pulling', already_running: boolean}`
- Do not stream the whole remote pull through the HTTP request for server target; the point is durability after GUI close.

If same endpoint with mixed local/server behavior becomes awkward, add a new endpoint such as `/tools/pull` and update the frontend to use it. Keep `/tools/local/pull` backward-compatible if any current code still calls it.

### Type/API Schema Changes

Update `tauri-app/src/api/schemas.ts`:

- Extend `toolImageSchema` with optional pull fields listed above.
- Extend `pullImageResponseSchema` to include `target`, `image`, `status`, `already_running`, and `pid` optional fields.

Update `tauri-app/src/types/backend.ts` through schema inference only.

Update `tauri-app/src/api/client.ts`:

- Make `pullImage` accept options:
  - `pullImage(image: string, {target = 'Local', remote = null} = {})`
- If `usePullImageStream` continues to use raw `fetch`, keep `BackendClient.pullImage` consistent anyway.

## Frontend Behavior Plan

### Pull Hook

Update `tauri-app/src/query/useTools.ts`:

- Update `usePullImageStream().pull` to accept `{target, remote}`.
- POST `{image, target, remote}`.
- Set state to `pulling` immediately before the fetch, not only after logs arrive.
- Track the active image name in state, e.g. `image: string | null`, so only that image card is disabled for local in-flight pulls.
- For server target, when the SSE `complete` returns `status='pulling'`, keep local hook state as `pulling` briefly or set a `started`/`success` state and rely on the next image-status refresh to show `Downloading`.
- After a server pull start/attach, trigger `refreshTools({manual: false})` to pick up `Downloading` status from `/tools/local/images`.

### Tools Page Target-Aware Actions

Update `tauri-app/src/pages/ToolsPage.tsx`:

- `handleDownload(image)` should use the selected runtime target.
- If target is `Server` and `remoteResult.connected` is false, show a message and do not call pull.
- If target is `Server`, pass `buildRemotePayload(formValues)`.
- After download start/attach, refresh images in the background so cards show `Downloading`.
- Add a polling effect while any current image has `status === 'Downloading'` or `pull_status === 'pulling'`:
  - Poll every 4-6 seconds.
  - Stop polling when no image is downloading or component unmounts.
  - Use `refreshTools({manual: false})`.
- Ensure duplicate Download clicks are blocked for cards where `pull_status === 'pulling'` even after GUI reopen.
- Keep local downloads working as before, but fix the short gap by disabling the clicked button as soon as `pull()` starts.

Important safety note:

- Current `Remove Image` is also local-only. In this plan, either:
  - make remove target-aware using `RemoteRunner.remove_images` for `Server`, or
  - disable/hide `Remove Image` when target is `Server` with a clear tooltip/message.
- Do not leave a server-visible installed card wired to local removal.

## UI Redesign Plan

Use the mock as the primary layout reference, and `DESIGN.md` for actual tokens and product style. The mock uses a white/blue SaaS look; adapt it to NeuroFlow’s warm cream canvas, white cards, hairline borders, sparse Sea Blue CTAs, and no shadows.

### Overall Page Layout

Files likely touched:

- `tauri-app/src/pages/ToolsPage.tsx`
- `tauri-app/src/components/ImageCard.tsx`
- Optionally split into:
  - `tauri-app/src/components/ToolImageCard.tsx`
  - `tauri-app/src/components/ToolEnvironmentCard.tsx`

Recommended structure:

- Page wrapper: warm cream/canvas, full height scroll, more horizontal breathing room.
- Top section: `Environment` header with icon on the left and `Check Environment` primary button on the right.
- Environment cards: three horizontal cards in a responsive grid:
  - Runtime Target
  - Python
  - Docker
- Section header row for `Available Images`:
  - Green/success check icon.
  - Count pill.
  - `Refresh` button aligned right, as in mock.
- `Available Images` grid:
  - Desktop: 3 columns if width allows.
  - Tablet: 2 columns.
  - Mobile: 1 column.
- Section header row for `Not Available`:
  - Error/warning icon.
  - Count pill.
- `Not Available` grid:
  - Desktop/wide: 4-5 compact columns if width allows.
  - Tablet: 2-3 columns.
  - Mobile: 1 column.

### Environment Cards

Match mock layout:

- Large left icon tile.
- Uppercase label (`RUNTIME TARGET`, `PYTHON`, `DOCKER`).
- Status pill and secondary text on one row.
- Use `StatusPill` or a refined variant.
- Use semantic success for `READY`, semantic error for missing.
- Do not use timeline pastel colors for general icon tiles; prefer subtle Sea Blue tint, neutral tint, or semantic tints.

### Available Image Card Layout

Make available cards visually similar to the mock:

- Larger horizontal card, white surface, `rounded-lg`/`rounded-xl`, 1px hairline, no shadow.
- Top row:
  - Docker/container icon tile on the left.
  - Repository/name and tag pill in the middle.
  - `INSTALLED` status pill top-right.
- Body:
  - Display description from tool details if available; if no description exists, use a compact label like `Docker image for N tools`.
  - Metadata row: target (`Local` or `Remote`), status, repo size, uncompressed size.
  - Tool chips wrapping into multiple rows.
- Bottom/right action:
  - Red outline `Remove` button with trash icon.
  - For `Server`, only show enabled remove if target-aware server remove is implemented; otherwise disable/hide as noted above.

### Not Available Card Layout

Make missing cards distinct and compact like the mock:

- Smaller vertical card.
- Top row:
  - Red-tinted Docker/container icon tile.
  - Repository/name and tag.
  - Status pill: `MISSING`, `DOWNLOADING`, or `FAILED`.
- Compact description line.
- Metadata row: target (`Local`/`Remote`), missing/downloading, repo size if known.
- Tool chips, but cap visible chips to avoid overly tall cards. Show `+N more` chip when needed.
- Bottom full-width action button:
  - `Download Image` with download icon.
  - `Downloading...` with spinner when `pull_status='pulling'` or active frontend pull image matches.
  - `Retry Download` when `pull_status='failed'` or status is `Failed`.
- Preserve accessibility with disabled states and explicit text.

### Status Classification Helpers

Update/create helpers in `tauri-app/src/lib/tools.ts`:

- `isImageInstalled(image)` remains true only for `Installed`/installed booleans.
- Add `isImageDownloading(image)` for `status === 'Downloading' || pull_status === 'pulling'`.
- Add `isImageFailed(image)` if using `Failed`.
- Add `imageDisplayParts(image.image)` to parse repo/tag safely if helpful.

## Tests

Backend tests:

- Add/extend `tests/test_app_backend_tools.py`:
  - Server `image_status` marks a missing image as `Downloading` when fake remote runner reports active pull.
  - Server `pull_image` returns `already_running: true` and does not start duplicate when active tracking exists.
  - Server `pull_image` starts a pull and returns `status='pulling'` when missing and no active tracking exists.
  - Installed image status wins over stale/pulling track file.
- Add/extend `tests/test_app_backend_server.py`:
  - `/tools/local/pull` accepts `{target: 'Server', image, remote}` and delegates to tool service with remote payload.

Frontend tests:

- Update `tauri-app/test/tools.test.ts` or add a focused test if the current file is repaired:
  - `isImageDownloading` returns true for `Downloading`/`pulling`.
  - image parsing/tag helper handles images with and without explicit tags.
- If there is an existing React Testing Library pattern, add a small card test:
  - Not-available card with `pull_status='pulling'` renders `Downloading...` and disabled button.
  - Available card uses the available layout and remove action.

Known issue from prior executor run:

- `tauri-app/test/tools.test.ts` currently has pre-existing failures because it references functions missing from `src/lib/tools.ts`. If not fixed in this task, report that as pre-existing. If adding helpers to `lib/tools.ts`, consider restoring the missing helpers if it is small and unblocks tests.

## Verification

From repo root:

```bash
pytest tests/test_app_backend_tools.py tests/test_app_backend_server.py
```

From `tauri-app`:

```bash
npm run typecheck
npm run test -- tools
```

If feasible after fixing pre-existing frontend test issues:

```bash
npm run test
```

Manual verification:

- Connect to server successfully.
- Open Tools Configuration with runtime target `Server`.
- Click `Download Image` on a missing server image.
- Confirm card changes to `Downloading...`.
- Close GUI while remote pull is running.
- Reopen GUI, connect to same server.
- Confirm the same image is detected as `Downloading...` from `/tmp/neuroflow-image-pulls/<sha>.json` and the button is disabled.
- After pull completes, confirm auto/background refresh moves image to `Available Images`.
- Click Download again for a known active pull and confirm no duplicate remote pull is started.

## Non-Goals

- Do not store tracking in the selected server workspace.
- Do not store secrets in `/tmp` tracking files.
- Do not make `/tmp` tracking the source of truth for installed images; Docker inspect remains the source of truth.
- Do not redesign the app sidebar unless absolutely necessary; the mock is page-layout inspiration, not a request to rebuild the whole shell.
