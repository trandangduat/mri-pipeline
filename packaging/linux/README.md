# NeuroFlow Linux Build

Build this on Linux or in CI.

## Prerequisites

- Node.js LTS and npm
- Rust via rustup
- Python 3.10+
- Tauri Linux system dependencies, including WebKitGTK, librsvg, OpenSSL, and AppIndicator packages

## Build

From the project root:

```bash
./packaging/linux/build-app.sh
```

This will:

1. Build `neuroflow-backend` with PyInstaller one-dir mode.
2. Stage the complete one-directory backend at `build/tauri-resources/backend/` for Tauri bundling.
3. Run `npm run tauri build`.
4. Produce a single-file AppImage under `tauri-app/src-tauri/target/release/bundle/appimage/`.

The AppImage contains the native shell and its PyInstaller backend. Docker and its large medical-imaging containers remain host-managed downloads, keeping the application installer compact.

## Resource-root contract

PyInstaller 6 one-directory builds keep declared data under `_internal/`.
Specs keep COLLECT(contents_directory="_internal"). Tauri stages that whole
folder as `backend/` and sets NEUROFLOW_RESOURCE_ROOT to `backend/_internal`
- not the directory that holds neuroflow-backend. Build scripts inspect the
frozen `_internal` tree and smoke-check /metadata so a wrong root fails
before packaging continues.

## End User Requirements

- Docker installed and running.
- Required Docker images pulled.
- FreeSurfer license if using FreeSurfer-based tools.
