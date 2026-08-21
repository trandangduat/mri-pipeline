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
2. Copy it into `tauri-app/src-tauri/backend/` for Tauri bundling.
3. Run `npm run tauri build`.
4. Produce Linux Tauri bundles under `tauri-app/src-tauri/target/release/bundle/`.

## End User Requirements

- Docker installed and running.
- Required Docker images pulled.
- FreeSurfer license if using FreeSurfer-based tools.
