#!/usr/bin/env python3
"""UserPromptSubmit hook: file → agent.

Detects changes to `.agentwf/todos.md` since the last hook firing and
emits an `additionalContext` JSON output telling the agent to refresh
its in-memory TodoWrite list. No-op when the file is unchanged or
missing — keeps the prompt path cheap.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys


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
        payload = {}

    cwd = payload.get("cwd") or os.getcwd()
    root = git_root(cwd)
    if not root:
        return

    todo_file = os.path.join(root, ".agentwf", "todos.md")
    last_seen = os.path.join(root, ".agentwf", ".last-seen-todos")

    if not os.path.exists(todo_file):
        return

    with open(todo_file, "rb") as f:
        body = f.read()
    current_hash = hashlib.sha1(body).hexdigest()

    last_hash = ""
    if os.path.exists(last_seen):
        with open(last_seen, "r", encoding="utf-8") as f:
            last_hash = f.read().strip()

    if current_hash == last_hash:
        return

    # Update snapshot first so we don't replay if the same prompt fires twice.
    os.makedirs(os.path.dirname(last_seen), exist_ok=True)
    with open(last_seen, "w", encoding="utf-8") as f:
        f.write(current_hash)

    ctx = (
        "The persistent workspace todo list (.agentwf/todos.md) was updated "
        "since your last turn. Current contents:\n\n"
        + body.decode("utf-8", errors="replace")
        + "\nLegend: [x]=completed, [~]=in_progress, [ ]=pending. "
        "If your in-memory TodoWrite list is out of sync, call TodoWrite to "
        "rewrite it to match — agents-workflow will mirror your call back to "
        "this file automatically."
    )
    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": ctx,
        }
    }
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
