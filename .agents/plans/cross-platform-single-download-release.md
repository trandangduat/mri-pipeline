# Cross-Platform Single-Download Release Plan

## Goal

Ship NeuroFlow as the smallest practical **single-download** release for each supported desktop target, without a measurable reduction in normal runtime performance:

| Target | Release artifact | Runtime form |
| --- | --- | --- |
| Windows x64 | Signed NSIS setup `.exe` | Installed app with bundled one-directory backend |
| Linux x64 | AppImage | One executable download with bundled one-directory backend |
| macOS arm64 and x64 | Separate signed/notarized DMGs | A mounted/downloaded single file that installs/runs a signed `.app` bundle |

Do not claim one executable works on Windows, Linux, and macOS. Native code, Python extensions, OS webviews, and tool containers require distinct per-OS/per-CPU builds. A literal single running file is also inappropriate for macOS, whose supported desktop form is an `.app` bundle.

Use a single *distribution file* per platform rather than PyInstaller `--onefile`. Keep the Python sidecar in PyInstaller one-directory mode inside the Tauri bundle. One-file mode re-extracts on every application and worker launch, increasing startup latency, temporary disk use, and antivirus risk.

Docker, images, FreeSurfer licences, remote servers, and optional data remain external/manageable content. They cannot be embedded while retaining a small artifact or a reasonable memory footprint.

## Review Summary and Release Gates

The source review covered 101 Python files (23,359 lines), 97 TypeScript/TSX files (18,855 lines), 3 Rust files, platform packaging scripts, and current tests.

### Must fix before any release

1. **Package the frozen backend.** The platform scripts copy it to `tauri-app/src-tauri/backend`, but `tauri-app/src-tauri/tauri.conf.json` does not package that directory. Normal Tauri installers therefore cannot start the backend. The Windows portable folder masks this only by copying `backend/` beside the executable manually.
2. **Make static content explicitly package-aware.** The current PyInstaller specs omit `info/`, `assets/atlases/`, `docker/`, `normalize_volumes.py`, and the optional `NeuroFLOW-private` scheduler content. Packaged statistics/atlas/image-build/scheduler paths are incomplete or fail silently.
3. **Close the privileged loopback API.** `app_backend/server.py` exposes file operations, Docker actions, job management, and remote SSH actions with `Access-Control-Allow-Origin: *`. Require a new random launch token for all non-health requests, reject non-loopback peers, and allow only the app's origin. The frontend must obtain the token from Tauri, not bundle it as a constant.
4. **Remove raw job-start command injection paths.** `/jobs/local/start` bypasses request preparation, and `subject_id` plus path values reach `sh -c` builders. Route every start through the existing strict request-preparation path, validate all fields, and quote/remove all shell interpolation.
5. **Protect remote credentials and host identity.** Do not serialize remote passwords to `outputs/jobs/job_registry.json`; migrate/redact current registry values and use platform credential storage or ask again. Replace Paramiko `AutoAddPolicy()` with persistent, user-approved known-host verification and host-key-change rejection.
6. **Make job state writes safe.** The threaded server does unsynchronized read-modify-write registry updates through a predictable temporary filename. Use locking plus unique/atomic replacement, or move the registry to SQLite with a migration.
7. **Restore green release checks.** `npm run typecheck` currently fails on `import.meta.env` typing and missing `RemotePayload`; `npm run lint` has 73 errors; the checked-in virtual environment points to a missing Python 3.12 executable, so the Python suite cannot run. Resolve these or rebuild an ignored local virtual environment before relying on tests.
8. **Repair the authenticated build smoke check.** The new sidecar correctly protects `/capabilities/runtime`, but every platform `build-backend` script currently probes that endpoint without the generated token. Pass a build-only random token to the frozen backend and send its `Authorization: Bearer` header in the Windows, Linux, and macOS smoke probes. Verify both success with the token and rejection without it.
9. **Resolve PyInstaller's resource directory precisely.** PyInstaller 6 one-directory bundles default to `_internal/`, while the native shell currently passes the backend executable's parent as `NEUROFLOW_RESOURCE_ROOT`. Static data declared in `a.datas` will therefore resolve incorrectly in a successfully built package. Choose one explicit contract across all targets: either set `COLLECT(contents_directory=".")` or set the resource root to the actual `_internal` directory. Add a frozen-artifact inspection and runtime resource smoke test; do not infer this from an unfrozen unit test.
10. **Make release automation publish the intended artifacts.** Current workflows archive portable folders despite producing native Tauri bundles. Upload the signed Windows NSIS `.exe`, Linux AppImage, and macOS architecture-specific DMG as the primary artifacts. Portable archives may be optional internal artifacts only.

### Important performance and size work

- Replace the post-stage recursive chmod plus four full filesystem scans in `pipeline/workspace.py` with one pruned traversal over newly created files. Never descend into preserved FreeSurfer outputs.
- Stream container output to a bounded log/ring buffer instead of retaining whole process output in memory.
- Remove runtime `pandas` (about 112 MiB with NumPy), Pillow (about 15 MiB), and `psutil` from the frozen backend only after smoke/feature tests prove their paths are not required. Move icon conversion to a build dependency; make cleanup tooling development-only. Keep Paramiko and PyYAML for the enabled remote/NeuroFLOW features.
- Stop placing the same Python packages both as PyInstaller modules and `datas`; package source code once and only include non-code runtime data.
- Keep Vite production minification. Consolidate overlapping Geist static/variable font imports only after screenshot visual regression checks.
- Add this Cargo release profile after error-path tests pass:

  ```toml
  [profile.release]
  strip = "symbols"
  lto = "thin"
  codegen-units = 1
  panic = "abort"
  ```

### Content-size decision

Surface atlas content alone is approximately 577 MiB (the wider static-data set is roughly 631 MiB), while MRI Docker images are much larger. A fully offline, all-features build cannot be small. Ship a core client with only essential configuration, then provide signed/versioned optional content packs:

- default/frequently used static atlas pack;
- full atlas pack;
- optional NeuroFLOW scheduler pack when its private source is distributable;
- offline Docker image packs for air-gapped users.

The app must show pack size, version, digest, license, install location, and exact missing-content remediation. Download/install only after explicit user action; verify a signed manifest and SHA-256 before activation. Never silently fetch or rebuild a tool at runtime.

## Implementation Plan

### 1. Define support and artifact contracts

- Document supported targets as Windows x64, Linux x64, macOS arm64, and macOS x64. Add Windows ARM64/Linux ARM64 only once CI and every required Docker image are proven native/multi-arch.
- Pin every OCI image to an immutable digest and publish/test native Linux manifests. The present image-size logic assumes `linux/amd64`, so Apple Silicon compatibility must not be claimed until verified.
- Define public artifact names, checksums, SBOM/provenance output, licences, and retention rules. Record explicit host prerequisites: WebView2 on Windows, WebKitGTK dependencies on Linux, Docker/remote engine, and FreeSurfer licence when selected.
- Define two user modes with separate data locations:
  - installed mode: writable state under Tauri's per-user application-data directory;
  - portable mode: opt-in, writable state under a sibling `NeuroFlow-data` directory, never inside signed/read-only resources.

### 2. Separate immutable resources from mutable state

- Extend `app_backend/paths.py` with explicit, validated paths for `NEUROFLOW_RESOURCE_ROOT` (read-only) and `NEUROFLOW_DATA_ROOT` (writable). Retain the existing portable variables only as backward-compatible aliases.
- Refactor `pipeline/config.py`, `pipeline/stats.py`, `pipeline/runner.py`, `pipeline/docker_ops.py`, `app_backend/metadata.py`, and remote upload code to resolve immutable assets, info tables, tool build contexts, `normalize_volumes.py`, and optional scheduler content from the resource/content-pack root—not `Path(__file__).parent.parent`.
- Keep app config, licences, logs, job registry, and temporary state in the data root. Preserve the selected user output directory unchanged.
- Add explicit availability checks at startup and request validation. If a selected atlas/scheduler/tool context is missing, show a direct install action and do not silently skip work.

### 3. Correct the Python sidecar and its packaging

- Retain `app_backend/neuroflow_backend_cli.py` dispatcher modes (`server` and `worker`) and PyInstaller one-directory output. Verify frozen worker invocation uses the same executable and succeeds after installation.
- Replace the three duplicated specs with a shared base/configuration where practical. Include only runtime Python modules and exact non-code data required by the core client; remove duplicate source `datas`.
- Stage the whole backend directory at `tauri-app/src-tauri/resources/backend/` and include it in Tauri `bundle.resources` mapped to `backend`. Do not use `externalBin`: it is designed around one target-suffixed binary and does not model the backend's adjacent Python libraries.
- Update `tauri-app/src-tauri/src/lib.rs` to find the resource backend reliably in installed and AppImage/macOS layouts. Pass resource/data roots, a randomly generated API token, and no untrusted inherited runtime overrides to the child process.
- Separate sidecar stdout/stderr from user-readable bounded logs and ensure all app exit/error paths terminate the backend process group and workers.

### 4. Secure local and remote execution before enabling packaged builds

- Add a loopback-peer check and token middleware in `app_backend/server.py`; expose only an unauthenticated minimal readiness endpoint needed before token transfer. Remove wildcard CORS and update the frontend client to attach the token.
- Delete or refactor the raw local-start handler to call `prepare_run_request`. Add allowlists for identifiers/tool keys; pass commands as argument arrays; remove `sh -c` where possible; otherwise apply correct POSIX quoting to every dynamic component.
- Add malicious-input tests for subject ids, filenames, input/output paths, remote paths, remote Python command, and request payloads.
- Replace SSH permissive policy with a user-confirmed known-hosts database stored in user data. Support first-use fingerprint display and reject a changed key.
- Implement unknown-host handling as a typed, non-writing error. `/remote/validate` must return structured `trust_required` data before any command execution, and an explicit protected approval endpoint must re-fetch and compare the displayed SHA-256 fingerprint before atomically saving it. Never use Paramiko `AutoAddPolicy()` in either pooled or direct connection paths.
- Parse and allowlist the configured remote Python command; reject shell operators and quote every accepted token. Replace unquoted image-pull here-documents with safe data writes so `$()`, backticks, variables, and newlines cannot execute remotely.
- Store SSH password/secret material only in OS credential storage. Migrate existing job registries by removing plaintext secret fields. Keep a redacted run summary only.
- Add a database/locking strategy for job state and a 20–50 concurrent start/refresh test to prove no data loss or corruption.

### 5. Reduce resource use without observable performance loss

- Implement a bounded line/byte ring buffer for container output while writing full debug logs to disk only when requested/configured.
- Remove the repeated post-stage recursive scans: discover outputs once and pass that result forward; make cleanup one pruned `os.walk` traversal that never descends into retained `mri`, `stats`, `logs`, `freesurfer`, or export trees. On POSIX, repair only failed/new paths; never recursively chmod the growing subject tree, and skip it on Windows.
- Replace the `O(N^2)` batch-report rewrites with an initial/final writer or a rate-limited cached writer. Preserve final CSV contents byte-for-byte and retain real-time job events.
- Replace unbounded frontend job-event/modal-metrics/download-log storage with incremental per-image reducers and bounded diagnostic/byte rings. Do not blindly slice events: preserve exact current state per subject/stage and request subject detail lazily. Add 10k-subject/70k-event linearity tests and retain the displayed final metric samples.
- Correct render-time ref writes, impure render timestamps, and synchronous effect state updates rather than suppressing React lint rules. Clear unused imports/variables and restore a zero-error, zero-warning frontend lint/test suite.
- Establish baseline metrics before and after: cold launch time, idle RSS for shell and sidecar, job-start latency, app download size, installed size, and a representative pipeline runtime. Reject a change that exceeds a pre-agreed 5% job-runtime or interactive-latency regression.
- Build with Vite/Rust release optimisation and audit the generated bundle/sidecar manifests. Do not remove dependencies solely from static inspection; retain a feature test for every dependency removed.

### 6. Implement optional content packs and Docker policy

- Create a content manifest format with product version, OS/architecture applicability, source URL, SHA-256, signature, licences, unpacked size, and resource-root mapping.
- Start with one `surface-atlases` data-only pack. It must contain exactly the referenced Destrieux, Yale `_new`, Kong, and Schaefer files—never the two orphan Yale annotations—and mount as a single verified read-only `/atlas-assets` root. Built-in `aparc` must require no pack.
- Pin an Ed25519 public key in the core application. The detached signature covers canonical index bytes; the pack archive contains its own per-file manifest (relative path, bytes, SHA-256). Make `cryptography` an explicit runtime release dependency rather than relying on Paramiko's transitive dependency.
- Install only after an explicit action: accept only a known pack ID, use HTTPS, stream to a random `.part`, enforce size limits, verify index/archive/pack signatures and hashes, reject traversal/symlinks/duplicates/unknown files/compression bombs, verify in a same-filesystem staging directory, then atomically activate a version and preserve the previous version on failure.
- Make missing, partial, incompatible, or unlicensed pack content a pre-Docker/pre-SSH validation error. Derive and sync only the selected surface files in remote runs. Do not silently mount an empty directory or upload every atlas.
- Do not publish a pack until redistribution rights and notices are verified for every file. The separate missing MNI NIfTI assets require their own verified pack or explicit UI unavailability.
- Add an app-managed installer that downloads to a temporary location, validates signature/digest/size, atomically activates the pack, and supports removal without touching user outputs or secrets.
- Package only the minimal core static data in the main artifact. Create full/offline packs outside the app download and keep them versioned with the release.
- Make image management explicit: report required image digests and sizes; pull/import only after user confirmation; provide offline OCI imports. Do not bundle Docker Desktop, Docker Engine, GPU drivers, or MRI Docker images in the core artifact.

### 7. Build and release automation

- Create native CI jobs for each target. PyInstaller is not a cross-compiler: build the backend on its target OS/architecture. Build Linux AppImage on the oldest supported Linux baseline.
- Replace the current platform scripts with deterministic, idempotent assembly scripts using locked Node/Python/Rust inputs. Do not modify source-tree resources during a build; stage under an ignored build directory.
- Windows: configure Tauri NSIS, WebView2 bootstrapper for the smallest download, sign the installer and embedded executables with Authenticode plus timestamp.
- Linux: produce AppImage, checksums, SBOM/provenance, and optional signature.
- macOS: produce separate arm64/x64 applications, sign every nested executable/library with hardened runtime, notarize and staple the DMG. Do not attempt to merge PyInstaller builds with `lipo`.
- Require signing credentials and macOS/Linux native CI runners before publishing public artifacts. Without those, publish only explicitly marked unsigned internal test artifacts.

### 8. Add release-grade verification

Automated tests:

1. Unit tests for installed/portable resource and data path resolution, frozen worker command selection, API token/loopback denial, validation, credential migration, SSH fingerprints, atomic registry state, content manifests, bounded logging, and pruned cleanup.
2. Package-inspection tests for every resource/data pack and an assertion that the current bundle actually contains `backend/neuroflow-backend` plus required adjacent files.
3. Native CI smoke tests that install/unpack each artifact, launch the real sidecar, pass health/capability checks, and close without orphaned processes.
4. End-to-end tests for a minimal Docker job, a default stats job, an installed atlas-pack job, remote connection, missing Docker/content diagnostics, and an offline content/image import.
5. Malicious browser-origin and shell-injection regressions returning 401/403 or safe validation errors.
6. Fresh-machine checks on Windows, Linux, macOS arm64, and macOS x64 for launch, update/uninstall/portable moves, signing/Gatekeeper verification, and documented host prerequisite handling.
7. Size/performance budget collection and comparison against the established baseline.

Manual acceptance:

- Download exactly one platform artifact, verify checksum/signature, install/run it without system Python, and confirm the backend is bundled.
- Confirm default app operation uses little idle memory and no tool/image download until the user asks.
- Confirm selected user outputs never move into application data and all app state follows installed/portable policy.
- Confirm full functionality when the required optional data/image packs and licences are installed.

## Changed Areas

- `app_backend/paths.py`, `app_backend/server.py`, `app_backend/jobs.py`, `app_backend/remote.py`, `app_backend/metadata.py`
- `pipeline/config.py`, `pipeline/runner.py`, `pipeline/stats.py`, `pipeline/workspace.py`, `pipeline/executor.py`, `pipeline/docker_ops.py`, `pipeline/job_worker.py`, `pipeline/jobs.py`, `pipeline/registry.py`
- `remote/ssh_client.py`, `remote/remote_runner.py`
- `tauri-app/src-tauri/tauri.conf.json`, `tauri-app/src-tauri/Cargo.toml`, `tauri-app/src-tauri/src/lib.rs`
- `tauri-app/src/api/client.ts`, token bootstrap/client types, frontend release-check failures, and frontend test coverage
- `packaging/windows/*`, `packaging/linux/*`, `packaging/macos/*`, plus native CI/release workflow and content-pack tooling
- focused Python, Rust, frontend, package-inspection, and fresh-install integration tests

## Out of Scope Without a New Product Decision

- A single runnable binary shared by all operating systems.
- Bundling Docker Desktop/Engine, all Docker images, GPU drivers, or every atlas in the small core release.
- Publishing signed Windows/macOS releases without approved signing identities, notarization credentials, and a native macOS build environment.

## Executor Handoff

Implement this plan in ordered phases. Do not build or publish release artifacts until the P0 security, completeness, and typecheck gates are green. Preserve existing user changes, and report any missing signing credentials, private NeuroFLOW distribution approval, or native runner access as an external release blocker.

## Current Verification Snapshot (2026-09-28)

### Done on this Windows checkout (`packaging/release-hardening-wip`)

- SSH host-key **UI** fingerprint review before Connect is in place (`5d58991`), with backend `trust_required` + protected approval from the release-hardening foundation (`1914a1f`).
- PyInstaller resource root is pinned to `_internal` across specs and the Tauri shell (`28f688d`); frozen metadata smoke resolves `project_root` under `_internal`.
- Kong 100/300/400 options stay gated out of the core picker until a pack provides files (`fe56afa`); they are advertised as pack-backed and flip to available when a signed `surface-atlases` pack is activated (`5d4fcc9`).
- **Content-pack machinery implemented** (`5d4fcc9`): Ed25519-pinned verifier, `surface-atlases` manifest/archive format, install/remove API + Tools UI import hook, synthetic signed fixtures (verify/install/activate/reject-tamper). `cryptography` is an explicit runtime dependency. **Redistribution rights are still required before shipping real proprietary atlas binaries.**
- **Windows unsigned internal-test backend freeze**: `packaging/windows/build-backend.ps1` produced `dist/neuroflow-backend/` (copied to `dist-portable/backend/`). Smoke green: token auth (401 without bearer), capabilities SSH ok, metadata `_internal` root, content-packs list, process cleanup. Artifacts marked `UNSIGNED-INTERNAL-TEST.txt`.
- **Windows unsigned internal-test desktop app** (2026-09-28 ~11:15 ICT): `packaging/windows/build-portable.ps1` completed end-to-end (backend rebuild + Tauri NSIS + portable assemble). Artifacts:
  - Portable: `dist-portable/windows/NeuroFlowPortable/` (~37 MB) with `NeuroFlow.exe` (~4.7 MB) beside `backend/` (`neuroflow-backend.exe` + `_internal` layout intact: `normalize_volumes.py`, `pipeline/job_worker.py`, `info/`, `configs/neuroflow`).
  - NSIS installer: `tauri-app/src-tauri/target/release/bundle/nsis/NeuroFlow_0.1.0_x64-setup.exe` (~12.3 MB).
  - All three marked `UNSIGNED-INTERNAL-TEST.txt` (no Authenticode).
  - Smoke: portable backend token path green (caps SSH ok, metadata `project_root` under `backend\_internal`, 401 without bearer); brief GUI launch kept process alive and `/health` on `127.0.0.1:8765` returned `ok` (service `mri-pipeline-backend`). Signing skipped (none available). WebView2 present on host; NSIS configured with `downloadBootstrapper` for machines without it.

### External blockers / cannot claim public multi-OS release

**Honest host status (2026-09-28):** this Windows checkout produced **unsigned Windows internal-test artifacts only** (portable folder + NSIS setup, both marked `UNSIGNED-INTERNAL-TEST.txt`). Do **not** claim Linux AppImage or macOS DMG artifacts, signed installers, or a public multi-OS release from this machine.

Blockers that must clear before any public release:

- **Windows Authenticode + timestamp** for the NSIS setup and every embedded executable (shell + PyInstaller backend). No signing identity on this host; unsigned builds must stay labeled internal-test.
- **macOS code signing + notarization/stapling**, and a **native macOS runner** able to produce separate **arm64 and x64 DMGs** (do not lipo PyInstaller backends; do not build macOS on Windows).
- **Native Linux runner** for the **AppImage** (WebKitGTK/Tauri Linux deps + package smoke). Not available or verifiable on this Windows host.
- **Redistribution rights + licence notices** for real **surface-atlases** binaries (Destrieux / Yale / Kong / Schaefer, etc.). Machinery and **synthetic fixtures only** are in-tree today (`packaging/content_packs/`, `5d4fcc9`); do not ship proprietary atlas payloads without approval. Optional **MNI NIfTI** pack (or explicit UI unavailability) is still unfinished.
- **Release-grade verification still open:** clean-machine install/uninstall/portable-move tests; size and performance baselines vs budget; SBOM/provenance attached to signed primary artifacts; offline OCI image packs / digest-pinned image policy checks.
- Until the above are cleared, CI/workflows and humans must keep labeling outputs **unsigned-test / internal-only** and must not publish them as the public single-download release.
