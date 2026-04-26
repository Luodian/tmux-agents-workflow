#!/usr/bin/env bash
# Stop hook: detect HEAD movement during the agent turn; if a new commit
# landed, append a "Review commit <sha>" todo and (optionally) open lazygit
# in a new tmux window so the user can scrub the diff out-of-band.
#
# Trigger discipline: opens at most one new window per HEAD change. The
# previous HEAD is cached at .agentwf/.last-head — we only fire when the
# cached value differs from the current rev.
#
# Configuration (tmux options):
#   @aw_diff_command   command run inside the new window. Default:
#                      "lazygit" if on PATH, else "git -c color.ui=always show --stat -p HEAD | less -R"
#   @aw_open_diff      "on" (default) | "off" — disable auto-window entirely

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC="$HERE/todos_sync.py"

root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$root" ]] || exit 0

aw="$root/.agentwf"
mkdir -p "$aw"
last_head_file="$aw/.last-head"
todo_file="$aw/todos.md"

current="$(git -C "$root" rev-parse HEAD 2>/dev/null || true)"
[[ -n "$current" ]] || exit 0

last=""
[[ -f "$last_head_file" ]] && last="$(<"$last_head_file")"

# Always update the snapshot so a subsequent `git reset` back to the same
# rev doesn't re-trigger.
printf '%s\n' "$current" > "$last_head_file"

if [[ "$current" == "$last" ]]; then
  exit 0
fi

short="${current:0:7}"
subject="$(git -C "$root" log -1 --pretty=%s "$current" 2>/dev/null || echo "")"
python3 "$SYNC" append "Review commit $short ($subject)" \
  --status pending --file "$todo_file" --idempotent

# Only open a tmux window if we're inside tmux and the user hasn't disabled it.
[[ -n "${TMUX:-}" ]] || exit 0

opt() {
  tmux show-option -gqv "$1" 2>/dev/null || true
}
enabled="$(opt '@aw_open_diff')"
enabled="${enabled:-on}"
[[ "$enabled" == "on" ]] || exit 0

cmd="$(opt '@aw_diff_command')"
if [[ -z "$cmd" ]]; then
  if command -v lazygit >/dev/null 2>&1; then
    cmd="cd '$root' && lazygit"
  else
    cmd="cd '$root' && git -c color.ui=always show --stat -p HEAD | less -R"
  fi
fi

# `-d` keeps the agent window focused; `-a` puts the new window adjacent.
# Window name = "diff:<sha>" so the autoname plugin won't fight us
# (it only renames windows whose pane runs an interactive claude/codex).
tmux new-window -d -a -n "diff:$short" "$cmd" 2>/dev/null || true
