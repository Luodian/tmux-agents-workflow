#!/usr/bin/env python3
"""Internal renderer for aw-summarize. Reads env vars set by the bash
wrapper and emits a markdown report to stdout.

Inputs (env):
  AW_SCRIPTS            absolute path to the plugin's scripts/ dir (for import)
  AW_SPEC               absolute path to .agentwf/spec.md
  AW_WORKTREE           git toplevel of the worktree
  AW_SLUG               human-readable task slug
  AW_INCLUDE_SNAPSHOT   "1" to embed verbatim spec at end, "0" to skip
"""

from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.environ["AW_SCRIPTS"])
from todos_sync import HTML_COMMENT, section_body_to_todos, split_sections  # noqa: E402


def sh(*args: str, cwd: str) -> str:
    try:
        return subprocess.check_output(
            args, cwd=cwd, stderr=subprocess.DEVNULL,
        ).decode().strip()
    except subprocess.CalledProcessError:
        return ""


def main() -> None:
    spec_path = os.environ["AW_SPEC"]
    worktree = os.environ["AW_WORKTREE"]
    slug = os.environ["AW_SLUG"]
    include_snap = os.environ.get("AW_INCLUDE_SNAPSHOT", "1") == "1"

    with open(spec_path, "r", encoding="utf-8") as f:
        text = f.read()

    _, sections, _ = split_sections(text)
    contexts = HTML_COMMENT.sub("", sections.get("Contexts", "")).strip()
    decisions = HTML_COMMENT.sub("", sections.get("Decisions", "")).strip()
    todos = section_body_to_todos(sections.get("To-dos", ""))

    branch = sh("git", "rev-parse", "--abbrev-ref", "HEAD", cwd=worktree) or "?"
    head = sh("git", "rev-parse", "HEAD", cwd=worktree) or "?"
    diff_stat = (
        sh("git", "diff", "--stat", "main...HEAD", cwd=worktree)
        or sh("git", "diff", "--stat", "HEAD", cwd=worktree)
    )
    timestamp = sh("date", "+%Y-%m-%d %H:%M", cwd=worktree)

    completed = [t for t in todos if t["status"] == "completed"]
    in_progress = [t for t in todos if t["status"] == "in_progress"]
    pending = [t for t in todos if t["status"] == "pending"]

    lines: list[str] = [
        f"# Report — {slug}",
        "",
        f"**Branch**: `{branch}`",
        f"**HEAD**: `{head[:12]}`",
        f"**Worktree**: `{worktree}`",
        f"**Generated**: {timestamp}",
        "",
        "## What shipped",
        "",
    ]
    if completed:
        lines.extend(f"- {t['content']}" for t in completed)
    else:
        lines.append("_(nothing marked completed yet)_")

    lines += ["", "## Decisions resolved", ""]
    lines.append(decisions if decisions else "_(no Decisions recorded)_")

    lines += ["", "## Contexts captured", ""]
    lines.append(contexts if contexts else "_(no Contexts recorded)_")

    lines += ["", "## Open follow-ups", ""]
    remaining = in_progress + pending
    if remaining:
        for t in remaining:
            tag = "in-progress" if t["status"] == "in_progress" else "pending"
            lines.append(f"- ({tag}) {t['content']}")
    else:
        lines.append("_(none — all to-dos complete)_")

    if diff_stat:
        lines += ["", "## Diff stat", "", "```", diff_stat, "```"]

    if include_snap:
        lines += [
            "", "## Source spec snapshot", "",
            "_Verbatim copy of `.agentwf/spec.md` at summary time:_",
            "", "```markdown", text.rstrip(), "```",
        ]

    sys.stdout.write("\n".join(lines).rstrip() + "\n")


if __name__ == "__main__":
    main()
