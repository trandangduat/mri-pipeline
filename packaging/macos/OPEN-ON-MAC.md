# Mở NeuroFlow trên macOS / Open NeuroFlow on macOS

> **Bản thử nội bộ chưa ký (unsigned internal test).** Không phải DMG hỏng.
> Gatekeeper báo *"NeuroFlow is damaged and can't be opened"* vì app **chưa có Developer ID + notarize**, và file tải về bị gắn cờ quarantine (`com.apple.quarantine`) — đặc biệt khi tải bằng Firefox/Safari/Chrome từ GitHub Actions artifact.

> **Unsigned internal test build.** Not a corrupt DMG.
> Gatekeeper's *"damaged and can't be opened"* is the classic response for an **unsigned / un-notarized** app that still has the download **quarantine** flag — common after downloading a GHA artifact in Firefox.

---

## Tiếng Việt — cách mở nhanh

1. Mở file `.dmg` (double-click), kéo `NeuroFlow.app` ra **Applications** hoặc Desktop (không chạy trực tiếp từ trong volume DMG nếu có thể).
2. Trong Terminal, gỡ quarantine trên bản đã copy ra:

```bash
# Thay đường dẫn nếu bạn đặt app ở chỗ khác
xattr -cr /Applications/NeuroFlow.app
# hoặc
xattr -cr ~/Desktop/NeuroFlow.app
```

3. Mở lại app (double-click hoặc `open /Applications/NeuroFlow.app`).
4. Nếu vẫn bị chặn: **System Settings → Privacy & Security** → kéo xuống, bấm **Open Anyway** / **Allow Anyway** cạnh NeuroFlow, rồi mở lại.
5. **Không** cần (và CI **không** dùng) chứng chỉ Apple. Cách sửa đúng cho phân phối công khai: ký **Developer ID Application** + **notarize** + staple.

### Nếu artifact có thêm `.app.tar.gz`

```bash
cd ~/Downloads   # hoặc thư mục bạn giải nén artifact
tar -xzf NeuroFlow-macOS-arm64-*.app.tar.gz
xattr -cr ./NeuroFlow.app
open ./NeuroFlow.app
```

### Kiểm tra quarantine (tuỳ chọn)

```bash
xattr -l /Applications/NeuroFlow.app
# Nếu còn dòng com.apple.quarantine → chạy lại xattr -cr
```

---

## English — quick open steps

1. Open the `.dmg`, drag `NeuroFlow.app` to **Applications** or Desktop (prefer not launching only from the mounted DMG volume).
2. Clear quarantine on the copied app:

```bash
xattr -cr /Applications/NeuroFlow.app
# or
xattr -cr ~/Desktop/NeuroFlow.app
```

3. Open the app again.
4. If macOS still blocks it: **System Settings → Privacy & Security** → scroll down → **Open Anyway** / **Allow Anyway**, then open again.
5. No Apple certificates are required for this internal test artifact. The real distribution fix is **Developer ID Application** signing + **notarization** (+ staple). Ad-hoc `codesign -s -` in CI only helps some local/non-quarantined opens; **downloaded** builds still need `xattr -cr`.

### If the artifact also includes `.app.tar.gz`

```bash
cd ~/Downloads
tar -xzf NeuroFlow-macOS-arm64-*.app.tar.gz
xattr -cr ./NeuroFlow.app
open ./NeuroFlow.app
```

### Optional: inspect quarantine

```bash
xattr -l /Applications/NeuroFlow.app
# If you still see com.apple.quarantine, re-run xattr -cr
```

---

## Why this happens / Vì sao gặp lỗi này

| Cause / Nguyên nhân | Effect / Hiệu ứng |
| --- | --- |
| Browser download quarantine | macOS marks the DMG/app; Gatekeeper is stricter |
| No Developer ID + notarization | Gatekeeper may say the app is "damaged" instead of a clear "unidentified developer" dialog |
| Ad-hoc signature only | Helps unsigned local opens; does **not** replace notarization for downloads |

This is expected for the **unsigned GHA test DMG**. Do not Trash the app solely because of that dialog after an internal download — clear quarantine first.

---

## Artifact contents (this zip)

- `NeuroFlow-macOS-arm64-<sha>.dmg` — disk image (drag `.app` out, then `xattr -cr`)
- `NeuroFlow-macOS-arm64-<sha>.app.tar.gz` — same `.app` archived (if present)
- `*.sha256` — checksums
- `OPEN-ON-MAC.md` — this file

CI does **not** use Apple signing secrets. Treat as internal QA only.