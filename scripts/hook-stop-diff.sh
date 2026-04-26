#!/usr/bin/env bash
# Stop hook: detect HEAD movement during the agent turn; if a new commit
# landed, append a "Review commit <sha>" todo to .agentwf/spec.md > To-dos
# and optionally open lazygit in a new tmux window so the user can scrub
# the diff out-of-band.
#
# Trigger discipline: opens at most one new window per HEAD change.
# Configuration (tmux options):
#   @aw_diff_command   command run inside the new window. Default:
#                      "lazygit" if on PATH, else "git -c color.ui=always show --stat -p HEAD | less -R"
#   @aw_open_diff      "on" (default) | "off"

set -euo pipefail
trap '' PIPE

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC="$HERE/todos_sync.py"

root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$root" ]] || exit 0

aw="$root/.agentwf"
mkdir -p "$aw"
spec="$aw/spec.md"
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

# Only spawn a tmux window if we're inside tmux and not disabled.
[[ -n "${TMUX:-}" ]] || exit 0

opt() { tmux show-option -gqv "$1" 2>/dev/null || true; }
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

tmux new-window -d -a -n "diff:$short" "$cmd" 2>/dev/null || true

# System notification when the user isn't watching: summarize unresolved
# work (unchecked todos + pending Decisions). Silent failure if no
# backend is available.
notify_msg="$(python3 - "$root" <<'PY' 2>/dev/null || true
import os, re, sys
root = sys.argv[1]
spec = os.path.join(root, ".agentwf", "spec.md")
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
