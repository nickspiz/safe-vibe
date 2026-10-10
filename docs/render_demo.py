#!/usr/bin/env python3
"""Rebuild docs/demo.gif by running docs/try.sh for real and drawing the output.

  python3 docs/render_demo.py            (needs Pillow: pip install pillow)

docs/demo.tape is the same demo for charmbracelet/vhs, if you prefer that.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import termgif as t  # noqa: E402

HERE = Path(__file__).resolve().parent
COMMANDS = [
    "git push --force origin main",
    'psql -c "DROP TABLE users;"',
    "git status",
]


def run(cmd):
    with tempfile.TemporaryDirectory() as d:
        env = {"PATH": os.environ["PATH"], "HOME": d, "CLAUDE_PROJECT_DIR": d}
        r = subprocess.run(["bash", str(HERE / "try.sh"), cmd], capture_output=True, text=True, env=env, cwd=d)
    return r.stdout.rstrip("\n").split("\n")


def main():
    term = t.Term(cols=88, rows=19, size=17, title="demo: safe-vibe guard")
    steps = []
    for cmd in COMMANDS:
        steps.append(("type", f"docs/try.sh {cmd}"))
        lines = run(cmd)
        segs = []
        for ln in lines:
            if ln.startswith("agent runs:"):
                segs.append([("agent runs: ", t.DIM), (ln[len("agent runs: "):], t.FG)])
            elif ln.startswith("exit 2"):
                segs.append([(ln, t.RED)])
            elif ln.startswith("exit 0"):
                segs.append([(ln, t.GREEN)])
            else:
                segs.extend(t.colorize_block(ln))
        steps.append(("outc", segs))
        steps.append(("pause", 1.6))
        if cmd.startswith("psql"):
            steps.append(("clear",))
    term.run(steps)
    term.save(HERE / "demo.gif")


if __name__ == "__main__":
    main()
