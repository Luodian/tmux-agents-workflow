#!/usr/bin/env python3
"""UserPromptSubmit hook: surface workspace state to the agent.

Two pieces of context, both via `additionalContext`:

1. Todo list change-detection — when `.agentwf/todos.md` changed since
   the last fire, emit the new contents. If the previous author was a
   peer agent (Codex when --agent claude, or vice versa), prepend a
   note so the agent knows whose write to acknowledge.

2. Prompt index — when `.agentwf/prompts/*.md` exist, list them once so
   the agent knows resources are available to read on demand
   (just-in-time content injection happens via PreToolUse, not here).

Usage:
    hook_prompt_submit.py --agent claude
    hook_prompt_submit.py --agent codex

No-op (silent) when nothing changed.
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
from todos_sync import parse_last_author  # noqa: E402


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
        payload = {}

    cwd = payload.get("cwd") or os.getcwd()
    root = git_root(cwd)
    if not root:
        return

    aw = os.path.join(root, ".agentwf")
    todo_file = os.path.join(aw, "todos.md")
    last_seen_file = os.path.join(aw, ".last-seen-todos")
    prompts_dir = os.path.join(aw, "prompts")
    prompts_seen_file = os.path.join(aw, ".last-seen-prompts")

    bits: list[str] = []

    # 1. Todo change detection.
    if os.path.exists(todo_file):
        with open(todo_file, "rb") as f:
            body = f.read()
        cur = hashlib.sha1(body).hexdigest()
        last = ""
        if os.path.exists(last_seen_file):
            with open(last_seen_file, "r", encoding="utf-8") as f:
                last = f.read().strip()
        if cur != last:
            with open(last_seen_file, "w", encoding="utf-8") as f:
                f.write(cur)
            text = body.decode("utf-8", errors="replace")
            author = parse_last_author(text)
            peer_note = ""
            if author and author != args.agent:
                peer_note = (
                    f"NOTE: peer agent **{author}** wrote this update. "
                    "If your in-memory plan is out of sync, refresh it.\n\n"
                )
            bits.append(
                "Persistent workspace todo list (.agentwf/todos.md) changed:\n\n"
                + peer_note
                + text
                + "\nLegend: [x]=completed, [~]=in_progress, [ ]=pending."
            )

    # 2. Prompt index — only emit on first change to avoid per-turn noise.
    if os.path.isdir(prompts_dir):
        files = sorted(
            f for f in os.listdir(prompts_dir)
            if f.endswith(".md") and not f.startswith(".")
        )
        if files:
            joined = ",".join(files)
            cur_idx = hashlib.sha1(joined.encode()).hexdigest()
            last_idx = ""
            if os.path.exists(prompts_seen_file):
                with open(prompts_seen_file, "r", encoding="utf-8") as f:
                    last_idx = f.read().strip()
            if cur_idx != last_idx:
                with open(prompts_seen_file, "w", encoding="utf-8") as f:
                    f.write(cur_idx)
                bits.append(
                    "Repo-specific prompt files available in .agentwf/prompts/: "
                    + ", ".join(files)
                    + ". Read them when relevant — they encode this repo's "
                    "conventions for PR descriptions, commit messages, and "
                    "general preferences. Specific files are auto-injected by "
                    "PreToolUse hooks at point-of-use (e.g. pr.md before "
                    "`gh pr create`)."
                )

    if not bits:
        return

    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n\n---\n\n".join(bits),
        }
    }
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
