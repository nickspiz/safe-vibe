import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def sh(script, home, *args, cwd=None):
    env = {**os.environ, "HOME": str(home)}
    return subprocess.run(["bash", str(ROOT / script), *args], capture_output=True, text=True, env=env, cwd=cwd)


@pytest.fixture()
def home(tmp_path):
    h = tmp_path / "home"
    (h / ".claude").mkdir(parents=True)
    return h


def pre_entries(settings_file):
    return json.loads(settings_file.read_text())["hooks"]["PreToolUse"]


def test_fresh_install(home):
    done = sh("install.sh", home, "--with-focus")
    assert done.returncode == 0, done.stderr
    entries = pre_entries(home / ".claude" / "settings.json")
    cmds = [h["command"] for h in entries[0]["hooks"]]
    assert len(cmds) == 3 and all("safe-vibe/hooks/" in c for c in cmds)
    assert (home / ".claude/safe-vibe/hooks/guard.py").exists()
    assert (home / ".claude/safe-vibe/hooks/common.py").exists()
    assert (home / ".config/safe-vibe/safe-vibe.toml").exists()


def test_keeps_existing_settings_and_backs_up(home):
    settings = home / ".claude" / "settings.json"
    original = {"model": "opus", "hooks": {"PreToolUse": [
        {"matcher": "Write", "hooks": [{"type": "command", "command": "echo mine"}]}],
        "Stop": [{"hooks": [{"type": "command", "command": "echo bye"}]}]}}
    settings.write_text(json.dumps(original))
    assert sh("install.sh", home).returncode == 0
    data = json.loads(settings.read_text())
    assert data["model"] == "opus" and data["hooks"]["Stop"] == original["hooks"]["Stop"]
    assert data["hooks"]["PreToolUse"][0] == original["hooks"]["PreToolUse"][0]
    backups = list((home / ".claude").glob("settings.json.safe-vibe-backup-*"))
    assert len(backups) == 1 and json.loads(backups[0].read_text()) == original


def test_idempotent(home):
    sh("install.sh", home)
    first = (home / ".claude/settings.json").read_text()
    done = sh("install.sh", home)
    assert "already installed" in done.stdout
    assert (home / ".claude/settings.json").read_text() == first
    assert len(pre_entries(home / ".claude/settings.json")) == 1


def test_uninstall_restores_other_hooks(home):
    settings = home / ".claude" / "settings.json"
    mine = {"matcher": "Write", "hooks": [{"type": "command", "command": "echo mine"}]}
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [mine]}}))
    sh("install.sh", home)
    done = sh("uninstall.sh", home)
    assert done.returncode == 0
    assert json.loads(settings.read_text()) == {"hooks": {"PreToolUse": [mine]}}
    assert not (home / ".claude/safe-vibe").exists()
    assert (home / ".config/safe-vibe/safe-vibe.toml").exists()  # user config stays


def test_uninstall_cleans_empty_hooks(home):
    sh("install.sh", home)
    sh("uninstall.sh", home)
    assert json.loads((home / ".claude/settings.json").read_text()) == {}


def test_invalid_json_is_left_untouched(home):
    settings = home / ".claude" / "settings.json"
    settings.write_text("{ nope")
    done = sh("install.sh", home)
    assert done.returncode != 0 and "not valid JSON" in done.stderr
    assert settings.read_text() == "{ nope"


def test_project_scope(home, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    done = sh("install.sh", home, "--project", str(proj))
    assert done.returncode == 0, done.stderr
    entries = pre_entries(proj / ".claude" / "settings.json")
    assert "$CLAUDE_PROJECT_DIR/.claude/safe-vibe/hooks/guard.py" in entries[0]["hooks"][0]["command"]
    assert (proj / ".claude/safe-vibe/hooks/guard.py").exists()
    assert not (home / ".claude/settings.json").exists()
    assert (proj / "safe-vibe.toml").exists()


def test_installed_hook_runs_end_to_end(home):
    sh("install.sh", home)
    cmd = pre_entries(home / ".claude/settings.json")[0]["hooks"][0]["command"]
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git reset --hard"}, "cwd": str(home)})
    done = subprocess.run(cmd, shell=True, input=payload, capture_output=True, text=True,
                          env={**os.environ, "HOME": str(home)})
    assert done.returncode == 2 and "safe-vibe blocked" in done.stderr
