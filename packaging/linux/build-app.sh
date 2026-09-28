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

echo "[5/6] Checking app icon..."
ICON_PNG="$TAURI_SRC_DIR/icons/icon.png"
if [[ ! -f "$ICON_PNG" ]]; then
  echo "Missing Linux application icon: $ICON_PNG" >&2
  exit 1
fi
echo "  icon.png exists"
echo ""

echo "[6/6] Building Tauri app..."
TAURI_BUNDLES="${NEUROFLOW_TAURI_BUNDLES:-appimage}"
(cd "$TAURI_APP_DIR" && npm run tauri build -- --bundles "$TAURI_BUNDLES")
echo ""

BUNDLE_DIR="$TAURI_SRC_DIR/target/release/bundle"

echo "========================================"
echo "  Build Complete"
echo "========================================"
if [[ -d "$BUNDLE_DIR" ]]; then
  find "$BUNDLE_DIR" -maxdepth 2 -type f -print
fi
