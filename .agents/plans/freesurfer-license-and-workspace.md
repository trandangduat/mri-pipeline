# Plan: FreeSurfer License Path & Workspace Save Fix

## Root Cause Analysis

### License not uploaded to remote server

The workspace `okok.json` has `"license_dir": "license.txt"` — just a filename, not a full path.

**Why?** The license file picker (`PipelinePage.tsx:215`) does:
```typescript
const path = (file as unknown as {path?: string}).path || file.name;
```

In Tauri 2's webview, `<input type="file">` does NOT expose `file.path`. So it falls back to `file.name` which is just `"license.txt"`. The backend then does `Path("license.txt").exists()` → `False` → license is never uploaded.

**Result:** `_upload_license()` (`remote_runner.py:1019-1034`) silently skips upload because the local path doesn't exist. The remote job config hardcodes `license_dir: <remote_job_dir>/license` (`remote_runner.py:620`), but that directory is empty. Docker mounts empty dir → FreeSurfer can't find `/license/license.txt`.

### Fix: Use Tauri dialog plugin for native file picker with full path

The Tauri `dialog` plugin returns full absolute paths. Need to:
1. Install the plugin (Rust + JS)
2. Register it in Tauri builder
3. Add permissions
4. Replace the license `<input type="file">` with a button that calls `open()` from `@tauri-apps/plugin-dialog`

---

## Implementation Steps

### Step 1: Install Tauri dialog plugin

**Rust side** — `tauri-app/src-tauri/Cargo.toml`:
```toml
[dependencies]
tauri = { version = "2", features = [] }
tauri-plugin-opener = "2"
tauri-plugin-dialog = "2"    # ← ADD
```

**JS side** — run in `tauri-app/`:
```bash
npm install @tauri-apps/plugin-dialog
```

### Step 2: Register plugin in Rust

**File:** `tauri-app/src-tauri/src/lib.rs`

Add `.plugin(tauri_plugin_dialog::init())` to the builder:
```rust
tauri::Builder::default()
    .plugin(tauri_plugin_opener::init())
    .plugin(tauri_plugin_dialog::init())    // ← ADD
    .setup(|app| { ... })
```

### Step 3: Add dialog permissions

**File:** `tauri-app/src-tauri/capabilities/default.json`:
```json
{
  "permissions": [
    "opener:default",
    "dialog:default",
    "dialog:allow-open"
  ]
}
```

### Step 4: Replace license file picker with Tauri dialog

**File:** `tauri-app/src/pages/PipelinePage.tsx`

Remove the hidden `<input type="file">` for license. Replace the Browse button's `onClick` with:

```typescript
import {open} from '@tauri-apps/plugin-dialog';

// In the license section:
<button
  type="button"
  onClick={async () => {
    const selected = await open({
      multiple: false,
      filters: [{name: 'License', extensions: ['txt']}],
    });
    if (selected) {
      setFormField('licensePath', selected);  // full absolute path
    }
  }}
>
```

Remove the `licenseFileInput` ref and the hidden `<input>` element.

### Step 5: Fix workspace save — `tools` logic inversion

**File:** `tauri-app/src/pages/PipelinePage.tsx:1414-1439`

Current (buggy):
```typescript
const isCustom = fv.pipelineMode === 'Custom';
const tools: Record<string, string> = {};
if (isCustom && metadata) { ... }        // collects only for Custom
...(isCustom ? {} : {tools}),            // includes only for non-Custom
```

Fixed:
```typescript
const tools: Record<string, string> = {};
if (metadata) {
  for (const stage of metadata.stage_order || []) {
    const val = (fv as Record<string, unknown>)[`stage_${stage}`] as string | undefined;
    if (val) tools[stage] = val;
  }
}
// In workspace object — always include:
tools,
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `tauri-app/src-tauri/Cargo.toml` | Add `tauri-plugin-dialog = "2"` |
| `tauri-app/src-tauri/src/lib.rs` | Register dialog plugin |
| `tauri-app/src-tauri/capabilities/default.json` | Add dialog permissions |
| `tauri-app/src/pages/PipelinePage.tsx` | Use `open()` from dialog plugin for license picker; fix save workspace tools logic |
| `tauri-app/package.json` | `npm install @tauri-apps/plugin-dialog` |

---

## Verification

1. Select FreeSurfer preset → license input appears
2. Click Browse → native file dialog opens, returns full path like `/home/user/license/license.txt`
3. Start pipeline → check server logs: `_upload_license` should log "Uploading license file: license.txt"
4. Docker container runs → `/license/license.txt` exists, `FS_LICENSE` is set
5. Save workspace → `license_dir` in JSON should be the full path
6. Save workspace (Custom mode) → `tools` map should be populated
7. Load workspace → all fields restored including full license path
