#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SRC_DIR="$ROOT_DIR/skills/paper-interpretation"
DEST_ROOT="${CODEX_HOME:-$HOME/.codex}/skills"
DEST_DIR="$DEST_ROOT/paper-interpretation"
FORCE=0

if [ "${1:-}" = "--force" ]; then
  FORCE=1
elif [ "${1:-}" != "" ]; then
  echo "Usage: ./install.sh [--force]" >&2
  exit 2
fi

if [ ! -f "$SRC_DIR/SKILL.md" ]; then
  echo "Cannot find skill at $SRC_DIR" >&2
  exit 1
fi

mkdir -p "$DEST_ROOT"

if [ -e "$DEST_DIR" ]; then
  if [ "$FORCE" != "1" ]; then
    echo "Destination already exists: $DEST_DIR" >&2
    echo "Run ./install.sh --force to replace it." >&2
    exit 1
  fi
  rm -rf "$DEST_DIR"
fi

cp -R "$SRC_DIR" "$DEST_DIR"
find "$DEST_DIR" -name "__pycache__" -type d -prune -exec rm -rf {} +
find "$DEST_DIR" -name ".DS_Store" -type f -delete

echo "Installed paper-interpretation skill to:"
echo "  $DEST_DIR"
echo "Restart Codex to pick up the skill."
