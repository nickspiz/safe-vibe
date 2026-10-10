"""Shared helpers for the safe-vibe hooks. Standard library only."""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None

CONFIG_NAMES = ("safe-vibe.toml", "safe-vibe.json")


def read_payload() -> dict:
    """Read the hook payload Claude Code sends on stdin. Never raises."""
    try:
        data = json.load(sys.stdin)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def bash_command(payload: dict) -> str:
    """Return the Bash command from the payload, or '' for any other tool."""
    if payload.get("tool_name") != "Bash":
        return ""
    cmd = (payload.get("tool_input") or {}).get("command")
    return cmd if isinstance(cmd, str) else ""


def project_dir(payload: dict) -> Path:
    base = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    return Path(base).expanduser().resolve()


def block(what: str, why: str, instead: str) -> None:
    """Block the tool call. Exit code 2 sends stderr back to the agent."""
    sys.stderr.write(
        "safe-vibe blocked this command.\n"
        f"  What:    {what}\n"
        f"  Why:     {why}\n"
        f"  Instead: {instead}\n"
    )
    sys.exit(2)


# ---------------------------------------------------------------- config

def _read_file(path: Path) -> dict:
    try:
        if path.suffix == ".toml":
            if tomllib is None:
                sys.stderr.write(f"safe-vibe: {path} needs Python 3.11+, use safe-vibe.json\n")
                return {}
            with path.open("rb") as fh:
                return tomllib.load(fh)
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        sys.stderr.write(f"safe-vibe: could not read {path}: {exc}\n")
        return {}


def _merge(base: dict, extra: dict) -> dict:
    """Lists are concatenated, tables are merged, scalars are overridden."""
    out = dict(base)
    for key, val in extra.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], val)
        elif isinstance(val, list) and isinstance(out.get(key), list):
            out[key] = out[key] + val
        else:
            out[key] = val
    return out


def load_config(project: Path) -> dict:
    """Global config first, then the project config on top."""
    env = os.environ.get("SAFE_VIBE_CONFIG")
    if env:
        return _read_file(Path(env).expanduser())
    home = Path(os.environ.get("HOME", str(Path.home())))
    places = [home / ".config" / "safe-vibe"]
    places += [project / ".claude", project]
    cfg: dict = {}
    for folder in places:
        for name in CONFIG_NAMES:
            path = folder / name
            if path.is_file():
                cfg = _merge(cfg, _read_file(path))
                break
    return cfg


# ---------------------------------------------------------------- parsing

def split_segments(command: str) -> list[str]:
    """Split a shell command on ; & | and newlines, ignoring quoted ones."""
    segments: list[str] = []
    buf: list[str] = []
    quote = ""
    i = 0
    while i < len(command):
        ch = command[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < len(command):
                buf.append(command[i + 1])
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
            buf.append(ch)
        elif ch == "\\" and i + 1 < len(command):
            buf.append(ch)
            buf.append(command[i + 1])
            i += 1
        elif ch in ";&|\n":
            segments.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    segments.append("".join(buf))
    return [s.strip() for s in segments if s.strip()]


def tokens(segment: str) -> list[str]:
    """Shell-split a segment. Falls back to whitespace split on bad quoting."""
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


_WRAPPERS = {"sudo", "command", "exec", "nohup", "time", "env", "nice", "xargs"}
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def strip_prefix(toks: list[str]) -> list[str]:
    """Drop `sudo`, `env`, `FOO=bar` and similar so toks[0] is the program."""
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in _WRAPPERS or _ASSIGN.match(t) or (t.startswith("-") and i > 0 and toks[0] in _WRAPPERS):
            i += 1
        else:
            break
    return toks[i:]


def program(toks: list[str]) -> str:
    """Program name without its directory, lower-cased."""
    if not toks:
        return ""
    return os.path.basename(toks[0]).lower()


def git_subcommand(toks: list[str]) -> tuple[str, list[str]]:
    """For `git [-C dir] [-c k=v] sub args` return (sub, args)."""
    if program(toks) != "git":
        return "", []
    i = 1
    while i < len(toks):
        t = toks[i]
        if t in ("-C", "-c", "--git-dir", "--work-tree", "--namespace"):
            i += 2
        elif t.startswith("-"):
            i += 1
        else:
            return t, toks[i + 1:]
    return "", []


def git_dir_option(toks: list[str]) -> str:
    """Value of `git -C <dir>` if present."""
    for i, t in enumerate(toks[:-1]):
        if t == "-C":
            return toks[i + 1]
    return ""
