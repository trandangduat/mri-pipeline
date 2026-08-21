#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${1:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

echo "========================================"
echo "  NeuroFlow Linux Builder"
echo "========================================"
echo ""

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This script must be run on Linux." >&2
  exit 1
fi

echo "[1/5] Checking prerequisites..."
for cmd in node npm cargo python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "$cmd is required but not found." >&2
    exit 1
  fi
  echo "  OK: $cmd"
done
echo ""

echo "[2/5] Building backend executable..."
"$SCRIPT_DIR/build-backend.sh" "$PROJECT_ROOT"
echo ""

echo "[3/5] Preparing Tauri backend resources..."
TAURI_APP_DIR="$PROJECT_ROOT/tauri-app"
TAURI_SRC_DIR="$TAURI_APP_DIR/src-tauri"
BACKEND_RESOURCE_DIR="$TAURI_SRC_DIR/backend"
rm -rf "$BACKEND_RESOURCE_DIR"
cp -R "$PROJECT_ROOT/dist/neuroflow-backend" "$BACKEND_RESOURCE_DIR"
chmod +x "$BACKEND_RESOURCE_DIR/neuroflow-backend"
echo "  Copied backend to: $BACKEND_RESOURCE_DIR"
echo ""

echo "[4/5] Installing frontend dependencies..."
if [[ ! -d "$TAURI_APP_DIR/node_modules" ]]; then
  (cd "$TAURI_APP_DIR" && npm install)
else
  echo "  node_modules exists, skipping install."
fi
echo ""

echo "[5/6] Preparing app icon..."
ICON_PNG="$TAURI_SRC_DIR/icons/icon.png"
ICON_ICO="$TAURI_SRC_DIR/icons/icon.ico"
if [[ ! -f "$ICON_ICO" ]]; then
  if [[ ! -f "$ICON_PNG" ]]; then
    echo "Missing icon source: $ICON_PNG" >&2
    exit 1
  fi
  if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    ICON_PYTHON="$PROJECT_ROOT/.venv/bin/python"
  else
    ICON_PYTHON="python3"
  fi
  "$ICON_PYTHON" - "$ICON_PNG" "$ICON_ICO" <<'PY'
from PIL import Image
import sys

src, dst = sys.argv[1], sys.argv[2]
img = Image.open(src).convert("RGBA")
img.save(dst, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
PY
  echo "  Generated icon.ico"
else
  echo "  icon.ico exists"
fi
echo ""

echo "[6/6] Building Tauri app..."
(cd "$TAURI_APP_DIR" && npm run tauri build)
echo ""

BUNDLE_DIR="$TAURI_SRC_DIR/target/release/bundle"

echo "========================================"
echo "  Build Complete"
echo "========================================"
if [[ -d "$BUNDLE_DIR" ]]; then
  find "$BUNDLE_DIR" -maxdepth 2 -type f -print
fi
