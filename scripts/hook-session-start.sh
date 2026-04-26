#!/usr/bin/env bash
# SessionStart hook: initialise .agentwf/ for the current worktree and seed
# automatic todos based on environmental signals.
#
# Auto-todos seeded here:
#   - "Confirm worktree isolation"  if HEAD is on main / master / amilabs
#   - "Run .agentwf/setup.sh"       if a setup.sh exists and .setup-done is missing
#   - "Open PR"                      always present (sentinel; last to check off)
#
# Idempotent — re-running on the same worktree won't duplicate items.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC="$HERE/todos_sync.py"

# Resolve worktree root from cwd. The hook's stdin payload includes "cwd",
# but we trust pwd here since Claude Code spawns hooks from the project dir.
root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$root" ]] || exit 0

aw="$root/.agentwf"
mkdir -p "$aw"
todo_file="$aw/todos.md"
[[ -f "$todo_file" ]] || printf '# Workspace todos\n\n' > "$todo_file"

append() {
  python3 "$SYNC" append "$1" --status pending --file "$todo_file" --idempotent
}

# 1. Worktree isolation gate — only on canonical trunks.
branch="$(git -C "$root" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")"
case "$branch" in
  main|master|amilabs)
    append "Confirm worktree isolation (currently on $branch)"
    ;;
esac

# 2. Setup script.
if [[ -x "$aw/setup.sh" && ! -f "$aw/.setup-done" ]]; then
  append "Run .agentwf/setup.sh"
fi

# 3. Validate script — added passively so users see it; only triggers when
#    a write happens (PostToolUse(Edit/Write)) — see hook-post-edit.sh
#    (not implemented in v1; users who want it can add it via append-on-edit).

# 4. PR sentinel.
append "Open PR via aw-pr"
