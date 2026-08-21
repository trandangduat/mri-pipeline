# NeuroFlow macOS Build

Build this on macOS. Use Apple Silicon for arm64 builds and Intel macOS for x64 builds, or configure a universal build separately.

## Prerequisites

- macOS
- Xcode Command Line Tools: `xcode-select --install`
- Node.js LTS and npm
- Rust via rustup
- Python 3.10+
- Docker Desktop installed and running for end users

## Build

From the project root:

```bash
./packaging/macos/build-app.sh
```

This will:

1. Build `neuroflow-backend` with PyInstaller one-dir mode.
2. Copy it into `tauri-app/src-tauri/backend/` for Tauri bundling.
3. Run `npm run tauri build`.
4. Produce the Tauri macOS output under `tauri-app/src-tauri/target/release/bundle/`.

## End User Requirements

- Docker Desktop installed and running.
- Required Docker images pulled.
- FreeSurfer license if using FreeSurfer-based tools.

## Signing

Unsigned builds are suitable for internal testing. For smooth distribution outside your machine, sign and notarize with an Apple Developer certificate.
