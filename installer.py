#!/usr/bin/env python3
"""Install or remove the safe-vibe hooks in a Claude Code settings.json.

  installer.py install   [--project [DIR]] [--no-focus] [--with-focus]
  installer.py uninstall [--project [DIR]]

User scope (default) edits ~/.claude/settings.json. Project scope edits
<DIR>/.claude/settings.json (DIR defaults to the current directory).
Every write makes a timestamped backup first. Running it twice changes
nothing the second time. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARKER = "safe-vibe/hooks/"
HOOKS = [
    ("guard.py", True),
    ("pull_before_push.py", True),
    ("no_focus_steal.py", False),  # macOS only by default
]
SUPPORT = ["common.py"]


def settings_path(base: Path) -> Path:
    return base / "settings.json"


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as exc:
        sys.exit(f"safe-vibe: {path} is not valid JSON ({exc}). Nothing was changed.")
    if not isinstance(data, dict):
        sys.exit(f"safe-vibe: {path} is not a JSON object. Nothing was changed.")
    return data


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = path.with_name(f"{path.name}.safe-vibe-backup-{stamp}")
        shutil.copy2(path, backup)
        print(f"  backup: {backup}")
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def is_ours(entry: dict) -> bool:
    return any(MARKER in h.get("command", "") for h in entry.get("hooks", []))


def command_for(scope_project: bool, base: Path, script: str) -> str:
    if scope_project:
        return f'python3 "$CLAUDE_PROJECT_DIR/.claude/{MARKER}{script}"'
    return f'python3 "{base}/{MARKER}{script}"'


def install(args) -> None:
    project = args.project is not None
    base = (Path(args.project).resolve() / ".claude") if project else Path.home() / ".claude"
    want_focus = args.with_focus or (platform.system() == "Darwin" and not args.no_focus)
    chosen = [name for name, default in HOOKS if name != "no_focus_steal.py" or want_focus]

    hooks_dir = base / "safe-vibe" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    for name in chosen + SUPPORT:
        shutil.copy2(HERE / "hooks" / name, hooks_dir / name)
        (hooks_dir / name).chmod(0o755)

    config_dir = (Path(args.project).resolve() if project else Path.home() / ".config" / "safe-vibe")
    config_file = config_dir / "safe-vibe.toml"
    if not config_file.exists() and not (config_dir / "safe-vibe.json").exists():
        config_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HERE / "examples" / "safe-vibe.toml", config_file)
        print(f"  config: {config_file} (edit this to add your own rules)")

    path = settings_path(base)
    data = load(path)
    before = json.dumps(data, sort_keys=True)
    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
    pre[:] = [e for e in pre if not is_ours(e)]  # replace, so reruns never duplicate
    pre.append({
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": command_for(project, base, name)} for name in chosen],
    })
    if json.dumps(data, sort_keys=True) == before:
        print("safe-vibe: already installed, nothing to change.")
        return
    save(path, data)
    print(f"safe-vibe: installed {', '.join(chosen)} into {path}")
    print("  Restart Claude Code (or open /hooks) to pick them up.")


def uninstall(args) -> None:
    project = args.project is not None
    base = (Path(args.project).resolve() / ".claude") if project else Path.home() / ".claude"
    path = settings_path(base)
    if path.exists():
        data = load(path)
        pre = data.get("hooks", {}).get("PreToolUse", [])
        kept = [e for e in pre if not is_ours(e)]
        if len(kept) != len(pre):
            if kept:
                data["hooks"]["PreToolUse"] = kept
            else:
                del data["hooks"]["PreToolUse"]
                if not data["hooks"]:
                    del data["hooks"]
            save(path, data)
            print(f"safe-vibe: removed the hook entries from {path}")
        else:
            print("safe-vibe: no hook entries found in settings.")
    support = base / "safe-vibe"
    if support.is_dir():
        shutil.rmtree(support)
        print(f"  deleted {support}")
    print("  Your safe-vibe.toml was left alone. Delete it yourself if you want it gone.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["install", "uninstall"])
    parser.add_argument("--project", nargs="?", const=".", default=None, metavar="DIR")
    parser.add_argument("--no-focus", action="store_true", help="skip the macOS focus hook")
    parser.add_argument("--with-focus", action="store_true", help="install the focus hook on non-macOS too")
    args = parser.parse_args()
    (install if args.action == "install" else uninstall)(args)


if __name__ == "__main__":
    main()
