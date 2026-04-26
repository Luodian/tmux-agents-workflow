#!/usr/bin/env python3
"""PostToolUse hook for Claude TodoWrite **and** Codex update_plan.

The matcher in hooks.json filters by tool_name (`TodoWrite` for Claude,
`update_plan` for Codex). This single script handles either schema via
`todos_sync.normalize_payload`, then writes a unified markdown checkbox
file to `.agentwf/todos.md` with a `<!-- last-author: X -->` marker so
peer agents can attribute the most recent edit.

Usage:
    hook_post_todos.py --agent claude    # in Claude settings.json
    hook_post_todos.py --agent codex     # in Codex hooks.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from todos_sync import normalize_payload, todos_to_md  # noqa: E402


def git_root(cwd: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except subprocess.CalledProcessError:
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="claude", choices=["claude", "codex"])
    args = ap.parse_args()

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    source, todos = normalize_payload(payload)
    if source == "unknown":
        return

    cwd = payload.get("cwd") or os.getcwd()
    root = git_root(cwd)
    if not root:
        return

    aw_dir = os.path.join(root, ".agentwf")
    os.makedirs(aw_dir, exist_ok=True)

    # Author preference: --agent flag wins, fall back to detected source.
    author = args.agent or source
    body = todos_to_md(todos, author=author)
    with open(os.path.join(aw_dir, "todos.md"), "w", encoding="utf-8") as f:
        f.write(body)

    h = hashlib.sha1(body.encode("utf-8")).hexdigest()
    with open(os.path.join(aw_dir, ".last-seen-todos"), "w", encoding="utf-8") as f:
        f.write(h)


if __name__ == "__main__":
    main()
