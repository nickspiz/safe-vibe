import pytest

BLOCKED = [
    "open -a Safari",
    "open https://example.com",
    "open ./report.html",
    "osascript -e 'tell application \"Finder\" to activate'",
    "osascript -e 'tell app \"Terminal\" to activate'",
    "say done",
    "/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome https://example.com",
    "google-chrome https://example.com",
    "firefox https://example.com",
    "chromium --user-data-dir=/tmp/p",
    "npx playwright test --headed",
    "node run.js --headless=false",
]

ALLOWED = [
    "open -g https://example.com",
    "google-chrome --headless=new --dump-dom https://example.com",
    "firefox --headless https://example.com",
    "/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --headless=new --screenshot",
    "chromedriver --port=9515",
    "npx playwright test",
    "osascript -e 'display notification \"hi\"'",
    "ls ~/Documents",
    'git commit -m "docs: say hello"',
    "echo open the door",
]


@pytest.mark.parametrize("cmd", BLOCKED)
def test_blocks(run, cmd):
    code, err, _ = run("no_focus_steal.py", cmd)
    assert code == 2, cmd
    assert "Instead:" in err


@pytest.mark.parametrize("cmd", ALLOWED)
def test_allows(run, cmd):
    assert run("no_focus_steal.py", cmd)[0] == 0, cmd


def test_off_switch(run):
    assert run("no_focus_steal.py", "say hi", env={"SAFE_VIBE_OFF": "1"})[0] == 0


def test_config_allow(run):
    (run.project / "safe-vibe.toml").write_text('[focus]\nallow = ["^open -a Xcode"]\n')
    assert run("no_focus_steal.py", "open -a Xcode")[0] == 0
    assert run("no_focus_steal.py", "open -a Safari")[0] == 2


def test_config_disable_say(run):
    (run.project / "safe-vibe.toml").write_text('[focus]\ndisable = ["say"]\n')
    assert run("no_focus_steal.py", "say hi")[0] == 0
