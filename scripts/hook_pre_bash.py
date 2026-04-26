#!/usr/bin/env python3
"""PreToolUse(Bash) hook: just-in-time injection of repo-specific prompts.

When the agent is about to run a Bash command that matches a known
"prompt-worthy" action (e.g. `gh pr create`, `aw-pr`, `git commit`),
this hook injects the corresponding `.agentwf/prompts/<name>.md` file
as `additionalContext` so the agent gets the repo's house style at
the exact moment it matters — no upfront context cost.

Mappings (extend the COMMAND_MAP dict to add more):
    gh pr create / aw-pr  → prompts/pr.md
    git commit            → prompts/commit.md

Usage:
    hook_pre_bash.py --agent claude
    hook_pre_bash.py --agent codex
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys


COMMAND_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(gh\s+pr\s+create|aw-pr)\b"), "pr.md"),
    (re.compile(r"\bgit\s+commit\b"), "commit.md"),
]


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
    args = ap.parse_args()  # noqa: F841 — accepted for symmetry with peer hooks

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    if payload.get("tool_name") != "Bash":
        return

    cmd = payload.get("tool_input", {}).get("command", "") or ""
    if not cmd:
        return

    cwd = payload.get("cwd") or os.getcwd()
    root = git_root(cwd)
    if not root:
        return

    matched: list[str] = []
    for pat, fname in COMMAND_MAP:
        if pat.search(cmd):
            path = os.path.join(root, ".agentwf", "prompts", fname)
            if os.path.exists(path):
                matched.append(path)

    if not matched:
        return

    blocks: list[str] = []
    for p in matched:
        with open(p, "r", encoding="utf-8") as f:
            content = f.read()
        rel = os.path.relpath(p, root)
        blocks.append(f"=== {rel} ===\n\n{content}")

    ctx = (
        "Repo-specific prompt(s) for the command you're about to run "
        "(.agentwf/prompts/). Apply the conventions defined here:\n\n"
        + "\n\n".join(blocks)
    )

    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": ctx,
        }
    }
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
