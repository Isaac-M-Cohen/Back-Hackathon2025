#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT_DIR/webui/src-tauri/bin"
WORK_DIR="$ROOT_DIR/build/tauri_backend"

mkdir -p "$OUT_DIR"

"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --paths "$ROOT_DIR" \
  --hidden-import api \
  --hidden-import api.server \
  --name "backend" \
  --distpath "$OUT_DIR" \
  --workpath "$WORK_DIR" \
  --specpath "$WORK_DIR" \
  "$ROOT_DIR/scripts/tauri_backend.py"

BACKEND_PATH="$OUT_DIR/backend"
if [[ -f "$OUT_DIR/backend.exe" ]]; then
  BACKEND_PATH="$OUT_DIR/backend.exe"
fi

if [[ -f "$BACKEND_PATH" ]]; then
  chmod +x "$BACKEND_PATH" || true
fi

echo "Built Tauri backend sidecar at $BACKEND_PATH"
