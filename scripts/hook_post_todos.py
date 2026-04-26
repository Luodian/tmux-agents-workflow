#!/usr/bin/env python3
"""PostToolUse hook: agent's plan tool → `.agentwf/spec.md` > To-dos section.

Handles both Claude TodoWrite and Codex update_plan via
`todos_sync.normalize_payload`. Writes ONLY into the `## To-dos`
section, preserving Contexts and Decisions intact. Updates the
last-seen hash so the UserPromptSubmit hook doesn't replay the
agent's own write back to itself.

Usage (in settings.json / hooks.json):
    hook_post_todos.py --agent claude
    hook_post_todos.py --agent codex
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from todos_sync import (  # noqa: E402
    DEFAULT_SECTION,
    EMPTY_SPEC,
    SPEC_FILE_NAME,
    normalize_payload,
    set_section,
    todos_to_section_body,
)

AUTHOR_RE = re.compile(r"<!--\s*last-author:[^>]*-->")


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
    spec_path = os.path.join(aw_dir, SPEC_FILE_NAME)

    existing = ""
    if os.path.exists(spec_path):
        with open(spec_path, "r", encoding="utf-8") as f:
            existing = f.read()
    if not existing.strip():
        existing = EMPTY_SPEC

    # Bump the author marker so peer agents see who wrote last.
    author = args.agent or source
    existing = AUTHOR_RE.sub(f"<!-- last-author: {author} -->", existing, count=1)
    if "last-author:" not in existing:
        existing = existing.replace("# Workspace spec\n", f"# Workspace spec\n<!-- last-author: {author} -->\n", 1)

    new_body = set_section(existing, DEFAULT_SECTION, todos_to_section_body(todos))
    with open(spec_path, "w", encoding="utf-8") as f:
        f.write(new_body)

    h = hashlib.sha1(new_body.encode("utf-8")).hexdigest()
    with open(os.path.join(aw_dir, ".last-seen-spec"), "w", encoding="utf-8") as f:
        f.write(h)


if __name__ == "__main__":
    main()
