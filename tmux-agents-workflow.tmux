#!/usr/bin/env bash
# TPM entry point for tmux-agents-workflow.
#
# Sibling to tmux-autoname-agent-sessions and tmux-coding-agents. Adds a
# Conductor-style per-worktree todo list (`.agentwf/todos.md`) that is
# bidirectionally synced with Claude Code's TodoWrite tool, plus tmux
# keybindings to view and edit it. Hook scripts under scripts/ are
# wired into Claude Code via install/settings.json.patch — this .tmux
# file only registers tmux-side keybindings and the optional status segment.

CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

tmux_opt() {
  local value
  value="$(tmux show-option -gqv "$1" 2>/dev/null)"
  printf '%s\n' "${value:-$2}"
}

normalize_key() {
  case "$1" in
    ''|off|none|disabled|disable) printf '\n' ;;
    *) printf '%s\n' "$1" ;;
  esac
}

# Resolve worktree root from current pane's cwd (#{pane_current_path}).
# The bound shell snippet is evaluated by tmux's run-shell, which inherits
# the pane's working directory.
git_root_expr='$(git -C "$(tmux display -p "#{pane_current_path}")" rev-parse --show-toplevel 2>/dev/null)'

# ── prefix + t : edit .agentwf/todos.md in a popup ──────────
edit_key="$(normalize_key "$(tmux_opt '@aw_bind_edit' 't')")"
if [[ -n "$edit_key" ]]; then
  tmux bind-key "$edit_key" display-popup -E -w 80% -h 80% \
    "root=$git_root_expr; mkdir -p \"\$root/.agentwf\"; \${EDITOR:-vi} \"\$root/.agentwf/todos.md\""
fi

# ── prefix + D : git diff popup (on-demand fallback) ────────
diff_key="$(normalize_key "$(tmux_opt '@aw_bind_diff' 'D')")"
if [[ -n "$diff_key" ]]; then
  tmux bind-key "$diff_key" display-popup -E -w 90% -h 90% \
    "root=$git_root_expr; cd \"\$root\" && (git -c color.ui=always diff --stat HEAD; echo; git -c color.ui=always diff HEAD) | less -R"
fi

# ── status-line: optional todo counter ──────────────────────
# User can `set -ag status-right '#(...)'` to embed; we provide the script.
status_widget="$CURRENT_DIR/scripts/status-todo-count.sh"
chmod +x "$status_widget" 2>/dev/null || true
