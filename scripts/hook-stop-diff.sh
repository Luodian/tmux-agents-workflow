#!/usr/bin/env bash
# Stop hook: detect HEAD movement during the agent turn; if a new commit
# landed, append a "Review commit <sha>" todo to spec.md > To-dos (only
# when a spec exists — simple tasks don't get a forced spec scaffold) and
# surface a Neovim view of the worktree so the user can scrub the diff
# inside their own editor (fugitive / gitsigns / netrw), rather than
# getting a separate lazygit window pushed at them.
#
# Default pane behavior on every HEAD move:
#   - refocus the existing diff pane (`@aw_spec_pane`) if it's still alive
#     in the current tmux window, OR
#   - spawn a fresh split-right pane (cwd = worktree root) if not.
#
# Pane target:
#   - `nvim <spec>` when a spec exists (doubles as the spec editor).
#   - `nvim <worktree-root>` when no spec exists, so simple tasks still
#     get a diff-review pane on commit — just navigated free-form via
#     netrw / Telescope rather than anchored on spec.md.
#
# Configuration (tmux options):
#   @aw_open_diff      "on" (default) | "off"
#   @aw_diff_command   if set, run as a split-right pane (-h -p 35) on
#                      every HEAD move; replaces the default refocus.
#                      Use this if you prefer lazygit or a custom view.
#                      Example: set -g @aw_diff_command 'cd "$AW_ROOT" && lazygit'

set -euo pipefail
trap '' PIPE

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC="$HERE/todos_sync.py"
# shellcheck source=_aw_lib.sh
. "$HERE/_aw_lib.sh"

root="$(aw_repo_root)"
[[ -n "$root" ]] || exit 0

aw="$root/.agentwf"
mkdir -p "$aw"
spec="$(aw_resolve_spec "$root")"
last_head_file="$aw/.last-head"

current="$(git -C "$root" rev-parse HEAD 2>/dev/null || true)"
[[ -n "$current" ]] || exit 0

last=""
[[ -f "$last_head_file" ]] && last="$(<"$last_head_file")"
printf '%s\n' "$current" > "$last_head_file"

[[ "$current" != "$last" ]] || exit 0

short="${current:0:7}"
subject="$(git -C "$root" log -1 --pretty=%s "$current" 2>/dev/null || echo "")"

# "Review commit" todo only when a spec exists — don't force-scaffold one
# on commit just to record the review (simple tasks stay simple).
if [[ -s "$spec" ]]; then
  python3 "$SYNC" append "Review commit $short ($subject)" \
    --status pending --file "$spec" --idempotent
fi

# Pane spawn / refocus only meaningful when we're inside tmux.
[[ -n "${TMUX:-}" ]] || exit 0

opt() { tmux show-option -gqv "$1" 2>/dev/null || true; }
enabled="$(opt '@aw_open_diff')"
enabled="${enabled:-on}"
[[ "$enabled" == "on" ]] || exit 0

cmd="$(opt '@aw_diff_command')"
if [[ -n "$cmd" ]]; then
  # User opted into a custom diff view — honor it as a split-right pane.
  tmux split-window -h -l 35% -d -c "$root" "$cmd" 2>/dev/null || true
else
  # Default: refocus the diff pane if alive in this window, else spawn a
  # new one. We do NOT delegate to aw-spec here because aw-spec gates on
  # spec-existence (so simple tasks would get no diff pane at all). Inline
  # the pane logic so the diff review fires on every commit regardless of
  # whether a spec exists; @aw_spec_pane stays the single tracking key.
  pane="$(tmux show-options -wv @aw_spec_pane 2>/dev/null || true)"
  alive=0
  if [[ -n "$pane" ]] && tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -qx "$pane"; then
    alive=1
  fi
  if [[ "$alive" -eq 1 ]]; then
    tmux select-pane -t "$pane" 2>/dev/null || true
  else
    editor="${EDITOR:-nvim}"
    if [[ -s "$spec" ]]; then
      launch_cmd="cd '$root' && $editor '$spec'"
    else
      launch_cmd="cd '$root' && $editor '$root'"
    fi
    new_pane="$(tmux split-window -h -l 35% -P -F '#{pane_id}' -c "$root" "$launch_cmd" 2>/dev/null || true)"
    if [[ -n "$new_pane" ]]; then
      tmux set-option -w @aw_spec_pane "$new_pane" 2>/dev/null || true
    fi
  fi
fi

# System notification when the user isn't watching: summarize unresolved
# work (unchecked todos + pending Decisions). Silent failure if no
# backend is available.
notify_msg="$(AW_SCRIPTS="$HERE" python3 - "$root" <<'PY' 2>/dev/null || true
import os, re, sys
sys.path.insert(0, os.environ["AW_SCRIPTS"])
from todos_sync import resolve_spec_path
root = sys.argv[1]
spec = resolve_spec_path(root)
if not os.path.exists(spec):
    sys.exit(0)
text = open(spec).read()
unchecked = len(re.findall(r"^\s*-\s*\[[ ~]\]", text, re.M))
pending_decisions = len(re.findall(r"\*\*Status\*\*:\s*pending", text, re.I))
parts = []
if unchecked: parts.append(f"{unchecked} todo")
if pending_decisions: parts.append(f"{pending_decisions} pending decision")
if parts: print(", ".join(parts))
PY
)"
if [[ -n "$notify_msg" ]]; then
  "$HERE/aw-notify" "agent stopped on commit $short" "$notify_msg" 2>/dev/null || true
fi

# ── Linear V2: auto-comment on commits when linked ─────────
# Best-effort; silent fail (e.g. offline, token revoked) doesn't block
# the rest of the Stop hook.
if [[ -f "$aw/.linear-issue" ]]; then
  auto_comment="$(opt '@aw_linear_auto_comment')"
  auto_comment="${auto_comment:-on}"
  if [[ "$auto_comment" == "on" ]]; then
    "$HERE/aw-link" --comment "Commit \`$short\` — $subject" 2>/dev/null || true
  fi
fi
