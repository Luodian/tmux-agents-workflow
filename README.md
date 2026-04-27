# tmux-agents-workflow

A tmux-based, lightweight take on [Conductor](https://www.conductor.build/)'s
workflow surface — wrapped around [Claude Code](https://github.com/anthropics/claude-code)
and [Codex CLI](https://github.com/openai/codex) sessions.

**Policy: `.agentwf/` is local-only.** `aw-init` auto-appends it to your repo's `.gitignore` — per-task spec files are transient, lifecycle scripts are user-customized, and durable summaries land in `docs/tasks/<slug>/report.md` via `aw-summarize` at task close.

```
.agentwf/                              # gitignored; regenerable via aw-init
├── spec.md                            # live spec (single-spec layout)
├── <name>_spec.md                     # named spec (multi-spec layout)
├── active-spec                        # one-line pointer: which *_spec.md is active
├── setup.sh                           # runs / shows up as todo on first session
├── archive.sh                         # tearing down the worktree (cache cleanup)
├── run.sh                             # long-running dev process (server, watcher)
└── prompts/
    ├── pr.md                          # injected before `gh pr create` / `aw-pr`
    ├── commit.md                      # injected before `git commit`
    ├── prefs.md                       # general repo preferences
    └── review.md                      # self-review checklist
```

The plugin resolves the active spec via, in order: the `AW_SPEC` env var
(if set), `.agentwf/active-spec` pointer, `spec.md` (regular file or
symlink), or a unique `*_spec.md` glob. Single-spec workflows keep using
`spec.md` unchanged. Run `aw-spec list` / `aw-spec switch <name>` /
`aw-spec new <name>` to manage multi-spec layouts.

The active spec has three top-level sections — agent maintains all three, user
edits any of them in Neovim (opens in a right-side split pane with the worktree
root as cwd when a spec already exists; simple tasks without a spec → no
auto-pane, create one explicitly via `aw-spec new <name>` when warranted):

```markdown
## Contexts          # observations, premises, constraints discovered
## Decisions         # `### Dn: <title>` blocks with checkbox options +
                     # `**Recommended**` pick — agent proceeds with the
                     # [x]'d option, user overrides by re-checking
## To-dos            # bidirectionally synced with TodoWrite / update_plan
```

Decisions section is the **non-blocking** alternative to AskUserQuestion-
style click popups — agent appends a decision, picks Recommended, keeps
working; user reviews in Neovim and can change the `[x]` to override at
their leisure. Use AskUserQuestion only when you genuinely can't
proceed without the answer.

Sibling to [`tmux-autoname-agent-sessions`](https://github.com/Luodian/tmux-autoname-agent-sessions)
(window naming) and [`tmux-coding-agents`](https://github.com/Luodian/tmux-coding-agents)
(picker / history). Each plugin handles one concern; combine them.

## What you get

**Linear integration.** Linear is treated as a bidirectional context medium — outbound (spec.md → issue body / comments) and inbound (issue description + comments → spec.md > Contexts). `aw-link` binds the current task to a Linear issue; `.agentwf/.linear-issue` (gitignored) holds the binding.

- **Outbound**: `aw-link` (create new) / `--update` (sync body) / `--comment` (progress) / `--close` (transition to Done). `aw-summarize` auto-comments the report when linked.
- **Inbound**: `aw-link --search "query"` finds candidate issues; `aw-link --bind BRI-12` binds an existing issue and auto-runs `--import` to pull description + last 20 comments into `spec.md > Contexts` so the agent sees prior history.
- **SessionStart proposal**: when entering an unbound worktree with `LINEAR_API_KEY` set, the SessionStart hook runs a fuzzy search using `branch + last commit subject` and appends a `### D-bind:` Decision block to `spec.md > Decisions` with the top candidates. Non-blocking — agent proceeds; user re-checks `[x]` to override the Recommended pick. Disable with `set -g @aw_linear_consent skip`.
- **Auto-comment on commits**: when linked + `@aw_linear_auto_comment on` (default), every new HEAD posts a `Commit \`<sha>\` — <subject>` comment. Disable with `set -g @aw_linear_auto_comment off`.

Auth: `LINEAR_API_KEY` env var or `~/.claude/credentials/linear-api-key`. Set `LINEAR_TEAM_ID` only if multiple teams reachable (single-team accounts auto-pick).

| Capability | Mechanism |
|---|---|
| Per-worktree todo list, blocks `aw-pr` until unchecked items resolve | `.agentwf/spec.md` + `aw-pr` wrapper around `gh pr create` |
| Bidirectional sync with agent's plan tool | Claude `TodoWrite` / Codex `update_plan` → `PostToolUse` hook → file; file change → `UserPromptSubmit` `additionalContext` → agent |
| Auto-populated todos on session start | worktree-isolation gate, "Run setup.sh", "Open PR" sentinel |
| Per-commit diff review | `Stop` hook detects HEAD move → refocuses the diff pane (`@aw_spec_pane`) if alive in the current tmux window, else spawns a fresh split-right pane (cwd = worktree root). Opens `nvim <spec>` when a spec exists, else `nvim <worktree-root>` so simple tasks without a spec still get a diff-review pane on commit. Opt into a custom split-right pane via `@aw_diff_command`. |
| Repo lifecycle scripts (setup / archive / run) | `aw-setup` / `aw-archive` / `aw-run`, with `$AW_ROOT` / `$AW_WORKSPACE` / `$AW_PORT` env, SIGHUP→200ms→SIGKILL nonconcurrent run mode |
| Repo-specific prompts injected just-in-time | `PreToolUse(Bash)` matches `gh pr create` / `git commit` → injects `prompts/{pr,commit}.md` as `additionalContext` |
| Multi-agent coexistence (Claude + Codex on the same workspace) | `<!-- last-author: claude\|codex -->` marker in spec.md; peer agent gets a "previous update from X" note on next turn |

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
| `prefix + t` | open the active `.agentwf/<spec>` in nvim split pane (right, idempotent) |
| `prefix + T` | interactive spec switcher (registered when `fzf` is on PATH) |
| `prefix + e` | edit the active spec in a transient popup (raw editor) |
| `prefix + D` | full `git diff HEAD` in popup |
| `prefix + S` | run `aw-setup` in popup |
| `prefix + A` | run `aw-archive` in popup |
| `prefix + R` | start dev process via `aw-run` (new background window `run:<workspace>`) |
| `prefix + M-r` | stop the running dev process (SIGHUP → 200ms → SIGKILL) |
| `prefix + I` | run `aw-init` in popup |
| `prefix + L` | bind/sync to a Linear issue (auto: create if unlinked, `--update` if linked) |

Override any binding via `set -g @aw_bind_<name>`. See `tmux-agents-workflow.tmux`.

## Configuration

```tmux
# Stop-hook diff review (default: refocus existing diff pane if alive, else
# spawn new). Pane target is `nvim <spec>` when a spec exists, else
# `nvim <worktree-root>` so simple tasks without a spec still get a pane
# on commit.
set -g @aw_open_diff     'on'        # 'off' to disable the on-commit pane
set -g @aw_diff_command  ''          # if set, run as a split-right pane on each HEAD move
                                     # e.g. 'cd "$AW_ROOT" && lazygit'

# Auto-spawn the spec nvim pane (worktree root as cwd) on Claude/Codex session start.
# Fires ONLY when a spec already exists in `.agentwf/`; tasks without a spec do
# not trigger a pane. Create a spec explicitly via `aw-spec new <name>` (or the
# agent's `/spec` slash command) when the task warrants tracking.
set -g @aw_auto_spec     'on'        # 'off' to disable

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

## Multi-spec layout

A worktree can carry several specs side-by-side — useful when one repo
hosts multiple in-flight efforts. File naming is `<name>_spec.md`; the
active one is tracked in a single-line `.agentwf/active-spec` pointer.

```bash
aw-spec list                 # show every *_spec.md (active marked '*')
aw-spec new install          # scaffold install_spec.md, set active, open
aw-spec switch refactor      # swap active to refactor_spec.md
aw-spec switch               # interactive picker (requires fzf)
aw-spec --print-active       # absolute path of the active spec
```

Resolution falls through these layers, so single-spec setups keep working:

1. `AW_SPEC` env var (per-command override).
2. `.agentwf/active-spec` (one line: `name_spec.md`).
3. `.agentwf/spec.md` — regular file or a symlink to a named spec.
4. A unique `*_spec.md` (no ambiguity → it wins).
5. Default: create `spec.md` from the template.

Hooks (`hook_post_todos.py`, `hook_prompt_submit.py`, `hook-stop-diff.sh`,
`status-todo-count.sh`, `aw-pr`, `aw-link`, `aw-summarize`) all read and
write through the same resolver, so flipping `active-spec` retargets the
whole workflow without touching any other file.

## Conductor parity

| Conductor | Here |
|---|---|
| Setup script auto-run | `aw-setup` (manual) or spec.md prompt; `@aw_auto_setup on` opt-in to fire from SessionStart (planned) |
| Run script + nonconcurrent + SIGHUP→SIGKILL | `aw-run` exact match |
| Archive script | `aw-archive` |
| `$CONDUCTOR_*` env | `$AW_ROOT` / `$AW_WORKSPACE` / `$AW_PORT` |
| Diff viewer | tmux popup (`prefix + D`) + Stop-hook refocus of the spec nvim pane (or custom `@aw_diff_command` split-right pane) |
| @todos in composer | `UserPromptSubmit` `additionalContext` injection |
| `conductor.json` team-shared config | `.agentwf/` is local-only (gitignored); durable summaries land in `docs/tasks/<slug>/report.md` via `aw-summarize` |
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
  hook-stop-diff.sh               # Stop — refocus spec nvim pane on HEAD move
  aw-init                         # bootstrap .agentwf/ scaffolding
  aw-spec list|switch|new         # multi-spec management (active resolution helpers)
  aw-setup / aw-archive / aw-run  # lifecycle script runners
  aw-pr                           # soft merge gate around `gh pr create`
  aw-summarize                    # distill spec.md → workspace docs/tasks/<slug>/report.md (+ Linear comment if linked)
  _aw_summarize.py                # internal renderer for aw-summarize
  aw-link                         # bind task to a Linear issue (create / --update / --comment / --close / --status / --teams)
  status-todo-count.sh            # optional status-line widget
  _aw_env.sh                      # shared env helper (AW_ROOT / AW_WORKSPACE / AW_PORT)
  _aw_lib.sh                      # shared spec-resolution helper (active spec + listing)
templates/
  prompts/{pr,prefs,commit,review}.md   # starter prompts copied by aw-init
install/
  claude-settings.json.patch      # Claude hook block template
  codex-hooks.json.patch          # Codex hook block template
  install.sh                      # prints resolved-path patches
```

## License

MIT
