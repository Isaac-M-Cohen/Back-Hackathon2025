#!/usr/bin/env bash
# Branch summary (video-module):
# - Tauri app + backend sidecar bundling
# - Settings API + UI, including theme toggle
# - Preferences menu + About metadata wiring
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEBUI_DIR="$ROOT_DIR/webui"
TAURI_DIR="$WEBUI_DIR/src-tauri"

TARGET_TRIPLE="${TAURI_TARGET_TRIPLE:-}"
if [[ -z "$TARGET_TRIPLE" ]]; then
  if command -v rustc >/dev/null 2>&1; then
    TARGET_TRIPLE="$(rustc -vV | awk -F': ' '/^host:/ {print $2}')"
  else
    ARCH="$(uname -m)"
    TARGET_TRIPLE="${ARCH}-apple-darwin"
  fi
fi

BACKEND_SRC="$TAURI_DIR/bin/backend-${TARGET_TRIPLE}"
BUNDLE_DIR="$TAURI_DIR/target/release/bundle/macos/Easy.app/Contents/Resources/bin"

if [[ ! -f "$BACKEND_SRC" ]]; then
  echo "Missing backend sidecar at $BACKEND_SRC" >&2
  exit 1
fi

mkdir -p "$BUNDLE_DIR"
cp -f "$BACKEND_SRC" "$BUNDLE_DIR/"
chmod +x "$BUNDLE_DIR/backend-${TARGET_TRIPLE}" || true
echo "Bundled backend sidecar into $BUNDLE_DIR"
