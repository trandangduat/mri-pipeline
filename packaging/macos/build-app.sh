#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${1:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

echo "========================================"
echo "  NeuroFlow macOS Builder"
echo "========================================"
echo ""

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script must be run on macOS." >&2
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

echo "[5/5] Building Tauri app..."
(cd "$TAURI_APP_DIR" && npm run tauri build)
echo ""

APP_PATH="$TAURI_SRC_DIR/target/release/bundle/macos/NeuroFlow.app"
DMG_PATH="$(find "$TAURI_SRC_DIR/target/release/bundle/dmg" -maxdepth 1 -name '*.dmg' -print -quit 2>/dev/null || true)"

echo "========================================"
echo "  Build Complete"
echo "========================================"
if [[ -d "$APP_PATH" ]]; then
  echo "App: $APP_PATH"
fi
if [[ -n "$DMG_PATH" ]]; then
  echo "DMG: $DMG_PATH"
fi
