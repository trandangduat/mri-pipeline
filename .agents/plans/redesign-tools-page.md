# Plan: Redesign Tools Configuration Page

## Goal

Replace the current table-based Tools page with a card-based layout organized into three distinct sections: Environment Check, Available (Installed) Images, and Not Available (Missing) Images. Each image card shows rich metadata (tag, repo size, uncompressed size) and contextual actions (Remove for installed, Download for missing).

## Current State

- **`ToolsPage.tsx`** (308 lines): Flat layout with a "Python Environment" Panel, a "Docker Images" Panel (table with checkboxes, search, bulk actions), and a "Docker Execution Log" Panel.
- **Backend** (`tools.py`): `LocalToolService.image_status()` returns `{image, status, tools[]}` per image. Does NOT return size data.
- **Backend** (`docker_ops.py`): Has `image_size_bytes(image)` and `format_image_size(size)` already available. Has `remove_image(image)` and `ensure_image(tool_key, on_progress, on_build_log)` for pull/build with streaming progress.
- **Backend** (`environment.py`): `LocalEnvironmentService.status()` returns python/docker/ssh status + hardware info.
- **API** (`server.py`): `POST /tools/local/images` checks image status. No endpoints for pull/remove/install yet.
- **Frontend schemas** (`schemas.ts`): `toolImageSchema` = `{image, status, tools[]}`. No size fields.
- **Frontend types** (`backend.ts`): `ToolImage` derived from schema.
- **Stores** (`toolsStore.ts`): Holds `imageSearch`, `imageSelection`, `imageLogText`, `toolMessage`, `latestImages`.
- **Query hooks** (`useTools.ts`): `useLocalImageStatusMutation()` for checking status.
- **Lib** (`tools.ts`): `isImageInstalled()`, `filterImages()`, selection helpers.

## Design Reference

Follow `DESIGN.md` strictly:
- Cards: `rounded-xl` (12px), 1px `border-cursor-hairline`, `bg-white`, no shadows.
- Buttons: `button-primary` (Sea Blue) for Download, `button-ghost` or danger variant for Remove.
- Status pills: use existing `StatusPill` component with `statusPillClasses()`.
- Typography: Geist Sans (CursorGothic substitute) for body, JetBrains Mono for code/tags.
- Spacing: 80px section rhythm, 24px card padding.
- Pending states: Loader2 spinner + "...ing..." label per DESIGN.md `button-pending-state`.

---

## Implementation Steps

### 1. Backend: Extend `toolImageSchema` to include size data

**File:** `app_backend/tools.py`

In `LocalToolService.image_status()`, after determining `status` for each image, call `docker image inspect --format '{{.Size}}'` to get the raw byte size. Also get the repository tag via `docker image inspect --format '{{.RepoTags}}'`.

Add to each image dict:
```python
{
    "image": image,
    "status": "Installed" | "Missing",
    "tools": [...],
    # NEW fields (only when installed):
    "repo_size": "1.2 GB",        # human-readable (use docker_ops.format_image_size)
    "uncompressed_size": "3.4 GB", # from docker inspect --format '{{.Size}}'
    "image_id": "sha256:abc...",   # short ID
}
```

For missing images, these fields should be `null` or omitted.

**File:** `pipeline/docker_ops.py`

Already has `image_size_bytes()` and `format_image_size()`. No changes needed here, but the tools service should import and use them.

### 2. Backend: Add pull/remove API endpoints

**File:** `app_backend/server.py`

Add two new POST endpoints:

#### `POST /tools/local/pull`
```json
// Request
{ "image": "mkdayyyy/mri-fs8-all:latest" }
// Response (SSE stream)
event: step
data: {"step": "pull", "status": "running", "detail": "Pulling mkdayyyy/mri-fs8-all:latest..."}

event: step
data: {"step": "pull", "status": "running", "detail": "abc123: Pulling layer... 45%"}

event: complete
data: {"ok": true}
```

Use `docker_ops._try_pull()` with `on_build_log` callback to stream progress via SSE (same pattern as `_handle_local_start_stream`).

#### `POST /tools/local/remove`
```json
// Request
{ "image": "mkdayyyy/mri-fs8-all:latest" }
// Response
{ "ok": true }
// or
{ "ok": false, "error": "image is being used by container xyz" }
```

Use `docker_ops.remove_image()`.

**File:** `app_backend/tools.py`

Add `pull_image(image, on_progress, on_build_log)` and `remove_image(image)` methods to `LocalToolService` (or call `docker_ops` directly from the handler).

### 3. Frontend: Update schemas and types

**File:** `tauri-app/src/api/schemas.ts`

Extend `toolImageSchema`:
```ts
export const toolImageSchema = z.object({
  image: z.string(),
  status: z.string(),
  tools: z.array(z.string()),
  repo_size: z.string().nullable().optional(),      // NEW
  uncompressed_size: z.string().nullable().optional(), // NEW
  image_id: z.string().nullable().optional(),        // NEW
});
```

Add response schemas:
```ts
export const pullImageResponseSchema = z.object({
  ok: z.boolean(),
  error: z.string().optional(),
});

export const removeImageResponseSchema = z.object({
  ok: z.boolean(),
  error: z.string().optional(),
});
```

**File:** `tauri-app/src/types/backend.ts`

Types auto-derived from Zod — `ToolImage` will automatically include the new fields.

### 4. Frontend: Add API client methods

**File:** `tauri-app/src/api/client.ts`

```ts
async pullImage(image: string): Promise<PullImageResponse> {
  return pullImageResponseSchema.parse(await this.post('/tools/local/pull', { image }));
}

async removeImage(image: string): Promise<RemoveImageResponse> {
  return removeImageResponseSchema.parse(await this.post('/tools/local/remove', { image }));
}
```

### 5. Frontend: Add query hooks for pull/remove

**File:** `tauri-app/src/query/useTools.ts`

```ts
export function usePullImage() {
  const client = useClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (image: string) => client.pullImage(image),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.tools.all });
    },
  });
}

export function useRemoveImage() {
  const client = useClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (image: string) => client.removeImage(image),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.tools.all });
    },
  });
}
```

Also add SSE streaming hook for pull progress:
```ts
export function usePullImageStream() {
  // Similar pattern to useStartPipelineStream
  // Connects to POST /tools/local/pull as SSE
  // Returns { pull, progress, logs, isPulling, error }
}
```

### 6. Frontend: Update Zustand store

**File:** `tauri-app/src/stores/toolsStore.ts`

Add per-image download state tracking:
```ts
interface ToolsState {
  // ... existing fields ...
  downloadState: Record<string, {
    status: 'idle' | 'pulling' | 'success' | 'failed';
    logs: string[];
    error?: string;
  }>;
  setDownloadState: (image: string, state: Partial<DownloadState>) => void;
  clearDownloadState: (image: string) => void;
}
```

### 7. Frontend: Rewrite `ToolsPage.tsx` — new layout

**File:** `tauri-app/src/pages/ToolsPage.tsx`

Replace the entire component with three sections:

#### Section 1: Environment Check
```
┌─────────────────────────────────────────────────┐
│ 🔧 Environment                    [Check] button │
├─────────────────────────────────────────────────┤
│ ┌──────────────┐ ┌──────────────┐ ┌───────────┐ │
│ │ Runtime Target│ │ Python Status│ │ Docker    │ │
│ │ Local         │ │ ● Ready 3.11│ │ ● Ready   │ │
│ └──────────────┘ └──────────────┘ └───────────┘ │
│                                                  │
│ [Install Python] button (if missing)             │
│ [Install Docker] button (if missing)             │
└─────────────────────────────────────────────────┘
```

- Use `useEnvironment()` hook (already exists).
- Show StatusPill for each dependency (Python, Docker).
- "Check Environment" button calls `refetchEnvironment()`.
- If Python/Docker missing, show an "Install" button (for now, can be a placeholder that shows instructions or links to install guide).

#### Section 2: Available Images (Installed)
```
┌─────────────────────────────────────────────────┐
│ ✅ Available Images              [2 installed]   │
├─────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────┐  │
│ │ mkdayyyy/mri-fs8-all:latest                 │  │
│ │                                              │  │
│ │ Tag: latest        Repo Size: 4.2 GB        │  │
│ │                    Uncompressed: 12.1 GB     │  │
│ │                                              │  │
│ │ Tools: fs8_recon_all, fs8_parcellation, ... │  │
│ │                                              │  │
│ │ [🗑 Remove Image]                           │  │
│ └─────────────────────────────────────────────┘  │
│ ┌─────────────────────────────────────────────┐  │
│ │ duattran05/cat12_26_glibc:latest            │  │
│ │ ...                                          │  │
│ └─────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

- Cards rendered from `images.filter(isImageInstalled)`.
- Each card shows: image tag (mono font), repo_size, uncompressed_size, tools list.
- "Remove Image" button → calls `useRemoveImage()` mutation, shows Loader2 spinner while pending.
- After remove success, auto-refresh image list.

#### Section 3: Not Available Images (Missing)
```
┌─────────────────────────────────────────────────┐
│ ⚠️ Not Available                [3 missing]     │
├─────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────┐  │
│ │ mkdayyyy/mri-fs7-all:latest                 │  │
│ │                                              │  │
│ │ Tools: fs7_recon_all                         │  │
│ │                                              │  │
│ │ [⬇ Download Image]                          │  │
│ └─────────────────────────────────────────────┘  │
│                                                  │
│ ┌─ Download Progress (expandable) ─────────────┐ │
│ │ mkdayyyy/mri-fs7-all:latest   ● Pulling...  │ │
│ │ abc123: Downloading  45%  2.1GB/4.7GB        │ │
│ │ [View Full Log]                              │ │
│ └──────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

- Cards rendered from `images.filter(img => !isImageInstalled(img))`.
- Each card shows: image tag, tools list.
- "Download Image" button → triggers SSE pull stream.
- While pulling: button becomes disabled with Loader2 spinner + "Downloading...".
- Show a progress area below the missing cards section with real-time log lines.
- If pull fails: show error status pill + "View Log" button that expands a `<pre>` with full pull log.
- After download success, auto-refresh image list (image moves to Available section).

### 8. Frontend: Create `ImageCard` component

**File:** `tauri-app/src/components/ImageCard.tsx` (new file)

```tsx
interface ImageCardProps {
  image: ToolImage;
  installed: boolean;
  onRemove?: (image: string) => void;
  onDownload?: (image: string) => void;
  downloadState?: { status: string; logs: string[]; error?: string };
}
```

- Renders a card with image tag, size info (if installed), tools list.
- Contextual action button based on `installed` prop.
- Download progress/logs shown inline if `downloadState.status === 'pulling'`.

### 9. Frontend: Create `DownloadProgress` component

**File:** `tauri-app/src/components/DownloadProgress.tsx` (new file)

- Shows real-time pull progress for in-flight downloads.
- Collapsible log viewer.
- Error state with "View Log" button.

### 10. Cleanup

- Remove old table-based code from `ToolsPage.tsx`.
- Remove `imageSelection`-related code from store if no longer needed (cards don't use checkboxes).
- Remove `imageSearch` if search is no longer needed (card layout is grouped, search may be optional).
- Remove the "Docker Execution Log" Panel at the bottom (logs now shown per-image in download progress).

---

## Files to Modify

| File | Change |
|---|---|
| `app_backend/tools.py` | Add size fields to `image_status()` response. Add `pull_image()` and `remove_image()` methods. |
| `app_backend/server.py` | Add `POST /tools/local/pull` (SSE) and `POST /tools/local/remove` endpoints. |
| `tauri-app/src/api/schemas.ts` | Extend `toolImageSchema` with size fields. Add pull/remove response schemas. |
| `tauri-app/src/api/client.ts` | Add `pullImage()` and `removeImage()` methods. |
| `tauri-app/src/query/useTools.ts` | Add `usePullImage()`, `useRemoveImage()`, `usePullImageStream()` hooks. |
| `tauri-app/src/stores/toolsStore.ts` | Add per-image download state tracking. Remove bulk selection state if unused. |
| `tauri-app/src/pages/ToolsPage.tsx` | **Full rewrite**: 3-section card layout. |
| `tauri-app/src/lib/tools.ts` | Minor: may need `splitByInstallStatus()` helper. |
| `tauri-app/src/types/backend.ts` | Auto-updates from Zod schema changes. |

## New Files

| File | Purpose |
|---|---|
| `tauri-app/src/components/ImageCard.tsx` | Reusable card component for a single Docker image. |
| `tauri-app/src/components/DownloadProgress.tsx` | Real-time pull progress + collapsible log viewer. |

---

## API Contract Summary

### `POST /tools/local/images` (existing, extended)

Response `ToolImage` gains new fields:
```ts
{
  image: string;           // "mkdayyyy/mri-fs8-all:latest"
  status: string;          // "Installed" | "Missing"
  tools: string[];         // ["fs8_recon_all", "fs8_parcellation"]
  repo_size: string | null;      // "4.2 GB" (null if missing)
  uncompressed_size: string | null; // "12.1 GB" (null if missing)
  image_id: string | null;       // "sha256:abc123" (null if missing)
}
```

### `POST /tools/local/pull` (new, SSE)

Request: `{ "image": "mkdayyyy/mri-fs8-all:latest" }`

Response (SSE stream):
```
event: step
data: {"step": "pull", "status": "running", "detail": "Pulling... 45%"}

event: complete
data: {"ok": true}
// or
event: complete
data: {"ok": false, "error": "pull failed: ..."}
```

### `POST /tools/local/remove` (new)

Request: `{ "image": "mkdayyyy/mri-fs8-all:latest" }`

Response: `{ "ok": true }` or `{ "ok": false, "error": "..." }`

---

## Acceptance Criteria

1. Environment section shows Runtime Target, Python status (with version), Docker status, with a "Check Environment" button.
2. Available Images section shows installed image cards with: image tag, repo size, uncompressed size, tools list, and "Remove Image" button.
3. Not Available Images section shows missing image cards with: image tag, tools list, and "Download Image" button.
4. Clicking "Download Image" shows real-time pull progress (SSE). On failure, shows error + "View Log" button to see full log.
5. Clicking "Remove Image" removes the image and refreshes the list.
6. After pull success or remove success, the image list auto-refreshes and cards move between sections.
7. All UI follows DESIGN.md: cream canvas, hairline borders, no shadows, Sea Blue CTAs, JetBrains Mono for code/tags, Loader2 spinner for pending states.
8. Page is responsive: cards stack vertically on narrow screens, 2-column grid on wide screens.
