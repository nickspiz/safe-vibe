import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent / "hooks"


@pytest.fixture()
def run(tmp_path):
    """Run a hook with a Bash payload. Returns (exit_code, stderr, stdout)."""
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()

    def _run(hook, command, cwd=None, env=None, tool="Bash"):
        payload = {"tool_name": tool, "tool_input": {"command": command}, "cwd": str(cwd or project)}
        full_env = {k: v for k, v in os.environ.items() if not k.startswith(("SAFE_VIBE", "CLAUDE_"))}
        full_env.update({"HOME": str(home), "CLAUDE_PROJECT_DIR": str(cwd or project)})
        full_env.update(env or {})
        done = subprocess.run([sys.executable, str(HOOKS / hook)], input=json.dumps(payload),
                              capture_output=True, text=True, env=full_env, timeout=120)
        return done.returncode, done.stderr, done.stdout

    _run.project = project
    _run.home = home
    return _run
