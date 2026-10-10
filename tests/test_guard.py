import subprocess
import sys

import pytest

from conftest import HOOKS

BLOCKED = [
    'psql -c "DROP TABLE users"',
    'mysql -e "drop database app"',
    'psql -c "TRUNCATE TABLE orders"',
    'psql -c "DELETE FROM users;"',
    'psql -c "delete from users"',
    "rm -rf /",
    "rm -rf ~",
    "rm -rf ../other",
    "rm -fr $HOME/stuff",
    "rm -rf $BUILD_DIR",
    "sudo rm -r /etc/foo",
    "git push --force origin main",
    "git push -f origin master",
    "git push origin +main",
    "git push --force-with-lease origin main",
    "git reset --hard",
    "git reset --hard HEAD~3",
    "git -C /tmp/x reset --hard",
    "docker compose down",
    "docker-compose down -v",
    "docker compose -f prod.yml down",
    "terraform destroy",
    "terraform destroy -auto-approve",
    "kubectl delete pod web-1",
    "kubectl -n prod delete deployment api",
    "ls && git reset --hard",
]

ALLOWED = [
    "ls -la",
    "rm -rf node_modules",
    "rm -rf ./build",
    "rm file.txt",
    "rm -rf /tmp/scratch",
    'psql -c "DELETE FROM users WHERE id = 4"',
    'psql -c "SELECT * FROM users"',
    "git push origin feature/x",
    "git push --force origin feature/x",
    "git reset --soft HEAD~1",
    "git status",
    "docker compose up -d",
    "docker compose stop web",
    "terraform plan",
    "kubectl get pods",
    'git commit -m "docs: explain why we never DROP TABLE in prod"',
    'grep -rn "DROP TABLE" migrations/',
    "echo hello",
]


@pytest.mark.parametrize("cmd", BLOCKED)
def test_blocks(run, cmd):
    code, err, _ = run("guard.py", cmd)
    assert code == 2, cmd
    assert "safe-vibe blocked" in err and "Why:" in err and "Instead:" in err


@pytest.mark.parametrize("cmd", ALLOWED)
def test_allows(run, cmd):
    code, err, _ = run("guard.py", cmd)
    assert code == 0, (cmd, err)


def test_ignores_other_tools(run):
    assert run("guard.py", "rm -rf /", tool="Read")[0] == 0


def test_bad_payload_fails_open():
    done = subprocess.run([sys.executable, str(HOOKS / "guard.py")], input="not json",
                          capture_output=True, text=True)
    assert done.returncode == 0


def test_rm_inside_project_with_absolute_path(run):
    assert run("guard.py", f"rm -rf {run.project / 'dist'}")[0] == 0
    assert run("guard.py", f"rm -rf {run.project}")[0] == 2


def test_off_switch(run):
    assert run("guard.py", "git reset --hard", env={"SAFE_VIBE_OFF": "1"})[0] == 0


def test_prod_host_from_toml(run):
    (run.project / "safe-vibe.toml").write_text('[prod]\nhosts = ["db.example.com"]\n')
    assert run("guard.py", "ssh root@db.example.com ls")[0] == 2
    assert run("guard.py", "psql -h db.example.com -c 'select 1'")[0] == 2
    assert run("guard.py", "ssh root@staging.example.com ls")[0] == 0
    assert run("guard.py", "ping db.example.com")[0] == 0


def test_prod_host_from_json(run):
    (run.project / "safe-vibe.json").write_text('{"prod": {"hosts": ["10.9.8.7"]}}')
    assert run("guard.py", "scp file root@10.9.8.7:/srv")[0] == 2


def test_custom_rule_and_message(run):
    (run.project / "safe-vibe.toml").write_text(
        '[[rule]]\nid = "no-deploy"\npattern = "npm run deploy"\n'
        'what = "a deploy"\nwhy = "deploys are manual here."\ninstead = "ask me."\n')
    code, err, _ = run("guard.py", "npm run deploy")
    assert code == 2 and "deploys are manual here." in err


def test_disable_rule_and_allow_pattern(run):
    (run.project / "safe-vibe.toml").write_text(
        '[guard]\ndisable = ["git-reset-hard"]\nallow = ["^docker compose -f test\\\\.yml down"]\n')
    assert run("guard.py", "git reset --hard")[0] == 0
    assert run("guard.py", "docker compose -f test.yml down")[0] == 0
    assert run("guard.py", "docker compose down")[0] == 2


def test_custom_protected_branch(run):
    (run.project / "safe-vibe.toml").write_text('[guard]\nprotected_branches = ["release"]\n')
    assert run("guard.py", "git push --force origin release")[0] == 2
    assert run("guard.py", "git push --force origin main")[0] == 0


def test_extra_rm_safe_path(run, tmp_path):
    scratch = tmp_path / "scratch"
    (run.project / "safe-vibe.toml").write_text(f'[guard]\nrm_safe_paths = ["{scratch}"]\n')
    assert run("guard.py", f"rm -rf {scratch}/cache")[0] == 0


def test_force_push_without_branch_uses_current(run):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=run.project, check=True)
    assert run("guard.py", "git push --force")[0] == 2
    subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=run.project, check=True)
    assert run("guard.py", "git push --force")[0] == 0
