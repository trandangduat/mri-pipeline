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

echo "[1/6] Checking prerequisites..."
for cmd in node npm cargo python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "$cmd is required but not found." >&2
    exit 1
  fi
  echo "  OK: $cmd"
done
echo ""

echo "[2/6] Building backend executable..."
"$SCRIPT_DIR/build-backend.sh" "$PROJECT_ROOT"
echo ""

echo "[3/6] Preparing Tauri backend resources..."
TAURI_APP_DIR="$PROJECT_ROOT/tauri-app"
TAURI_SRC_DIR="$TAURI_APP_DIR/src-tauri"
BACKEND_RESOURCE_DIR="$PROJECT_ROOT/build/tauri-resources/backend"
rm -rf "$BACKEND_RESOURCE_DIR"
mkdir -p "$(dirname "$BACKEND_RESOURCE_DIR")"
cp -R "$PROJECT_ROOT/dist/neuroflow-backend" "$BACKEND_RESOURCE_DIR"
chmod +x "$BACKEND_RESOURCE_DIR/neuroflow-backend"
echo "  Copied backend to: $BACKEND_RESOURCE_DIR"
echo ""

echo "[4/6] Installing frontend dependencies..."
if [[ "${CI:-}" == "true" || ! -d "$TAURI_APP_DIR/node_modules" ]]; then
  (cd "$TAURI_APP_DIR" && npm ci)
else
  echo "  node_modules exists, skipping install."
fi
echo ""

echo "[5/6] Checking app icons..."
ICON_PNG="$TAURI_SRC_DIR/icons/icon.png"
ICON_ICNS="$TAURI_SRC_DIR/icons/icon.icns"
for icon in "$ICON_PNG" "$ICON_ICNS"; do
  if [[ ! -f "$icon" ]]; then
    echo "Missing macOS application icon: $icon" >&2
    exit 1
  fi
done
echo "  icon.png and icon.icns exist"
echo ""

echo "[6/6] Building Tauri app..."
TAURI_BUNDLES="${NEUROFLOW_TAURI_BUNDLES:-dmg}"
(cd "$TAURI_APP_DIR" && npm run tauri build -- --bundles "$TAURI_BUNDLES")
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
