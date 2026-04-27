#!/usr/bin/env python3
"""UserPromptSubmit hook: surface workspace-state changes to the agent.

Two pieces of context, both via `additionalContext`:

1. **Spec change** — `.agentwf/spec.md` contains the live spec
   (Contexts / Decisions / To-dos). When sha changes since last firing,
   inject the full file with a peer-agent attribution note when the
   last writer was a different agent.

2. **Prompt index** — list `.agentwf/prompts/*.md` once when first seen,
   so the agent knows the resources are available (specific contents
   are auto-injected at point-of-use by the PreToolUse hook).

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
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from todos_sync import parse_last_author, resolve_spec_path  # noqa: E402

HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


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
    spec_file = resolve_spec_path(root)
    spec_seen = os.path.join(aw, ".last-seen-spec")
    prompts_dir = os.path.join(aw, "prompts")
    prompts_seen = os.path.join(aw, ".last-seen-prompts")

    bits: list[str] = []

    # 1. Spec change detection.
    if os.path.exists(spec_file):
        with open(spec_file, "rb") as f:
            body = f.read()
        cur_hash = hashlib.sha1(body).hexdigest()
        last_hash = ""
        if os.path.exists(spec_seen):
            with open(spec_seen, "r", encoding="utf-8") as f:
                last_hash = f.read().strip()
        if cur_hash != last_hash:
            os.makedirs(os.path.dirname(spec_seen), exist_ok=True)
            with open(spec_seen, "w", encoding="utf-8") as f:
                f.write(cur_hash)
            text = body.decode("utf-8", errors="replace")
            # Strip HTML comments — they're for human readers, not agent context.
            visible = HTML_COMMENT.sub("", text).strip() + "\n"
            author = parse_last_author(text)
            peer_note = ""
            if author and author != args.agent:
                peer_note = (
                    f"NOTE: peer agent **{author}** wrote the most recent "
                    "update. Reconcile your in-memory plan if it diverges.\n\n"
                )
            spec_rel = os.path.relpath(spec_file, root)
            bits.append(
                f"Workspace spec (`{spec_rel}`) changed since last turn:\n\n"
                + peer_note
                + visible
                + "\nLegend: To-dos `[ ]`/`[~]`/`[x]` = pending/in_progress/completed. "
                "Decisions: the `[x]`-marked option is the active choice (defaults to "
                "**Recommended** until the user picks). Edit any section directly via "
                "Write/Edit on the spec file."
            )

    # 2. Prompt index.
    if os.path.isdir(prompts_dir):
        files = sorted(
            f for f in os.listdir(prompts_dir)
            if f.endswith(".md") and not f.startswith(".")
        )
        if files:
            joined = ",".join(files)
            cur_idx = hashlib.sha1(joined.encode()).hexdigest()
            last_idx = ""
            if os.path.exists(prompts_seen):
                with open(prompts_seen, "r", encoding="utf-8") as f:
                    last_idx = f.read().strip()
            if cur_idx != last_idx:
                with open(prompts_seen, "w", encoding="utf-8") as f:
                    f.write(cur_idx)
                bits.append(
                    "Repo prompt files in `.agentwf/prompts/`: "
                    + ", ".join(files)
                    + ". Auto-injected by PreToolUse hooks at point-of-use "
                    "(e.g. pr.md before `gh pr create`, commit.md before `git commit`)."
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
