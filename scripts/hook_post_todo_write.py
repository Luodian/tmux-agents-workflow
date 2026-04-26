#!/usr/bin/env python3
"""PostToolUse(TodoWrite) hook: agent → file.

Reads the Claude Code hook payload from stdin, extracts the new TodoWrite
list, and overwrites `.agentwf/todos.md` in the cwd's git worktree root.
Updates `.agentwf/.last-seen-todos` so the UserPromptSubmit hook does not
falsely flag this write as an external edit.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from todos_sync import todos_to_md  # noqa: E402


def git_root(cwd: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except subprocess.CalledProcessError:
        return None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    if payload.get("tool_name") != "TodoWrite":
        return

    todos = payload.get("tool_input", {}).get("todos", [])
    if not isinstance(todos, list):
        return

    cwd = payload.get("cwd") or os.getcwd()
    root = git_root(cwd)
    if not root:
        return

    aw_dir = os.path.join(root, ".agentwf")
    os.makedirs(aw_dir, exist_ok=True)

    body = todos_to_md(todos)
    with open(os.path.join(aw_dir, "todos.md"), "w", encoding="utf-8") as f:
        f.write(body)

    h = hashlib.sha1(body.encode("utf-8")).hexdigest()
    with open(os.path.join(aw_dir, ".last-seen-todos"), "w", encoding="utf-8") as f:
        f.write(h)


if __name__ == "__main__":
    main()
