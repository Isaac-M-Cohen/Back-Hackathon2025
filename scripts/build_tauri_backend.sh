#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-/opt/homebrew/Caskroom/miniconda/base/envs/qt/bin/python}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT_DIR/webui/src-tauri/bin"
WORK_DIR="$ROOT_DIR/build/tauri_backend"

mkdir -p "$OUT_DIR"

"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name backend \
  --distpath "$OUT_DIR" \
  --workpath "$WORK_DIR" \
  --specpath "$WORK_DIR" \
  "$ROOT_DIR/scripts/tauri_backend.py"

echo "Built Tauri backend sidecar at $OUT_DIR/backend"
