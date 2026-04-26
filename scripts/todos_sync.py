#!/usr/bin/env python3
"""Bidirectional parser between Claude TodoWrite / Codex update_plan
hook payloads and `.agentwf/spec.md` (the per-worktree spec file).

`spec.md` is a single markdown file split into three top-level (`##`)
sections: **Contexts**, **Decisions**, **To-dos**. The plugin's hooks
only ever touch the **To-dos** section; Contexts and Decisions are
written directly by the agent (or by hand). Section-aware read/write
keeps those two sections intact when TodoWrite mirrors a new list.

Markdown checkbox grammar inside the To-dos section:
    - [ ] pending
    - [~] in_progress
    - [x] completed   (also [X])

CLI:
    todos_sync.py to-md        < tool_input.json   > to-dos.md fragment
    todos_sync.py to-json      < to-dos.md fragment > [{...}]
    todos_sync.py append "content" [--status ...] [--file <path>] [--idempotent]
    todos_sync.py mark "substr" --status completed [--file <path>]
    todos_sync.py count [--file <path>] [--unchecked-only]
    todos_sync.py extract <section> [--file <path>]   # print one section's body
    todos_sync.py --selftest

`--file` defaults to `$PWD/.agentwf/spec.md` (back-compat: also accepts
the old `$PWD/.agentwf/todos.md` if present). Section name defaults to
"To-dos" wherever it matters.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

# ── status / box mapping ────────────────────────────────────

STATUS_TO_BOX = {"pending": " ", "in_progress": "~", "completed": "x"}
BOX_TO_STATUS = {" ": "pending", "~": "in_progress", "x": "completed", "X": "completed"}

TODO_LINE = re.compile(r"^(\s*)-\s*\[([ xX~])\]\s*(.*)$")
H2 = re.compile(r"^##\s+(.+?)\s*$")
AUTHOR_MARKER_RE = re.compile(r"<!--\s*last-author:\s*(\w+)\s*-->")
# Strip HTML comments before counting/parsing checkboxes — template
# explainer comments use the same `- [ ] foo` syntax they document.
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

DEFAULT_SECTION = "To-dos"
SPEC_FILE_NAME = "spec.md"
LEGACY_FILE_NAME = "todos.md"

# Three-section skeleton used when spec.md doesn't exist yet.
EMPTY_SPEC = (
    "# Workspace spec\n<!-- last-author: claude -->\n\n"
    "## Contexts\n\n"
    "## Decisions\n\n"
    "## To-dos\n\n"
)

# ── section-aware text manipulation ────────────────────────

def split_sections(text: str) -> tuple[str, dict[str, str], list[str]]:
    """Return (preamble, sections, section_order).

    `preamble` is everything before the first `## Heading` line (typically
    the H1 title and the author marker). `sections` maps heading → body
    (without the heading line itself). `section_order` preserves the
    document's heading order so we can serialize back losslessly.
    """
    lines = text.splitlines()
    preamble: list[str] = []
    sections: dict[str, str] = {}
    order: list[str] = []
    current: str | None = None
    buf: list[str] = []
    for line in lines:
        m = H2.match(line)
        if m:
            if current is None:
                pass  # first section starts here
            else:
                sections[current] = "\n".join(buf).strip("\n")
            current = m.group(1).strip()
            order.append(current)
            buf = []
        elif current is None:
            preamble.append(line)
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip("\n")
    return ("\n".join(preamble).strip("\n"), sections, order)


def join_sections(preamble: str, sections: dict[str, str], order: list[str]) -> str:
    parts: list[str] = []
    if preamble.strip():
        parts.append(preamble.strip("\n"))
        parts.append("")  # blank between preamble and first section
    for name in order:
        body = sections.get(name, "").strip("\n")
        parts.append(f"## {name}")
        parts.append("")
        if body:
            parts.append(body)
            parts.append("")
    out = "\n".join(parts).rstrip() + "\n"
    return out


def get_section(text: str, name: str = DEFAULT_SECTION) -> str:
    _, sections, _ = split_sections(text)
    return sections.get(name, "")


def set_section(text: str, name: str, new_body: str) -> str:
    """Replace a section's body, preserving the rest of the file. If the
    file is empty or lacks the section, scaffold it from EMPTY_SPEC.
    """
    if not text.strip():
        text = EMPTY_SPEC
    preamble, sections, order = split_sections(text)
    sections[name] = new_body.strip("\n")
    if name not in order:
        order.append(name)
    return join_sections(preamble, sections, order)


# ── todo list ↔ markdown ───────────────────────────────────

def todos_to_section_body(todos: list[dict]) -> str:
    """Render a TodoWrite-shaped list into the *body* of the To-dos section
    (no `## To-dos` heading — that's added by `set_section`).
    """
    lines: list[str] = []
    for t in todos:
        if not isinstance(t, dict):
            continue
        content = (t.get("content") or "").strip()
        if not content:
            continue
        box = STATUS_TO_BOX.get(t.get("status", "pending"), " ")
        lines.append(f"- [{box}] {content}")
    return "\n".join(lines)


def section_body_to_todos(body: str) -> list[dict]:
    body = HTML_COMMENT.sub("", body)  # don't parse checkboxes inside comments
    out: list[dict] = []
    for line in body.splitlines():
        m = TODO_LINE.match(line)
        if not m:
            continue
        box, content = m.group(2), m.group(3).strip()
        if not content:
            continue
        out.append({
            "content": content,
            "status": BOX_TO_STATUS.get(box, "pending"),
            "activeForm": content,
        })
    return out


# Back-compat aliases — old name exposed so existing imports keep working.
def todos_to_md(todos: list[dict], author: str | None = None) -> str:
    """Render a *full* spec.md from a todo list. Used when the file
    doesn't exist yet — we scaffold all three sections, fill To-dos.
    """
    text = EMPTY_SPEC
    if author:
        text = re.sub(
            r"<!--\s*last-author:[^>]*-->",
            f"<!-- last-author: {author} -->",
            text,
            count=1,
        )
    return set_section(text, DEFAULT_SECTION, todos_to_section_body(todos))


def md_to_todos(text: str) -> list[dict]:
    """Return the to-dos parsed out of a spec.md (To-dos section only).

    For back-compat with files that have no `## To-dos` heading (legacy
    todos.md), fall back to scanning the entire body.
    """
    _, _, order = split_sections(text)
    if DEFAULT_SECTION in order:
        body = get_section(text, DEFAULT_SECTION)
    else:
        body = text  # legacy flat todos.md (no `## To-dos` heading)
    return section_body_to_todos(body)


def parse_last_author(text: str) -> str | None:
    for line in text.splitlines():
        m = AUTHOR_MARKER_RE.search(line)
        if m:
            return m.group(1)
    return None


# ── normalize hook payloads from either agent ──────────────

def normalize_payload(payload: dict) -> tuple[str, list[dict]]:
    if not isinstance(payload, dict):
        return ("unknown", [])
    tool = payload.get("tool_name", "")
    if tool == "TodoWrite":
        items = payload.get("tool_input", {}).get("todos", []) or []
        out = [
            {
                "content": (t.get("content") or "").strip(),
                "status": t.get("status", "pending"),
                "activeForm": t.get("activeForm") or t.get("content", ""),
            }
            for t in items
            if isinstance(t, dict) and (t.get("content") or "").strip()
        ]
        return ("claude", out)
    if tool == "update_plan":
        ti = payload.get("tool_input", {}) or {}
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
        out = [
            {
                "content": (p.get("step") or "").strip(),
                "status": p.get("status", "pending"),
                "activeForm": p.get("step", ""),
            }
            for p in (plan or [])
            if isinstance(p, dict) and (p.get("step") or "").strip()
        ]
        return ("codex", out)
    return ("unknown", [])


# ── file path resolution (spec.md preferred, todos.md back-compat) ──

def _resolve_file(file_arg: str | None) -> str:
    if file_arg:
        return file_arg
    cwd = os.getcwd()
    aw = os.path.join(cwd, ".agentwf")
    spec = os.path.join(aw, SPEC_FILE_NAME)
    legacy = os.path.join(aw, LEGACY_FILE_NAME)
    if os.path.exists(spec):
        return spec
    if os.path.exists(legacy):
        return legacy
    return spec  # default to writing the new path


def _read(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write(path: str, body: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)


# ── CLI commands ───────────────────────────────────────────

def cmd_to_md() -> None:
    payload = json.load(sys.stdin)
    if isinstance(payload, dict) and "tool_input" in payload:
        todos = payload.get("tool_input", {}).get("todos", [])
    elif isinstance(payload, dict) and "todos" in payload:
        todos = payload["todos"]
    elif isinstance(payload, list):
        todos = payload
    else:
        todos = []
    sys.stdout.write(todos_to_section_body(todos) + "\n")


def cmd_to_json() -> None:
    json.dump(section_body_to_todos(sys.stdin.read()), sys.stdout, indent=2)
    sys.stdout.write("\n")


def cmd_append(content: str, status: str, file_path: str, idempotent: bool) -> None:
    body_full = _read(file_path)
    todos_body = get_section(body_full, DEFAULT_SECTION) if body_full else ""
    todos = section_body_to_todos(todos_body)
    if idempotent and any(t["content"] == content for t in todos):
        return
    todos.append({"content": content, "status": status, "activeForm": content})
    new_section = todos_to_section_body(todos)
    new_full = set_section(body_full or EMPTY_SPEC, DEFAULT_SECTION, new_section)
    _write(file_path, new_full)


def cmd_mark(substr: str, status: str, file_path: str) -> None:
    body_full = _read(file_path)
    if not body_full:
        return
    todos_body = get_section(body_full, DEFAULT_SECTION)
    if not todos_body:
        return
    box = STATUS_TO_BOX.get(status, " ")
    out_lines: list[str] = []
    changed = False
    for line in todos_body.splitlines():
        m = TODO_LINE.match(line)
        if m and substr in m.group(3):
            indent = m.group(1)
            out_lines.append(f"{indent}- [{box}] {m.group(3).strip()}")
            changed = True
        else:
            out_lines.append(line)
    if changed:
        _write(file_path, set_section(body_full, DEFAULT_SECTION, "\n".join(out_lines)))


def cmd_count(file_path: str, unchecked_only: bool) -> None:
    body_full = _read(file_path)
    todos_body = get_section(body_full, DEFAULT_SECTION) if body_full else ""
    todos = section_body_to_todos(todos_body)
    if unchecked_only:
        todos = [t for t in todos if t["status"] != "completed"]
    print(len(todos))


def cmd_extract(section: str, file_path: str) -> None:
    sys.stdout.write(get_section(_read(file_path), section) + "\n")


# ── selftest ───────────────────────────────────────────────

def selftest() -> None:
    sample = [
        {"content": "Run setup.sh", "status": "completed", "activeForm": "Running"},
        {"content": "Confirm worktree", "status": "in_progress", "activeForm": "Confirming"},
        {"content": "Open PR", "status": "pending", "activeForm": "Opening"},
    ]
    md = todos_to_md(sample, author="claude")
    assert "## Contexts" in md and "## Decisions" in md and "## To-dos" in md, md
    assert "- [x] Run setup.sh" in md and "- [~] Confirm worktree" in md, md
    assert "<!-- last-author: claude -->" in md, md

    parsed = md_to_todos(md)
    assert len(parsed) == 3 and parsed[0]["status"] == "completed", parsed

    # set_section preserves Contexts and Decisions
    spec = md.replace("## Contexts\n", "## Contexts\n\n- repo uses uv\n")
    spec = spec.replace(
        "## Decisions\n",
        "## Decisions\n\n### D1: Pick lib\n**Status**: pending\n- [x] foo\n- [ ] bar\n",
    )
    new_spec = set_section(spec, "To-dos", "- [ ] new only")
    assert "- repo uses uv" in new_spec, "Contexts lost"
    assert "### D1: Pick lib" in new_spec, "Decisions lost"
    assert "- [ ] new only" in new_spec, "To-dos not replaced"
    assert "- [x] Run setup.sh" not in new_spec, "Old to-dos leaked"

    # idempotent append + mark
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "spec.md")
        cmd_append("Open PR", "pending", p, idempotent=False)
        cmd_append("Open PR", "pending", p, idempotent=True)
        ts = section_body_to_todos(get_section(_read(p), "To-dos"))
        assert sum(1 for t in ts if t["content"] == "Open PR") == 1, ts
        cmd_mark("Open PR", "completed", p)
        ts2 = section_body_to_todos(get_section(_read(p), "To-dos"))
        assert ts2[0]["status"] == "completed", ts2

    # legacy flat todos.md still parseable (no headings)
    legacy = "- [x] alpha\n- [ ] beta\n"
    parsed_legacy = md_to_todos(legacy)
    assert len(parsed_legacy) == 2, parsed_legacy

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

    ep = sub.add_parser("extract")
    ep.add_argument("section")
    ep.add_argument("--file", default=None)

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
    elif args.cmd == "extract":
        cmd_extract(args.section, _resolve_file(args.file))
    else:
        p.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
