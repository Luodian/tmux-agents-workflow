#!/usr/bin/env bash
# Stop hook: detect HEAD movement during the agent turn; if a new commit
# landed, append a "Review commit <sha>" todo to .agentwf/spec.md > To-dos
# and surface a Neovim view of the worktree workspace so the user can
# scrub the diff inside their own editor (fugitive / gitsigns / netrw),
# rather than getting a separate lazygit window pushed at them.
#
# Default: refocus / spawn the spec.md nvim pane via `aw-spec` — that
# pane has cwd = worktree root, so it doubles as the diff workspace.
# Idempotent (`@aw_spec_pane` tracking inside aw-spec).
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
python3 "$SYNC" append "Review commit $short ($subject)" \
  --status pending --file "$spec" --idempotent

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
  # Default: focus / spawn the spec.md nvim pane. cwd is the worktree
  # root, so it doubles as the diff workspace.
  AW_ROOT="$root" "$HERE/aw-spec" >/dev/null 2>&1 || true
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
