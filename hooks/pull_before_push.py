#!/usr/bin/env python3
"""safe-vibe pull-before-push: sync with the remote before `git push`.

If the remote branch moved ahead, run `git pull --rebase --autostash`
first. If that hits a conflict, abort the rebase so the working tree is
exactly as it was, block the push, and explain what happened.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

TIMEOUT = 60


def git(cwd: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=TIMEOUT)


def say(note: str) -> None:
    """Tell the agent what happened, without blocking."""
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": note}}))


def main() -> int:
    if os.environ.get("SAFE_VIBE_OFF") == "1":
        return 0
    payload = common.read_payload()
    command = common.bash_command(payload)
    if not command:
        return 0
    cwd = str(common.project_dir(payload))

    for segment in common.split_segments(command):
        toks = common.strip_prefix(common.tokens(segment))
        sub, args = common.git_subcommand(toks)
        if sub != "push":
            continue
        workdir = common.git_dir_option(toks) or cwd
        if any(a in ("-f", "--force") or a.startswith("--force") or a in ("--delete", "-d", "--tags", "--mirror")
               for a in args):
            continue  # a forced or special push is not something a rebase should fix
        positional = [a for a in args if not a.startswith("-")]
        branch = git(workdir, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if len(positional) > 1 and positional[1].split(":")[-1] not in (branch, "HEAD"):
            continue  # pushing some other branch
        remote = positional[0] if positional else ""

        if git(workdir, "fetch", *( [remote] if remote else [] )).returncode != 0:
            continue  # offline or no remote: let git push report it
        upstream = git(workdir, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        if upstream.returncode != 0:
            continue  # new branch with no upstream yet
        behind = git(workdir, "rev-list", "--count", "HEAD..@{u}").stdout.strip()
        if behind in ("", "0"):
            continue

        pull = git(workdir, "pull", "--rebase", "--autostash")
        if pull.returncode == 0:
            say(f"safe-vibe: the remote had {behind} new commit(s). I rebased your work on top of them before pushing.")
            continue

        git(workdir, "rebase", "--abort")
        common.block(
            "git push (remote is ahead and the rebase conflicts)",
            f"{behind} commit(s) on {upstream.stdout.strip()} touch the same lines as yours. I aborted the rebase, "
            "so your files and commits are exactly as they were.",
            "Run `git pull --rebase`, resolve the conflicted files together with the user, then push again. "
            "Never force-push to get around this.",
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        sys.stderr.write(f"safe-vibe pull-before-push error (push allowed): {exc}\n")
        sys.exit(0)
