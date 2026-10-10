import json
import subprocess

import pytest


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                   cwd=cwd, check=True, capture_output=True)


def commit_all(cwd, msg):
    git(cwd, "add", ".")
    git(cwd, "commit", "-q", "-m", msg)


@pytest.fixture()
def repos(tmp_path):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    a, b = tmp_path / "a", tmp_path / "b"
    git(tmp_path, "clone", "-q", str(remote), str(a))
    git(a, "checkout", "-q", "-b", "main")
    (a / "one.txt").write_text("1\n")
    (a / "shared.txt").write_text("base\n")
    commit_all(a, "init")
    git(a, "push", "-q", "-u", "origin", "main")
    git(tmp_path, "clone", "-q", str(remote), str(b))
    return a, b


def test_not_behind_passes_silently(run, repos):
    a, _ = repos
    code, err, out = run("pull_before_push.py", "git push", cwd=a)
    assert code == 0 and out == ""


def test_behind_gets_rebased(run, repos):
    a, b = repos
    (b / "two.txt").write_text("2\n")
    commit_all(b, "two")
    git(b, "push", "-q")
    (a / "three.txt").write_text("3\n")
    commit_all(a, "three")
    (a / "dirty.txt").write_text("uncommitted\n")  # autostash must protect this
    code, err, out = run("pull_before_push.py", "git push origin main", cwd=a)
    assert code == 0
    assert "rebased" in json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert (a / "two.txt").exists() and (a / "three.txt").exists() and (a / "dirty.txt").exists()


def test_conflict_aborts_cleanly(run, repos):
    a, b = repos
    (b / "shared.txt").write_text("from b\n")
    commit_all(b, "b edit")
    git(b, "push", "-q")
    (a / "shared.txt").write_text("from a\n")
    commit_all(a, "a edit")
    code, err, _ = run("pull_before_push.py", "git push", cwd=a)
    assert code == 2
    assert "aborted the rebase" in err and "Instead:" in err
    status = subprocess.run(["git", "status"], cwd=a, capture_output=True, text=True).stdout
    assert "rebase in progress" not in status
    assert (a / "shared.txt").read_text() == "from a\n"


def test_ignores_other_commands(run, repos):
    a, _ = repos
    assert run("pull_before_push.py", "git status", cwd=a)[0] == 0


def test_force_push_is_left_alone(run, repos):
    a, b = repos
    (b / "two.txt").write_text("2\n")
    commit_all(b, "two")
    git(b, "push", "-q")
    code, _, out = run("pull_before_push.py", "git push --force", cwd=a)
    assert code == 0 and out == ""


def test_no_upstream_is_fine(run, repos):
    a, _ = repos
    git(a, "checkout", "-q", "-b", "newbranch")
    assert run("pull_before_push.py", "git push -u origin newbranch", cwd=a)[0] == 0


def test_not_a_repo_fails_open(run, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert run("pull_before_push.py", "git push", cwd=plain)[0] == 0
