# tmux-agents-workflow

A tmux-based, lightweight take on [Conductor](https://www.conductor.build/)'s
workflow surface — wrapped around [Claude Code](https://github.com/anthropics/claude-code)
and [Codex CLI](https://github.com/openai/codex) sessions.

```
.agentwf/                              # everything per-worktree, git-trackable
├── todos.md                           # source of truth (markdown checkboxes)
├── setup.sh                           # runs / shows up as todo on first session
├── archive.sh                         # tearing down the worktree (cache cleanup)
├── run.sh                             # long-running dev process (server, watcher)
└── prompts/
    ├── pr.md                          # injected before `gh pr create` / `aw-pr`
    ├── commit.md                      # injected before `git commit`
    ├── prefs.md                       # general repo preferences
    └── review.md                      # self-review checklist
```

Sibling to [`tmux-autoname-agent-sessions`](https://github.com/Luodian/tmux-autoname-agent-sessions)
(window naming) and [`tmux-coding-agents`](https://github.com/Luodian/tmux-coding-agents)
(picker / history). Each plugin handles one concern; combine them.

## What you get

| Capability | Mechanism |
|---|---|
| Per-worktree todo list, blocks `aw-pr` until unchecked items resolve | `.agentwf/todos.md` + `aw-pr` wrapper around `gh pr create` |
| Bidirectional sync with agent's plan tool | Claude `TodoWrite` / Codex `update_plan` → `PostToolUse` hook → file; file change → `UserPromptSubmit` `additionalContext` → agent |
| Auto-populated todos on session start | worktree-isolation gate, "Run setup.sh", "Open PR" sentinel |
| Per-commit diff window | `Stop` hook detects HEAD move → opens `lazygit` (or `git show HEAD | less`) in a background tmux window named `diff:<sha>` |
| Repo lifecycle scripts (setup / archive / run) | `aw-setup` / `aw-archive` / `aw-run`, with `$AW_ROOT` / `$AW_WORKSPACE` / `$AW_PORT` env, SIGHUP→200ms→SIGKILL nonconcurrent run mode |
| Repo-specific prompts injected just-in-time | `PreToolUse(Bash)` matches `gh pr create` / `git commit` → injects `prompts/{pr,commit}.md` as `additionalContext` |
| Multi-agent coexistence (Claude + Codex on the same workspace) | `<!-- last-author: claude\|codex -->` marker in todos.md; peer agent gets a "previous update from X" note on next turn |

## Install

### 1. Plugin (tmux side)

Via TPM, in `.tmux.conf`:

```tmux
set -g @plugin 'Luodian/tmux-agents-workflow'
```

`prefix + I` to install. Reload tmux.

### 2. Hooks (Claude / Codex side)

We do **not** modify your settings files automatically — most users have other
hooks (peon-ping, preflight, etc.) that blind merging would clobber.

```bash
# print both Claude Code (settings.json) and Codex CLI (hooks.json) patches:
~/.tmux/plugins/tmux-agents-workflow/install/install.sh

# or just one:
install.sh --claude
install.sh --codex
```

Each patch lists the events to extend; merge by hand into:
- Claude: `~/.claude/settings.json` (or project-local `.claude/settings.json`)
- Codex: `~/.codex/hooks.json`

### 3. Bootstrap a repo

In any git worktree:

```bash
~/.tmux/plugins/tmux-agents-workflow/scripts/aw-init
```

Creates `.agentwf/{setup,archive,run}.sh` + `.agentwf/prompts/*.md` with
sensible defaults inferred from repo signals (Python / Node / Rust / Go,
pre-commit, uv). Idempotent — won't overwrite existing files; `--force`
to overwrite. `--git-track` to `git add` the new files.

### 4. (Optional) `aw-pr` on PATH

```bash
ln -s ~/.tmux/plugins/tmux-agents-workflow/scripts/aw-pr ~/.local/bin/aw-pr
```

## Keybindings

| Key | Action |
|---|---|
| `prefix + t` | edit `.agentwf/todos.md` in popup |
| `prefix + D` | full `git diff HEAD` in popup |
| `prefix + S` | run `aw-setup` in popup |
| `prefix + A` | run `aw-archive` in popup |
| `prefix + R` | start dev process via `aw-run` (new background window `run:<workspace>`) |
| `prefix + M-r` | stop the running dev process (SIGHUP → 200ms → SIGKILL) |
| `prefix + I` | run `aw-init` in popup |

Override any binding via `set -g @aw_bind_<name>`. See `tmux-agents-workflow.tmux`.

## Configuration

```tmux
# Stop-hook diff window
set -g @aw_open_diff     'on'        # 'off' to disable auto-window
set -g @aw_diff_command  ''           # default: lazygit if on PATH, else git show | less

# Status-line counter (manual wire)
set -ag status-right ' #(~/.tmux/plugins/tmux-agents-workflow/scripts/status-todo-count.sh)'
```

## Markdown grammar

```
- [ ] pending item
- [~] in-progress item
- [x] completed item
<!-- last-author: claude|codex -->     ← optional authorship marker
```

`[~]` is non-standard but mirrors Claude TodoWrite / Codex update_plan's
three-state lifecycle. Lines that don't match the checkbox pattern (headers,
prose, the author marker) are preserved on round-trip.

## Conductor parity

| Conductor | Here |
|---|---|
| Setup script auto-run | `aw-setup` (manual) or todos.md prompt; `@aw_auto_setup on` opt-in to fire from SessionStart (planned) |
| Run script + nonconcurrent + SIGHUP→SIGKILL | `aw-run` exact match |
| Archive script | `aw-archive` |
| `$CONDUCTOR_*` env | `$AW_ROOT` / `$AW_WORKSPACE` / `$AW_PORT` |
| Diff viewer | tmux popup (`prefix + D`) + auto background window per commit |
| @todos in composer | `UserPromptSubmit` `additionalContext` injection |
| `conductor.json` team-shared config | `.agentwf/` is git-tracked |
| Slash commands / MCP | Claude Code / Codex CLI handle these directly |

## Files

```
tmux-agents-workflow.tmux         # TPM entry: keybindings + status widget
scripts/
  todos_sync.py                   # Claude TodoWrite & Codex update_plan ↔ markdown
  hook_post_todos.py              # PostToolUse — agent → file (--agent claude|codex)
  hook_prompt_submit.py           # UserPromptSubmit — file → agent + prompts index
  hook_pre_bash.py                # PreToolUse(Bash) — just-in-time prompt injection
  hook-session-start.sh           # SessionStart — seed auto-todos
  hook-stop-diff.sh               # Stop — lazygit window on HEAD move
  aw-init                         # bootstrap .agentwf/ scaffolding
  aw-setup / aw-archive / aw-run  # lifecycle script runners
  aw-pr                           # soft merge gate around `gh pr create`
  status-todo-count.sh            # optional status-line widget
  _aw_env.sh                      # shared env helper (AW_ROOT / AW_WORKSPACE / AW_PORT)
templates/
  prompts/{pr,prefs,commit,review}.md   # starter prompts copied by aw-init
install/
  claude-settings.json.patch      # Claude hook block template
  codex-hooks.json.patch          # Codex hook block template
  install.sh                      # prints resolved-path patches
```

## License

MIT
