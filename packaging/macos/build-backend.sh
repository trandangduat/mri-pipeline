#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${1:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
SPEC_PATH="$SCRIPT_DIR/neuroflow-backend.spec"

echo "=== Building neuroflow-backend for macOS (one-dir) ==="

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

INTERNAL_ROOT="$PROJECT_ROOT/dist/neuroflow-backend/_internal"

# Modern cryptography (>=42) requires OpenSSL >=3.2 (specifically _SSL_get0_group_name).
# On macOS runners, Python toolcache bundles OpenSSL 3.0.0 without this symbol.
# Ensure Homebrew OpenSSL 3 (3.2+) dylibs are copied into _internal so cryptography works everywhere.
OPENSSL_PREFIX=""
if command -v brew >/dev/null 2>&1; then
  OPENSSL_PREFIX="$(brew --prefix openssl@3 2>/dev/null || true)"
fi
if [[ -z "$OPENSSL_PREFIX" || ! -f "$OPENSSL_PREFIX/lib/libssl.3.dylib" ]]; then
  if [[ -f "/usr/local/opt/openssl@3/lib/libssl.3.dylib" ]]; then
    OPENSSL_PREFIX="/usr/local/opt/openssl@3"
  elif [[ -f "/opt/homebrew/opt/openssl@3/lib/libssl.3.dylib" ]]; then
    OPENSSL_PREFIX="/opt/homebrew/opt/openssl@3"
  fi
fi

if [[ -n "$OPENSSL_PREFIX" && -f "$OPENSSL_PREFIX/lib/libssl.3.dylib" ]]; then
  echo "Syncing OpenSSL 3 dylibs from $OPENSSL_PREFIX to $INTERNAL_ROOT..."
  cp -f "$OPENSSL_PREFIX/lib/libssl.3.dylib" "$INTERNAL_ROOT/libssl.3.dylib"
  cp -f "$OPENSSL_PREFIX/lib/libcrypto.3.dylib" "$INTERNAL_ROOT/libcrypto.3.dylib"
  chmod 755 "$INTERNAL_ROOT/libssl.3.dylib" "$INTERNAL_ROOT/libcrypto.3.dylib"
fi

if [[ -f "$INTERNAL_ROOT/libssl.3.dylib" ]]; then
  if strings "$INTERNAL_ROOT/libssl.3.dylib" | grep -q "SSL_get0_group_name"; then
    echo "Verified: $INTERNAL_ROOT/libssl.3.dylib exports SSL_get0_group_name."
  else
    echo "ERROR: $INTERNAL_ROOT/libssl.3.dylib does NOT export SSL_get0_group_name!" >&2
    exit 1
  fi
fi

for required_resource in \
  "$INTERNAL_ROOT/normalize_volumes.py" \
  "$INTERNAL_ROOT/pipeline/job_worker.py" \
  "$INTERNAL_ROOT/info/subcortical_volume_feats.txt" \
  "$INTERNAL_ROOT/configs/neuroflow"; do
  if [[ ! -e "$required_resource" ]]; then
    echo "Bundled backend is missing required _internal resource: $required_resource" >&2
    exit 1
  fi
done

echo "Running standalone diagnostic check on bundled backend..."
"$OUTPUT_EXE" check

SMOKE_PORT=18765
SMOKE_TOKEN="$($PYTHON -c 'import secrets; print(secrets.token_urlsafe(32))')"
SMOKE_LOG="$(mktemp "${TMPDIR:-/tmp}/neuroflow-backend-smoke.XXXXXX.log")"
SMOKE_CAPABILITIES="$(mktemp "${TMPDIR:-/tmp}/neuroflow-capabilities.XXXXXX.json")"
NEUROFLOW_API_TOKEN="$SMOKE_TOKEN" "$OUTPUT_EXE" server --host 127.0.0.1 --port "$SMOKE_PORT" >"$SMOKE_LOG" 2>&1 &
BACKEND_PID=$!
cleanup_smoke() {
  kill "$BACKEND_PID" 2>/dev/null || true
  rm -f "$SMOKE_LOG" "$SMOKE_CAPABILITIES"
}
trap cleanup_smoke EXIT
ready=false
for _ in $(seq 1 20); do
  if curl -fsS -H "Authorization: Bearer $SMOKE_TOKEN" "http://127.0.0.1:$SMOKE_PORT/capabilities/runtime" >"$SMOKE_CAPABILITIES"; then
    ready=true
    break
  fi
  sleep 0.25
done
if [[ "$ready" != true ]]; then
  cat "$SMOKE_LOG" >&2 || true
  echo "Bundled backend did not provide authenticated capabilities." >&2
  exit 1
fi
if ! curl -fsS -H "Authorization: Bearer $SMOKE_TOKEN" "http://127.0.0.1:$SMOKE_PORT/metadata" \
  | grep -Eq '"project_root"[[:space:]]*:[[:space:]]*".*_internal"'; then
  echo "Bundled backend did not resolve the PyInstaller _internal resource root." >&2
  exit 1
fi
if [[ "$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:$SMOKE_PORT/capabilities/runtime")" != "401" ]]; then
  echo "Bundled backend accepted an unauthenticated capabilities request." >&2
  exit 1
fi
grep -q '"id": "paramiko"' "$SMOKE_CAPABILITIES"
grep -A3 '"id": "paramiko"' "$SMOKE_CAPABILITIES" | grep -q '"ok": true'
