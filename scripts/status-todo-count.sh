#!/usr/bin/env bash
# Optional status-line widget: prints "N todo" if there are unchecked items
# in the current pane's worktree, blank otherwise.
#
# Wire it into status-right with:
#   set -ag status-right ' #(~/.tmux/plugins/tmux-agents-workflow/scripts/status-todo-count.sh)'

set -euo pipefail

# tmux passes nothing useful via env here; resolve cwd via tmux client itself.
pane_path="$(tmux display -p '#{pane_current_path}' 2>/dev/null || true)"
[[ -n "$pane_path" ]] || exit 0

root="$(git -C "$pane_path" rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$root" ]] || exit 0

todo_file="$root/.agentwf/todos.md"
[[ -f "$todo_file" ]] || exit 0

n="$(grep -cE '^\s*-\s*\[[ ~]\]' "$todo_file" 2>/dev/null || echo 0)"
[[ "$n" -gt 0 ]] || exit 0

printf '%s todo' "$n"
