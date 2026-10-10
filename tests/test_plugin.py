import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_plugin_manifests_are_valid_json():
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert plugin["name"] == "safe-vibe"
    assert market["plugins"][0]["name"] == plugin["name"]


def test_plugin_hooks_point_at_real_scripts():
    data = json.loads((ROOT / "hooks" / "hooks.json").read_text())
    for entry in data["hooks"]["PreToolUse"]:
        for hook in entry["hooks"]:
            script = hook["command"].split("/hooks/")[1].rstrip('"')
            assert (ROOT / "hooks" / script).exists()
