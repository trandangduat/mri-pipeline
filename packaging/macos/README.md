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
2. Stage the complete one-directory backend at `build/tauri-resources/backend/` for Tauri bundling.
3. Run `npm run tauri build`.
4. Produce a single-download DMG under `tauri-app/src-tauri/target/release/bundle/dmg/`.

Use a native Apple Silicon machine for arm64 and an Intel machine for x64. Each DMG contains a macOS application bundle with the native backend; macOS cannot use one executable that runs on both CPU architectures.

## Resource-root contract

PyInstaller 6 one-directory builds keep declared data under `_internal/`.
Specs keep COLLECT(contents_directory="_internal"). Tauri stages that whole
folder as `backend/` and sets NEUROFLOW_RESOURCE_ROOT to `backend/_internal`
- not the directory that holds neuroflow-backend. Build scripts inspect the
frozen `_internal` tree and smoke-check /metadata so a wrong root fails
before packaging continues.

## End User Requirements

- Docker Desktop installed and running.
- Required Docker images pulled.
- FreeSurfer license if using FreeSurfer-based tools.

## Signing

Unsigned builds are suitable for internal testing. For smooth distribution outside your machine, sign and notarize with an Apple Developer certificate.
