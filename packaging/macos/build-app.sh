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

echo "[1/7] Checking prerequisites..."
for cmd in node npm cargo python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "$cmd is required but not found." >&2
    exit 1
  fi
  echo "  OK: $cmd"
done
echo ""

echo "[2/7] Building backend executable..."
"$SCRIPT_DIR/build-backend.sh" "$PROJECT_ROOT"
echo ""

echo "[3/7] Preparing Tauri backend resources..."
TAURI_APP_DIR="$PROJECT_ROOT/tauri-app"
TAURI_SRC_DIR="$TAURI_APP_DIR/src-tauri"
BACKEND_RESOURCE_DIR="$PROJECT_ROOT/build/tauri-resources/backend"
rm -rf "$BACKEND_RESOURCE_DIR"
mkdir -p "$(dirname "$BACKEND_RESOURCE_DIR")"
cp -R "$PROJECT_ROOT/dist/neuroflow-backend" "$BACKEND_RESOURCE_DIR"
chmod +x "$BACKEND_RESOURCE_DIR/neuroflow-backend"
echo "  Copied backend to: $BACKEND_RESOURCE_DIR"
echo ""

echo "[4/7] Installing frontend dependencies..."
if [[ "${CI:-}" == "true" || ! -d "$TAURI_APP_DIR/node_modules" ]]; then
  (cd "$TAURI_APP_DIR" && npm ci)
else
  echo "  node_modules exists, skipping install."
fi
echo ""

echo "[5/7] Checking app icons..."
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

# Tauri's dmg bundler removes macos/*.app after packaging ("Cleaning NeuroFlow.app").
# Always build the .app bundle first, ad-hoc codesign, then optionally rebuild DMG
# ourselves so both stay in the artifact (and OPEN-ON-MAC.md can refer to either).
REQUESTED_BUNDLES="${NEUROFLOW_TAURI_BUNDLES:-dmg}"
WANT_DMG=0
case ",${REQUESTED_BUNDLES}," in
  *,dmg,*) WANT_DMG=1 ;;
esac

echo "[6/7] Building Tauri .app (bundle=app; DMG handled after codesign)..."
echo "  Requested NEUROFLOW_TAURI_BUNDLES=${REQUESTED_BUNDLES} (WANT_DMG=${WANT_DMG})"
(cd "$TAURI_APP_DIR" && npm run tauri build -- --bundles app)
echo ""

APP_PATH="$TAURI_SRC_DIR/target/release/bundle/macos/NeuroFlow.app"
DMG_DIR="$TAURI_SRC_DIR/target/release/bundle/dmg"
DMG_PATH=""

echo "[7/7] Ad-hoc codesign (unsigned internal test; NOT notarized)..."
if [[ ! -d "$APP_PATH" ]]; then
  echo "Expected NeuroFlow.app was not produced at: $APP_PATH" >&2
  find "$TAURI_SRC_DIR/target/release/bundle" -maxdepth 3 -print >&2 || true
  exit 1
fi

# Ad-hoc identity ("-") helps some local unsigned opens. Downloaded builds
# still carry quarantine and need `xattr -cr` — see OPEN-ON-MAC.md.
# This is NOT Developer ID signing and does NOT notarize.
codesign --force --deep --sign - "$APP_PATH"
echo "  codesign -dv:"
codesign -dv --verbose=2 "$APP_PATH" 2>&1 | sed 's/^/    /' || true

if [[ "$WANT_DMG" -eq 1 ]]; then
  mkdir -p "$DMG_DIR"
  DMG_PATH="$DMG_DIR/NeuroFlow.dmg"
  echo "  Creating DMG from ad-hoc-signed .app → $DMG_PATH"
  TMP_DMG_DIR="$(mktemp -d)"
  cp -R "$APP_PATH" "$TMP_DMG_DIR/"
  ln -sf /Applications "$TMP_DMG_DIR/Applications"
  rm -f "$DMG_PATH"
  hdiutil create -volname "NeuroFlow" -srcfolder "$TMP_DMG_DIR" -ov -format UDZO "$DMG_PATH"
  rm -rf "$TMP_DMG_DIR"
fi
echo ""

echo "========================================"
echo "  Build Complete"
echo "========================================"
echo "App: $APP_PATH"
if [[ -n "${DMG_PATH}" && -f "$DMG_PATH" ]]; then
  echo "DMG: $DMG_PATH"
fi
echo "Note: unsigned internal test — see packaging/macos/OPEN-ON-MAC.md"