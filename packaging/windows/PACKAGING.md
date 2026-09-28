# Hướng dẫn đóng gói NeuroFlow cho Windows (NSIS + Portable)

Tài liệu này mô tả **cách build lại** bản Windows nội bộ (unsigned) giống quy trình đã chạy trên máy này: **NSIS installer** + **thư mục portable**. Chi tiết kỹ thuật tiếng Anh bổ sung: `README-PORTABLE.md` trong cùng thư mục.

> **Trạng thái hiện tại:** artifact là **unsigned internal-test** — chỉ dùng nội bộ / QA. Không phân phối công khai khi chưa ký Authenticode + timestamp.

---

## 1. Điều kiện tiên quyết (Prerequisites)

| Thành phần | Ghi chú |
| --- | --- |
| **Windows 10/11** | Build trên path local Windows (ví dụ `C:\Users\...\mri-pipeline`). **Không** build từ UNC/`\\wsl.localhost\...`. |
| **Node.js LTS + npm** | Dùng trong `tauri-app/` (`npm run tauri build`). |
| **Rust (rustup) + Cargo** | Toolchain ổn định; Tauri 2 cần Rust. |
| **Python 3.10+** | Nên dùng `.venv` ở root repo (`.\.venv\Scripts\python.exe`). PyInstaller sẽ được script cài nếu thiếu. |
| **WebView2 Runtime** | End-user cần [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/). Trên Windows 11 thường đã có; máy sạch có thể phải cài. |
| **Docker Desktop** (runtime) | App gọi Docker image y tế trên máy người dùng — **không** nhét image vào installer. |

Các thư mục build lớn (`dist/`, `dist-portable/`, `build/`, `tauri-app/src-tauri/target/`, `node_modules/`) đã được **gitignore** — không commit.

---

## 2. Lệnh build chính xác

Làm việc từ **root repo** (`mri-pipeline`).

### 2.1. Portable + NSIS (khuyến nghị khi cần cả hai)

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build-portable.ps1
```

Script sẽ lần lượt:

1. Build backend PyInstaller one-dir → `dist\neuroflow-backend\`
2. Stage backend → `build\tauri-resources\backend\`
3. `npm run tauri build -- --bundles nsis` trong `tauri-app\`
4. Ghép thư mục portable → `dist-portable\windows\NeuroFlowPortable\`

### 2.2. Chỉ NSIS (bỏ bước ghép portable)

`build-app.ps1` gọi cùng pipeline nhưng thêm `-SkipPortable`:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build-app.ps1
```

### 2.3. Chỉ backend (debug / tái tạo `neuroflow-backend.exe`)

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build-backend.ps1
```

---

## 3. Đường dẫn output

| Artifact | Path |
| --- | --- |
| **Portable folder** | `dist-portable\windows\NeuroFlowPortable\` (`NeuroFlow.exe` + `backend\`, `config\`, `logs\`, `outputs\`, …) |
| **NSIS setup** | `tauri-app\src-tauri\target\release\bundle\nsis\NeuroFlow_0.1.0_x64-setup.exe` |
| **Backend one-dir** | `dist\neuroflow-backend\` (`neuroflow-backend.exe` + `_internal\`) |
| **Marker unsigned** | `UNSIGNED-INTERNAL-TEST.txt` cạnh artifact (NSIS / portable / backend) |

Tên version trong file setup lấy từ cấu hình Tauri (`0.1.0` hiện tại); nếu đổi version trong `tauri.conf`, tên exe setup sẽ đổi theo.

---

## 4. Cấm: `cargo build --release` trần (lỗi Vite :1420)

**Không** đóng gói shell bằng:

```text
cd tauri-app\src-tauri
cargo build --release
```

Với Tauri, lệnh này thường giữ `cfg(dev)` → WebView mở `http://127.0.0.1:1420` (Vite `devUrl`) thay vì nhúng `frontendDist`. Khi không có Vite, cửa sổ báo **ERR_CONNECTION_REFUSED** / “127.0.0.1 refused to connect” dù backend `127.0.0.1:8765` vẫn healthy.

**Luôn** dùng `npm run tauri build` (như `build-portable.ps1`). Script portable còn kiểm tra chunk JS/CSS từ `tauri-app\dist\assets` đã được nhúng trong `NeuroFlow.exe` — thiếu thì fail sớm (“hollow shell”).

---

## 5. Ký số / phát hành công khai (blocking)

Trên máy developer điển hình:

- **Chưa** có chứng chỉ Authenticode + timestamp server → mọi `.exe` / NSIS là **unsigned internal-test**.
- Linux AppImage / macOS DMG signed+notarized **không** tạo được từ host Windows-only.
- Quyền redistribution atlas / image Docker vẫn là blocker bên ngoài (xem `.agents/plans/cross-platform-single-download-release.md`).

Marker `UNSIGNED-INTERNAL-TEST.txt` phải đi kèm khi giao nội bộ.

---

## 6. Smoke test nhanh (verify)

Sau khi build:

1. **Portable:** chạy `dist-portable\windows\NeuroFlowPortable\NeuroFlow.exe`
   - Không flash cửa sổ console đen khi mở app / spawn worker (subsystem Windows + `CREATE_NO_WINDOW`).
   - UI hiện (không phải trang Edge lỗi :1420).
2. **Health:** trong lúc app chạy, `http://127.0.0.1:8765/health` trả ok.
3. **NSIS (tuỳ chọn):** cài `NeuroFlow_*_x64-setup.exe` trên máy sạch / VM; xác nhận shortcut + launch tương tự. Tránh ghi đè install đang dùng nếu đang smoke portable.
4. (Tuỳ QA sâu hơn) `/capabilities/runtime` → 401 không token; có bearer thì SSH/capabilities ok như ghi trong `README-PORTABLE.md`.

---

## 7. Git: cái nào commit / cái nào ignore

### Nên commit (source / docs packaging)

- `packaging/windows/*.ps1`, `neuroflow-backend.spec`
- `packaging/windows/PACKAGING.md`, `README-PORTABLE.md`
- Sửa Tauri/backend liên quan đóng gói (HTTP/1.0 readiness, no-console, anti-hollow shell, …)

### Đã gitignore — **không** commit (tái tạo bằng script)

- `dist/`, `dist-portable/`, `build/` (trừ placeholder `.gitkeep` nếu có)
- `tauri-app/src-tauri/target/`, `tauri-app/dist/`, `node_modules/`
- `.venv/`, `__pycache__/`, `.test-deps/`, `benchmark_results/`
- `*.bak`, `*.bak.*`

Giữ bản portable/NSIS local để dùng nội bộ là bình thường; chúng **không** vào git. Muốn máy khác có cùng binary → build lại hoặc copy ngoài git.

### Để ngoài commit (WIP không liên quan packaging)

- `.agents/plans/*` ad-hoc, `scripts/*_clean.sh`, báo cáo benchmark trong `docs/`, `configs/*_clean.txt`, v.v. — chỉ commit khi chủ đích review riêng.

---

## 8. Tóm tắt một dòng

```powershell
# Từ root repo, trên disk Windows local:
powershell -ExecutionPolicy Bypass -File packaging\windows\build-portable.ps1
# → portable: dist-portable\windows\NeuroFlowPortable\
# → NSIS:    tauri-app\src-tauri\target\release\bundle\nsis\NeuroFlow_*_x64-setup.exe
```

Không dùng `cargo build --release` trần cho shell. Artifact hiện tại = **unsigned internal-test**.
