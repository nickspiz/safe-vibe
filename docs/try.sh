#!/usr/bin/env bash
# Show what the guard hook says about a command, the way Claude Code would see it.
#   docs/try.sh git push --force origin main
here="$(cd "$(dirname "$0")/.." && pwd)"
cmd="$*"
payload="$(python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","tool_input":{"command":sys.argv[1]}}))' "$cmd")"
echo "agent runs: $cmd"
out="$(printf '%s' "$payload" | python3 "$here/hooks/guard.py" 2>&1)"
code=$?
if [ "$code" -eq 2 ]; then
  echo "$out"
  echo "exit 2: command not run"
else
  echo "exit $code: allowed"
fi
