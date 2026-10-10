#!/usr/bin/env python3
"""safe-vibe guard: block destructive shell commands before they run.

Claude Code PreToolUse hook for the Bash tool. Reads the hook payload on
stdin. Exit 0 lets the command through, exit 2 blocks it and sends the
message on stderr back to the agent. Any internal error lets the command
through, so a bug here never locks you out of your own terminal.

Set SAFE_VIBE_OFF=1 in the environment that launches Claude Code to turn
the guard off for that session.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

PROTECTED_BRANCHES = ["main", "master"]
SAFE_RM_PREFIXES = ["/tmp/", "/private/tmp/"]

# Programs that only talk about SQL and never run it.
TEXT_ONLY = {"grep", "rg", "ag", "man", "less", "head", "tail"}
REMOTE_PROGRAMS = {"ssh", "scp", "sftp", "rsync", "psql", "mysql", "mongosh",
                   "redis-cli", "pg_dump", "pg_restore", "kubectl", "docker"}

# (id, regex, what, why, instead). Matched case-insensitively per segment.
TEXT_RULES = [
    ("sql-drop",
     r"\bdrop\s+(table|database|schema|index|view|column)\b",
     "DROP statement",
     "it deletes a table or database, and the data does not come back.",
     "Rename it first, or take a dump and ask the user to run the DROP themselves."),
    ("sql-truncate",
     r"\btruncate\s+(table\s+)?[\w\"`.]+",
     "TRUNCATE statement",
     "it empties a whole table in one step, with no row-by-row undo.",
     "Delete a limited set of rows with a WHERE clause, or ask the user to run it."),
    ("terraform-destroy",
     r"\bterraform\s+destroy\b|\bterraform\s+apply\b.*-destroy\b|\btofu\s+destroy\b",
     "terraform destroy",
     "it tears down real infrastructure.",
     "Run `terraform plan -destroy` and show the plan to the user."),
    ("compose-down",
     r"\bdocker[\s-]+compose\s+(-\S+\s+\S+\s+|-\S+\s+)*down\b",
     "docker compose down",
     "it stops and removes the running containers, and `down -v` also deletes their volumes.",
     "Use `docker compose stop` or restart a single service. Ask the user before `down`."),
    ("kubectl-delete",
     r"\bkubectl\s+(\S+\s+)*delete\b",
     "kubectl delete",
     "it removes cluster resources that may be serving real traffic.",
     "Run `kubectl get` and `kubectl describe` to look, and ask the user to run the delete."),
    ("git-reset-hard",
     r"\bgit\s+(\S+\s+)*reset\s+(\S+\s+)*--hard\b",
     "git reset --hard",
     "it throws away your uncommitted changes for good and moves the branch.",
     "Use `git stash`, or `git reset --soft` / `--mixed` to keep the changes."),
]

DELETE_FROM = re.compile(r"\bdelete\s+from\b", re.I)


def delete_without_where(segment: str) -> bool:
    """True when a DELETE FROM statement has no WHERE before it ends."""
    for m in DELETE_FROM.finditer(segment):
        rest = segment[m.end():]
        end = re.search(r";|\"|'|\\n", rest)
        statement = rest[: end.start()] if end else rest
        if not re.search(r"\bwhere\b", statement, re.I):
            return True
    return False


def check_rm(toks: list[str], root: Path, extra_safe: list[str]) -> None:
    if common.program(toks) != "rm":
        return
    flags = [t for t in toks[1:] if t.startswith("-")]
    recursive = any(
        t in ("--recursive",) or (not t.startswith("--") and ("r" in t[1:] or "R" in t[1:]))
        for t in flags
    )
    if not recursive:
        return
    targets = [t for t in toks[1:] if not t.startswith("-")]
    for raw in targets:
        if "$" in raw or "`" in raw:
            common.block(
                f"rm -r {raw}",
                "the path uses a variable, so I cannot check where it points. An empty variable turns this into `rm -rf /`.",
                "Write out the real path, inside this project, and run it again.",
            )
        home = os.environ.get("HOME", str(Path.home()))
        expanded = raw.replace("~", home, 1) if raw.startswith("~") else raw
        path = Path(expanded)
        if not path.is_absolute():
            path = root / path
        resolved = Path(os.path.realpath(path))
        text = str(resolved)
        safe = SAFE_RM_PREFIXES + extra_safe
        if any(text.startswith(p) and text != p.rstrip("/") for p in safe):
            continue
        inside = resolved != root and root in resolved.parents
        if not inside:
            common.block(
                f"rm -r {raw}  (resolves to {text})",
                f"it is outside the project folder ({root}) or is the project folder itself.",
                "Delete only paths inside the project, or ask the user to run this one.",
            )


def check_force_push(toks: list[str], root: Path, protected: list[str]) -> None:
    sub, args = common.git_subcommand(toks)
    if sub != "push":
        return
    force = any(a in ("-f", "--force", "--force-with-lease") or a.startswith("--force-with-lease=")
                or (a.startswith("-") and not a.startswith("--") and "f" in a[1:]) for a in args)
    plus_ref = any(a.startswith("+") for a in args)
    if not (force or plus_ref):
        return
    positional = [a for a in args if not a.startswith("-")]
    refs = positional[1:]  # first positional is the remote
    named = []
    for ref in refs:
        ref = ref.lstrip("+")
        named.append(ref.split(":")[-1].replace("refs/heads/", ""))
    if not named:
        named = [current_branch(common.git_dir_option(toks) or str(root))]
    hit = [b for b in named if b in protected or b == "HEAD" and current_branch(str(root)) in protected]
    if hit:
        common.block(
            "git push --force to " + ", ".join(hit),
            "it rewrites shared history, and teammates' clones and deploys will not match afterwards.",
            "Push a new commit, or push a feature branch. If history really must change, ask the user.",
        )


def current_branch(cwd: str) -> str:
    import subprocess
    try:
        out = subprocess.run(["git", "-C", cwd, "symbolic-ref", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip()
    except Exception:
        return ""


def main() -> int:
    if os.environ.get("SAFE_VIBE_OFF") == "1":
        return 0
    payload = common.read_payload()
    command = common.bash_command(payload)
    if not command:
        return 0

    root = common.project_dir(payload)
    cfg = common.load_config(root)
    settings = cfg.get("guard", {})
    disabled = set(settings.get("disable", []))
    allow = [re.compile(p, re.I) for p in settings.get("allow", [])]
    protected = settings.get("protected_branches", PROTECTED_BRANCHES)
    extra_safe = [str(Path(p).expanduser()).rstrip("/") + "/" for p in settings.get("rm_safe_paths", [])]
    hosts = [h.lower() for h in cfg.get("prod", {}).get("hosts", [])]
    custom = cfg.get("rule", [])

    for segment in common.split_segments(command):
        if any(p.search(segment) for p in allow):
            continue
        toks = common.strip_prefix(common.tokens(segment))
        prog = common.program(toks)
        sub, _ = common.git_subcommand(toks)

        if prog not in TEXT_ONLY and not (sub in ("commit", "log", "tag", "notes")):
            for rid, pattern, what, why, instead in TEXT_RULES:
                if rid not in disabled and re.search(pattern, segment, re.I):
                    common.block(what, why, instead)
            if "sql-delete" not in disabled and delete_without_where(segment):
                common.block(
                    "DELETE FROM without WHERE",
                    "it deletes every row in the table.",
                    "Add a WHERE clause, run a SELECT with the same WHERE first, or ask the user.",
                )

        if "rm-outside-project" not in disabled:
            check_rm(toks, root, extra_safe)
        if "git-force-push" not in disabled:
            check_force_push(toks, root, protected)

        if "prod-host" not in disabled and prog in REMOTE_PROGRAMS:
            low = segment.lower()
            for host in hosts:
                if re.search(r"(?<![\w.-])" + re.escape(host) + r"(?![\w-])", low):
                    common.block(
                        f"{prog} against the production host {host}",
                        "this host is listed under [prod] in your safe-vibe config.",
                        "Work on a staging copy, or ask the user to run this one themselves.",
                    )

        for rule in custom:
            try:
                if rule["id"] not in disabled and re.search(rule["pattern"], segment, re.I):
                    common.block(rule.get("what", rule["id"]),
                                 rule.get("why", "a rule in your safe-vibe config forbids it."),
                                 rule.get("instead", "Ask the user before running this."))
            except (KeyError, re.error) as exc:
                sys.stderr.write(f"safe-vibe: bad custom rule skipped: {exc}\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # never lock the user out
        sys.stderr.write(f"safe-vibe guard error (command allowed): {exc}\n")
        sys.exit(0)
