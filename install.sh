#!/usr/bin/env bash
# safe-vibe installer. Usage:
#   ./install.sh                  install for your user (~/.claude/settings.json)
#   ./install.sh --project .      install for one project (.claude/settings.json)
#   ./install.sh --no-focus       skip the macOS focus hook
# One line, no clone:
#   curl -fsSL https://raw.githubusercontent.com/nickspiz/safe-vibe/main/install.sh | bash
set -euo pipefail

command -v python3 >/dev/null || { echo "safe-vibe needs python3." >&2; exit 1; }

SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -z "$SRC" ] || [ ! -f "$SRC/installer.py" ]; then
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  curl -fsSL "https://github.com/nickspiz/safe-vibe/archive/refs/heads/main.tar.gz" | tar -xz -C "$TMP" --strip-components=1
  SRC="$TMP"
fi

python3 "$SRC/installer.py" install "$@"
