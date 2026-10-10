#!/usr/bin/env python3
"""safe-vibe no-focus-steal (macOS): keep the agent from grabbing your screen.

Blocks commands that pull a window to the front or make noise:
`open` (apps, URLs, files), AppleScript `activate`, `say`, and browsers
started without a headless flag.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

BROWSERS = {"chrome", "google chrome", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
            "firefox", "brave", "brave-browser", "msedge", "microsoft-edge"}
OSA_FRONT = re.compile(r"\bactivate\b|\bfrontmost\b|\breopen\b|\bkeystroke\b|\bkey code\b", re.I)
HEADED_FLAGS = re.compile(r"--headed\b|--headless=(false|0)\b|headless\s*[:=]\s*false", re.I)


def is_headless(segment: str) -> bool:
    return bool(re.search(r"(?<![\w-])-{1,2}headless\b(?!=(false|0))", segment, re.I))


def main() -> int:
    if os.environ.get("SAFE_VIBE_OFF") == "1":
        return 0
    payload = common.read_payload()
    command = common.bash_command(payload)
    if not command:
        return 0
    cfg = common.load_config(common.project_dir(payload)).get("focus", {})
    disabled = set(cfg.get("disable", []))
    allow = [re.compile(p, re.I) for p in cfg.get("allow", [])]

    for segment in common.split_segments(command):
        if any(p.search(segment) for p in allow):
            continue
        toks = common.strip_prefix(common.tokens(segment))
        prog = common.program(toks)
        if not prog:
            continue
        sub, _ = common.git_subcommand(toks)
        if prog == "git" and sub:
            continue

        if prog == "open" and "open" not in disabled and "-g" not in toks:
            common.block(
                "open " + " ".join(toks[1:4]),
                "on macOS `open` brings the app or browser window to the front and interrupts whatever you are doing.",
                "Print the path or URL for the user instead. If you must launch it, use `open -g` (stays in the background).",
            )
        if prog == "say" and "say" not in disabled:
            common.block(
                "say",
                "it speaks out loud on the user's machine.",
                "Write the message in the chat instead.",
            )
        if prog in ("osascript", "osacompile") and "osascript" not in disabled and OSA_FRONT.search(segment):
            common.block(
                "osascript that activates an app or presses keys",
                "it moves focus to another app, or types into whatever is in front.",
                "Skip the UI scripting. Use a command-line or API route, or ask the user.",
            )
        if "headed" not in disabled:
            is_browser = prog in BROWSERS
            if HEADED_FLAGS.search(segment) or (is_browser and not is_headless(segment)):
                common.block(
                    "a browser started in headed mode",
                    "a visible browser window pops up over the user's work.",
                    "Add --headless (for Chrome or Chromium: --headless=new), or use a headless test runner.",
                )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        sys.stderr.write(f"safe-vibe no-focus-steal error (command allowed): {exc}\n")
        sys.exit(0)
