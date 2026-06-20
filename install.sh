#!/usr/bin/env sh
set -eu

SKILL_NAME="paper-interpretation"
INSTALLER_VERSION="0.2.0"
DEFAULT_REPO="houyili/paper-interpretation-codex-skill"
DEFAULT_REF="main"

ACTION="install"
FORCE=0
WITH_DEPS=0
BACKUP=1
PURGE_BACKUPS=0
REPO="${PAPER_INTERPRETATION_REPO:-$DEFAULT_REPO}"
REF="${PAPER_INTERPRETATION_REF:-$DEFAULT_REF}"
DEST_ROOT="${CODEX_HOME:-$HOME/.codex}/skills"

usage() {
  cat <<'EOF'
Usage:
  ./install.sh [install|upgrade|uninstall|doctor] [options]

Actions:
  install      Install the paper-interpretation Codex skill. Default action.
  upgrade      Replace an existing installation with this version/ref.
  uninstall    Remove the installed skill after verifying it is this skill.
  doctor       Check installation, Python dependencies, and optional tools.

Options:
  --force            Replace an existing install when using "install".
  --with-deps        Run "python3 -m pip install -r requirements.txt".
  --no-backup        Do not keep a timestamped backup during replacement.
  --purge-backups    With uninstall, also remove timestamped backups.
  --dest PATH        Codex skills root. Default: ${CODEX_HOME:-$HOME/.codex}/skills
  --repo OWNER/REPO  GitHub repo for curl-pipe installs.
  --ref REF          Git ref for curl-pipe installs. Default: main
  -h, --help         Show this help.

One-line install:
  curl -fsSL https://raw.githubusercontent.com/houyili/paper-interpretation-codex-skill/main/install.sh | sh

One-line upgrade:
  curl -fsSL https://raw.githubusercontent.com/houyili/paper-interpretation-codex-skill/main/install.sh | sh -s -- upgrade

One-line uninstall:
  curl -fsSL https://raw.githubusercontent.com/houyili/paper-interpretation-codex-skill/main/install.sh | sh -s -- uninstall
EOF
}

if [ $# -gt 0 ]; then
  case "$1" in
    install|upgrade|uninstall|doctor)
      ACTION="$1"
      shift
      ;;
  esac
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --force)
      FORCE=1
      ;;
    --with-deps)
      WITH_DEPS=1
      ;;
    --no-backup)
      BACKUP=0
      ;;
    --purge-backups)
      PURGE_BACKUPS=1
      ;;
    --dest)
      shift
      [ $# -gt 0 ] || { echo "--dest requires a path" >&2; exit 2; }
      DEST_ROOT="$1"
      ;;
    --repo)
      shift
      [ $# -gt 0 ] || { echo "--repo requires OWNER/REPO" >&2; exit 2; }
      REPO="$1"
      ;;
    --ref)
      shift
      [ $# -gt 0 ] || { echo "--ref requires a git ref" >&2; exit 2; }
      REF="$1"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

DEST_DIR="$DEST_ROOT/$SKILL_NAME"
TMP_DIR=""
SRC_DIR=""
REQ_FILE=""

cleanup() {
  if [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT HUP INT TERM

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

script_root() {
  CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd
}

download_file() {
  url="$1"
  out="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$out"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$out" "$url"
  else
    echo "Need curl or wget to download $url" >&2
    exit 1
  fi
}

resolve_source() {
  root="$(script_root || pwd)"
  local_src="$root/skills/$SKILL_NAME"

  if [ -n "${PAPER_INTERPRETATION_SOURCE_DIR:-}" ]; then
    SRC_DIR="$PAPER_INTERPRETATION_SOURCE_DIR"
    REQ_FILE="$(dirname "$SRC_DIR")/../requirements.txt"
  elif [ -f "$local_src/SKILL.md" ]; then
    SRC_DIR="$local_src"
    REQ_FILE="$root/requirements.txt"
  else
    need_cmd tar
    TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/paper-interpretation-install.XXXXXX")"
    archive="$TMP_DIR/source.tar.gz"
    url="https://codeload.github.com/$REPO/tar.gz/$REF"
    echo "Downloading $REPO@$REF..."
    download_file "$url" "$archive"
    tar -xzf "$archive" -C "$TMP_DIR"
    top="$(find "$TMP_DIR" -mindepth 1 -maxdepth 1 -type d | sed -n '1p')"
    SRC_DIR="$top/skills/$SKILL_NAME"
    REQ_FILE="$top/requirements.txt"
  fi

  if [ ! -f "$SRC_DIR/SKILL.md" ]; then
    echo "Cannot find skill source at $SRC_DIR" >&2
    exit 1
  fi
}

verify_skill_dir() {
  skill_dir="$1"
  if [ ! -f "$skill_dir/SKILL.md" ]; then
    echo "Refusing to modify $skill_dir: SKILL.md is missing." >&2
    exit 1
  fi
  if ! grep -Eq '^name:[[:space:]]*paper-interpretation[[:space:]]*$' "$skill_dir/SKILL.md"; then
    echo "Refusing to modify $skill_dir: it is not the paper-interpretation skill." >&2
    exit 1
  fi
}

verify_installed_skill() {
  verify_skill_dir "$DEST_DIR"
}

remove_generated_files() {
  find "$1" -name "__pycache__" -type d -prune -exec rm -rf {} +
  find "$1" -name ".DS_Store" -type f -delete
}

install_deps() {
  if [ "$WITH_DEPS" != "1" ]; then
    return
  fi
  if [ ! -f "$REQ_FILE" ]; then
    echo "Cannot find requirements.txt near source; skipping dependency install." >&2
    return
  fi
  need_cmd python3
  python3 -m pip install -r "$REQ_FILE"
}

write_install_metadata() {
  installed_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  {
    echo "installer_version=$INSTALLER_VERSION"
    echo "repo=$REPO"
    echo "ref=$REF"
    echo "installed_at=$installed_at"
  } > "$DEST_DIR/.install-source"
}

install_or_upgrade() {
  resolve_source
  install_deps
  mkdir -p "$DEST_ROOT"

  if [ -e "$DEST_DIR" ]; then
    if [ "$ACTION" = "install" ] && [ "$FORCE" != "1" ]; then
      echo "Already installed: $DEST_DIR" >&2
      echo "Use './install.sh upgrade' or './install.sh install --force'." >&2
      exit 1
    fi
    verify_installed_skill
    if [ "$BACKUP" = "1" ]; then
      backup="$DEST_DIR.backup.$(date -u '+%Y%m%d%H%M%S')"
      mv "$DEST_DIR" "$backup"
      echo "Backed up previous install to:"
      echo "  $backup"
    else
      rm -rf "$DEST_DIR"
    fi
  fi

  cp -R "$SRC_DIR" "$DEST_DIR"
  remove_generated_files "$DEST_DIR"
  write_install_metadata

  echo "Installed $SKILL_NAME skill to:"
  echo "  $DEST_DIR"
  if [ -f "$DEST_DIR/VERSION" ]; then
    echo "Version: $(cat "$DEST_DIR/VERSION")"
  fi
  echo "Restart Codex to pick up the skill."
}

uninstall_skill() {
  if [ ! -e "$DEST_DIR" ]; then
    echo "$SKILL_NAME is not installed at:"
    echo "  $DEST_DIR"
  else
    verify_installed_skill
    rm -rf "$DEST_DIR"
    echo "Removed $SKILL_NAME from:"
    echo "  $DEST_DIR"
  fi

  if [ "$PURGE_BACKUPS" = "1" ]; then
    for backup in "$DEST_DIR".backup.*; do
      if [ -e "$backup" ]; then
        verify_skill_dir "$backup"
        rm -rf "$backup"
        echo "Removed backup:"
        echo "  $backup"
      fi
    done
  fi

  echo "Restart Codex to drop the skill from the UI."
}

doctor() {
  status=0
  echo "paper-interpretation installer: $INSTALLER_VERSION"
  echo "Codex skills root: $DEST_ROOT"

  if [ -f "$DEST_DIR/SKILL.md" ]; then
    echo "OK: skill installed at $DEST_DIR"
    if [ -f "$DEST_DIR/VERSION" ]; then
      echo "OK: installed version $(cat "$DEST_DIR/VERSION")"
    else
      echo "WARN: installed skill has no VERSION file"
    fi
  else
    echo "FAIL: skill is not installed at $DEST_DIR"
    status=1
  fi

  if command -v python3 >/dev/null 2>&1; then
    echo "OK: python3 $(python3 --version 2>&1)"
    if ! python3 - <<'PY'
import importlib.util
import sys

required = [
    ("fitz", "PyMuPDF"),
    ("pdfplumber", "pdfplumber"),
    ("PIL", "Pillow"),
]
missing = []
for module, package in required:
    if importlib.util.find_spec(module) is None:
        missing.append(package)
if missing:
    print("FAIL: missing Python packages: " + ", ".join(missing))
    print("Run: python3 -m pip install pymupdf pdfplumber Pillow")
    sys.exit(1)
print("OK: required Python packages are importable")
PY
    then
      status=1
    fi
  else
    echo "FAIL: python3 not found"
    status=1
  fi

  for cmd in rg pdflatex pdfinfo pdftoppm; do
    if command -v "$cmd" >/dev/null 2>&1; then
      echo "OK: optional command found: $cmd"
    else
      echo "WARN: optional command missing: $cmd"
    fi
  done

  return "$status"
}

case "$ACTION" in
  install|upgrade)
    install_or_upgrade
    ;;
  uninstall)
    uninstall_skill
    ;;
  doctor)
    doctor
    ;;
  *)
    echo "Unknown action: $ACTION" >&2
    usage >&2
    exit 2
    ;;
esac
