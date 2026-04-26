#!/usr/bin/env python3
"""Bidirectional parser between Claude TodoWrite JSON and the
`.agentwf/todos.md` markdown checkbox file.

Markdown grammar (single source of truth):

    # Workspace todos
    <optional preamble lines preserved>

    - [ ] pending item                 # status = pending
    - [~] in-progress item             # status = in_progress
    - [x] completed item               # status = completed
    - [X] also completed               # case-insensitive

The parser preserves any non-todo lines in the markdown file (so users
can keep notes / section headers there). Only checkbox lines round-trip
to the JSON list.

CLI:
    todos_sync.py to-md        < tool_input.json   > todos.md
    todos_sync.py to-json      < todos.md          > [{...}]
    todos_sync.py append "content" [--status pending|in_progress|completed]
                          [--file <path>] [--idempotent]
    todos_sync.py mark "content-substr" --status completed [--file <path>]
    todos_sync.py count [--file <path>] [--unchecked-only]
    todos_sync.py --selftest
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Iterable

STATUS_TO_BOX = {
    "pending": " ",
    "in_progress": "~",
    "completed": "x",
}
BOX_TO_STATUS = {
    " ": "pending",
    "~": "in_progress",
    "x": "completed",
    "X": "completed",
}

# Header line `# Workspace todos` and an authorship marker comment line
# `<!-- last-author: claude|codex -->`. The marker is preserved by
# md_to_todos (which only matches checkbox lines), so it round-trips safely.
AUTHOR_MARKER_RE = re.compile(r"<!--\s*last-author:\s*(\w+)\s*-->")

# Match `- [ ] content`, `- [x] content`, `- [~] content`. Leading whitespace tolerated.
TODO_LINE = re.compile(r"^(\s*)-\s*\[([ xX~])\]\s*(.*)$")
HEADER_DEFAULT = "# Workspace todos"


def todos_to_md(todos: list[dict], author: str | None = None) -> str:
    """Render a TodoWrite-shaped list into markdown checkboxes.

    `author` (optional) embeds an HTML comment marker so a peer agent
    reading the file later can attribute the most recent write.
    """
    lines: list[str] = [HEADER_DEFAULT, ""]
    if author:
        lines.append(f"<!-- last-author: {author} -->")
        lines.append("")
    for t in todos:
        if not isinstance(t, dict):
            continue
        content = (t.get("content") or "").strip()
        if not content:
            continue
        status = t.get("status", "pending")
        box = STATUS_TO_BOX.get(status, " ")
        lines.append(f"- [{box}] {content}")
    return "\n".join(lines) + "\n"


def parse_last_author(text: str) -> str | None:
    """Read the `<!-- last-author: X -->` marker from a todos.md body."""
    for line in text.splitlines():
        m = AUTHOR_MARKER_RE.search(line)
        if m:
            return m.group(1)
    return None


def normalize_payload(payload: dict) -> tuple[str, list[dict]]:
    """Convert a Claude TodoWrite or Codex update_plan hook payload into a
    unified `(source, todos)` tuple.

    Returns:
      - ("claude", [{content, status, activeForm}])   for Claude TodoWrite
      - ("codex",  [{content, status, activeForm}])   for Codex update_plan
      - ("unknown", [])                                for anything else
    """
    if not isinstance(payload, dict):
        return ("unknown", [])
    tool = payload.get("tool_name", "")

    if tool == "TodoWrite":
        items = payload.get("tool_input", {}).get("todos", []) or []
        out: list[dict] = []
        for t in items:
            if not isinstance(t, dict):
                continue
            content = (t.get("content") or "").strip()
            if not content:
                continue
            out.append({
                "content": content,
                "status": t.get("status", "pending"),
                "activeForm": t.get("activeForm") or content,
            })
        return ("claude", out)

    if tool == "update_plan":
        ti = payload.get("tool_input", {}) or {}
        # Codex sometimes nests under arguments (string or dict), sometimes flat.
        plan = None
        for source in (ti.get("arguments"), ti):
            if isinstance(source, str):
                try:
                    source = json.loads(source)
                except Exception:
                    continue
            if isinstance(source, dict) and isinstance(source.get("plan"), list):
                plan = source["plan"]
                break
        plan = plan or []
        out = []
        for p in plan:
            if not isinstance(p, dict):
                continue
            step = (p.get("step") or "").strip()
            if not step:
                continue
            out.append({
                "content": step,
                "status": p.get("status", "pending"),
                "activeForm": step,
            })
        return ("codex", out)

    return ("unknown", [])


def md_to_todos(text: str) -> list[dict]:
    """Parse markdown into TodoWrite-shaped list (only checkbox lines)."""
    out: list[dict] = []
    for line in text.splitlines():
        m = TODO_LINE.match(line)
        if not m:
            continue
        box, content = m.group(2), m.group(3).strip()
        if not content:
            continue
        out.append({
            "content": content,
            "status": BOX_TO_STATUS.get(box, "pending"),
            # activeForm is not represented in the markdown; surface a sensible default.
            "activeForm": content,
        })
    return out


def _resolve_file(file_arg: str | None) -> str:
    if file_arg:
        return file_arg
    cwd = os.getcwd()
    return os.path.join(cwd, ".agentwf", "todos.md")


def _read(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write(path: str, body: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)


def cmd_to_md() -> None:
    payload = json.load(sys.stdin)
    # Accept both: a raw todos array, or a PostToolUse payload with tool_input.todos.
    if isinstance(payload, dict) and "tool_input" in payload:
        todos = payload.get("tool_input", {}).get("todos", [])
    elif isinstance(payload, dict) and "todos" in payload:
        todos = payload["todos"]
    elif isinstance(payload, list):
        todos = payload
    else:
        todos = []
    sys.stdout.write(todos_to_md(todos))


def cmd_to_json() -> None:
    text = sys.stdin.read()
    json.dump(md_to_todos(text), sys.stdout, indent=2)
    sys.stdout.write("\n")


def cmd_append(content: str, status: str, file_path: str, idempotent: bool) -> None:
    body = _read(file_path)
    todos = md_to_todos(body) if body else []
    if idempotent and any(t["content"] == content for t in todos):
        return
    todos.append({"content": content, "status": status, "activeForm": content})
    # Preserve any non-todo preamble (e.g., a custom header).
    preamble_lines: list[str] = []
    saw_todo = False
    for line in body.splitlines():
        if TODO_LINE.match(line):
            saw_todo = True
            continue
        if saw_todo:
            # Drop trailing prose past the last existing todo to avoid drift.
            continue
        preamble_lines.append(line)
    if not preamble_lines or not any(line.strip() for line in preamble_lines):
        preamble_lines = [HEADER_DEFAULT, ""]
    rendered_todos = []
    for t in todos:
        box = STATUS_TO_BOX.get(t["status"], " ")
        rendered_todos.append(f"- [{box}] {t['content']}")
    out = "\n".join(preamble_lines + rendered_todos) + "\n"
    _write(file_path, out)


def cmd_mark(substr: str, status: str, file_path: str) -> None:
    body = _read(file_path)
    if not body:
        return
    out_lines: list[str] = []
    box = STATUS_TO_BOX.get(status, " ")
    changed = False
    for line in body.splitlines():
        m = TODO_LINE.match(line)
        if m and substr in m.group(3):
            indent = m.group(1)
            content = m.group(3).strip()
            out_lines.append(f"{indent}- [{box}] {content}")
            changed = True
        else:
            out_lines.append(line)
    if changed:
        _write(file_path, "\n".join(out_lines) + "\n")


def cmd_count(file_path: str, unchecked_only: bool) -> None:
    body = _read(file_path)
    todos = md_to_todos(body) if body else []
    if unchecked_only:
        todos = [t for t in todos if t["status"] != "completed"]
    print(len(todos))


def selftest() -> None:
    """Round-trip and edge-case checks."""
    sample = [
        {"content": "Run setup.sh", "status": "completed", "activeForm": "Running setup"},
        {"content": "Confirm worktree", "status": "in_progress", "activeForm": "Confirming"},
        {"content": "Open PR", "status": "pending", "activeForm": "Opening PR"},
    ]
    md = todos_to_md(sample)
    assert "- [x] Run setup.sh" in md, md
    assert "- [~] Confirm worktree" in md, md
    assert "- [ ] Open PR" in md, md

    parsed = md_to_todos(md)
    assert len(parsed) == 3, parsed
    assert parsed[0]["status"] == "completed"
    assert parsed[1]["status"] == "in_progress"
    assert parsed[2]["status"] == "pending"

    # Idempotent append
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "todos.md")
        cmd_append("Open PR", "pending", p, idempotent=False)
        cmd_append("Open PR", "pending", p, idempotent=True)  # should not duplicate
        ts = md_to_todos(_read(p))
        assert sum(1 for t in ts if t["content"] == "Open PR") == 1, ts

        cmd_mark("Open PR", "completed", p)
        ts2 = md_to_todos(_read(p))
        assert ts2[0]["status"] == "completed", ts2

    print("selftest OK")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("to-md")
    sub.add_parser("to-json")

    ap = sub.add_parser("append")
    ap.add_argument("content")
    ap.add_argument("--status", default="pending", choices=list(STATUS_TO_BOX))
    ap.add_argument("--file", default=None)
    ap.add_argument("--idempotent", action="store_true")

    mp = sub.add_parser("mark")
    mp.add_argument("substr")
    mp.add_argument("--status", default="completed", choices=list(STATUS_TO_BOX))
    mp.add_argument("--file", default=None)

    cp = sub.add_parser("count")
    cp.add_argument("--file", default=None)
    cp.add_argument("--unchecked-only", action="store_true")

    p.add_argument("--selftest", action="store_true")

    args = p.parse_args()
    if args.selftest:
        selftest()
        return

    if args.cmd == "to-md":
        cmd_to_md()
    elif args.cmd == "to-json":
        cmd_to_json()
    elif args.cmd == "append":
        cmd_append(args.content, args.status, _resolve_file(args.file), args.idempotent)
    elif args.cmd == "mark":
        cmd_mark(args.substr, args.status, _resolve_file(args.file))
    elif args.cmd == "count":
        cmd_count(_resolve_file(args.file), args.unchecked_only)
    else:
        p.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
