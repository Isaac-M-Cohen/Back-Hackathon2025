#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"
"$PYTHON_BIN" -m PyInstaller --noconfirm pyinstaller_easy.spec
echo "Built dist/easy.app"




