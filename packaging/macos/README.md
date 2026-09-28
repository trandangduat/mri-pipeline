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
3. Run `npm run tauri build -- --bundles app`.
4. Keep the `.app` (Tauri's DMG step would delete it) (Tauri's DMG step would delete the `.app`).
5. Ad-hoc `codesign --force --deep --sign -` on `NeuroFlow.app` (local unsigned convenience only; **not** notarization).
6. If DMG was requested, create it with `hdiutil` from the signed `.app` under `tauri-app/src-tauri/target/release/bundle/dmg/`.

Use a native Apple Silicon machine for arm64 and an Intel machine for x64. Each DMG contains a macOS application bundle with the native backend; macOS cannot use one executable that runs on both CPU architectures.

## Opening a downloaded unsigned build (Gatekeeper)

Browsers (Firefox included) attach `com.apple.quarantine`. Combined with no Developer ID + notarization, macOS often shows:

> "NeuroFlow is damaged and can't be opened. You should move it to the Trash."

That is **not** a corrupt DMG. Full Vietnamese + English steps: **[OPEN-ON-MAC.md](./OPEN-ON-MAC.md)** (`xattr -cr` after copying the `.app` out of the DMG, Privacy & Security fallback). The real public-distribution fix remains Developer ID + notarize.

CI uploads `OPEN-ON-MAC.md` inside the macOS artifact zip alongside the DMG / `.app.tar.gz`.

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

- **Internal test / GHA artifact:** unsigned + optional ad-hoc identity (`codesign -s -`). No Apple certs. Expect quarantine on download Ã¢â€ â€™ use `OPEN-ON-MAC.md`.
- **Public distribution:** Developer ID Application certificate, notarize, and staple. Do not pretend ad-hoc signing replaces that.