#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
THESIS_DIR="$ROOT_DIR/thesis"
BUILD_DIR="$THESIS_DIR/build"
PDF_FILE="$BUILD_DIR/main.pdf"

if ! command -v tectonic >/dev/null 2>&1; then
  echo "Error: tectonic is not installed." >&2
  echo "Install it with: sudo pacman -S tectonic" >&2
  exit 1
fi

cd "$THESIS_DIR"
mkdir -p "$BUILD_DIR"
tectonic --outdir "$BUILD_DIR" main.tex

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$PDF_FILE" >/dev/null 2>&1 &
else
  echo "PDF built at: $PDF_FILE"
fi
