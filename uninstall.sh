#!/usr/bin/env bash
# Removes the safe-vibe hooks. Usage: ./uninstall.sh [--project DIR]
# Your settings.json is backed up first and your other hooks are left alone.
set -euo pipefail

command -v python3 >/dev/null || { echo "safe-vibe needs python3." >&2; exit 1; }

SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -z "$SRC" ] || [ ! -f "$SRC/installer.py" ]; then
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  curl -fsSL "https://github.com/nickspiz/safe-vibe/archive/refs/heads/main.tar.gz" | tar -xz -C "$TMP" --strip-components=1
  SRC="$TMP"
fi

python3 "$SRC/installer.py" uninstall "$@"
