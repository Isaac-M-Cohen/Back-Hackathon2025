#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT_DIR/webui/src-tauri/bin"
WORK_DIR="$ROOT_DIR/build/tauri_backend"

mkdir -p "$OUT_DIR"

TARGET_TRIPLE="${TAURI_TARGET_TRIPLE:-}"
if [[ -z "$TARGET_TRIPLE" ]]; then
  if command -v rustc >/dev/null 2>&1; then
    TARGET_TRIPLE="$(rustc -vV | awk -F': ' '/^host:/ {print $2}')"
  else
    ARCH="$(uname -m)"
    TARGET_TRIPLE="${ARCH}-apple-darwin"
  fi
fi

"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --paths "$ROOT_DIR" \
  --hidden-import api \
  --hidden-import api.server \
  --name "backend-${TARGET_TRIPLE}" \
  --distpath "$OUT_DIR" \
  --workpath "$WORK_DIR" \
  --specpath "$WORK_DIR" \
  "$ROOT_DIR/scripts/tauri_backend.py"

if [[ -f "$OUT_DIR/backend-${TARGET_TRIPLE}" ]]; then
  chmod +x "$OUT_DIR/backend-${TARGET_TRIPLE}" || true
fi

echo "Built Tauri backend sidecar at $OUT_DIR/backend-${TARGET_TRIPLE}"
