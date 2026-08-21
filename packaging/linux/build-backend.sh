#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${1:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
SPEC_PATH="$SCRIPT_DIR/neuroflow-backend.spec"

echo "=== Building neuroflow-backend for Linux (one-dir) ==="

if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  PYTHON="$PROJECT_ROOT/.venv/bin/python"
else
  PYTHON="python3"
fi

echo "Using Python: $PYTHON"

if ! "$PYTHON" -m PyInstaller --version >/dev/null 2>&1; then
  echo "Installing PyInstaller..."
  "$PYTHON" -m pip install pyinstaller --quiet
fi

echo "Installing project dependencies..."
"$PYTHON" -m pip install -r "$PROJECT_ROOT/requirements.txt" --quiet

echo "Running PyInstaller..."
"$PYTHON" -m PyInstaller "$SPEC_PATH" --noconfirm --clean --distpath "$PROJECT_ROOT/dist" --workpath "$PROJECT_ROOT/build"

OUTPUT_EXE="$PROJECT_ROOT/dist/neuroflow-backend/neuroflow-backend"
if [[ ! -x "$OUTPUT_EXE" ]]; then
  echo "Expected output not found or not executable: $OUTPUT_EXE" >&2
  exit 1
fi

echo "Build succeeded: $OUTPUT_EXE"
