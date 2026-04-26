# tmux-agents-workflow

A tmux plugin that adds a Conductor-style per-worktree todo list to your AI
coding agent sessions. Auto-populated by Claude Code / Codex hooks,
bidirectionally synced with the agent's built-in TodoWrite tool, gated
by a soft `aw-pr` wrapper that refuses to ship a PR with unchecked items.

```
.agentwf/todos.md            # source of truth (markdown checkbox file)
- [x] Run setup.sh
- [~] Validate changes
- [ ] Open PR via aw-pr
- [ ] Review commit a3f2b91 (Add foo bar)
```

Sibling to [`tmux-autoname-agent-sessions`](https://github.com/Luodian/tmux-autoname-agent-sessions)
(which only renames windows) and [`tmux-coding-agents`](https://github.com/Luodian/tmux-coding-agents)
(picker / history). Use them together; each handles a separate concern.

## What it does

1. **Per-worktree todo file** — `.agentwf/todos.md` lives at the git
   worktree root. Plain markdown, human-editable, agent-readable.
2. **Bidirectional TodoWrite sync** — when Claude Code calls TodoWrite,
   a PostToolUse hook overwrites `todos.md`. When you (or another hook)
   edit the file, a UserPromptSubmit hook surfaces the diff to the agent
   on its next turn so it can re-read.
3. **Auto-populated todos** — SessionStart adds e.g.
   "Confirm worktree isolation" if you launched on `main` / `master` /
   `amilabs`, "Run .agentwf/setup.sh" if a setup script is present, and
   a sentinel "Open PR via aw-pr".
4. **Stop-hook diff window** — when the agent turn ends and HEAD has
   moved, a new tmux window (`diff:<sha>`) is spawned in the background
   running `lazygit` (or `git show HEAD | less` as fallback). Append-only:
   one window per new commit, never per turn.
5. **Soft merge gate** — `aw-pr` wraps `gh pr create`; refuses to fire if
   any todo is still unchecked. `aw-pr --force` to bypass.

## Requirements

- tmux >= 3.2 (for `display-popup`)
- Python 3.8+ (parser uses stdlib only)
- `gh` (only for `aw-pr`)
- `lazygit` (optional; falls back to `git show | less`)
- Claude Code (or Codex CLI; Codex hook payload format may differ slightly
  — see Codex notes below)

## Install

### 1. Install the plugin

Via TPM, in your `.tmux.conf`:

```tmux
set -g @plugin 'Luodian/tmux-agents-workflow'
```

Reload tmux, install with `prefix + I`.

### 2. Wire up Claude Code hooks

The plugin's hooks need entries in `~/.claude/settings.json`. We do **not**
modify your settings.json automatically — most users have other hooks
(peon-ping, preflight, etc.) and blind merging would clobber them.

Run:

```bash
~/.tmux/plugins/tmux-agents-workflow/install/install.sh
```

This prints a ready-to-paste JSON snippet with the plugin path resolved.
Merge it into `~/.claude/settings.json` by hand: append each hook entry
to the existing `hooks.<EventName>[].hooks` array.

### 3. Optional: add `aw-pr` to PATH

```bash
ln -s ~/.tmux/plugins/tmux-agents-workflow/scripts/aw-pr ~/.local/bin/aw-pr
```

### 4. Optional: status-line counter

In `.tmux.conf`:

```tmux
set -ag status-right ' #(~/.tmux/plugins/tmux-agents-workflow/scripts/status-todo-count.sh)'
```

## Configuration

```tmux
# Default keybindings
set -g @aw_bind_edit  't'      # prefix + t : edit todos.md in popup
set -g @aw_bind_diff  'D'      # prefix + D : git diff in popup

# Stop-hook diff window
set -g @aw_open_diff     'on'  # 'off' to disable auto window
set -g @aw_diff_command  ''    # default: lazygit if available, else git show | less
```

## Markdown grammar

```
- [ ] pending item
- [~] in-progress item
- [x] completed item
```

`[~]` (in_progress) is non-standard but matches Claude TodoWrite's
three-state lifecycle. The parser also accepts `[X]` (case-insensitive
completed). Lines that don't match the checkbox pattern are preserved
on round-trip — feel free to keep section headers and notes alongside
the items.

## Codex / non-Claude agents

The Stop / SessionStart hooks are agent-agnostic — they fire on git
state. The bidirectional sync hooks (`UserPromptSubmit`,
`PostToolUse(TodoWrite)`) currently target Claude Code's payload schema.
Codex CLI's task-tracking tool emits a different schema; PRs adding
parsing for `TaskCreate` / `TaskUpdate` payloads welcome.

## Files

```
tmux-agents-workflow.tmux        # TPM entry: keybindings + status hook
scripts/
  todos_sync.py                  # bidirectional JSON ↔ markdown parser
  hook_post_todo_write.py        # PostToolUse(TodoWrite) — agent → file
  hook_prompt_submit.py          # UserPromptSubmit       — file → agent
  hook-session-start.sh          # SessionStart           — seed auto-todos
  hook-stop-diff.sh              # Stop                   — open lazygit window
  aw-pr                          # soft merge gate around gh pr create
  status-todo-count.sh           # optional status-line widget
install/
  settings.json.patch            # template hook block
  install.sh                     # prints resolved-path snippet
```

## License

MIT
