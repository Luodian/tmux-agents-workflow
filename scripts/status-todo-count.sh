#!/usr/bin/env bash
# Optional status-line widget: prints "N todo" when there are unchecked
# items in the current pane's worktree's .agentwf/spec.md > To-dos.

set -euo pipefail
trap '' PIPE

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC="$HERE/todos_sync.py"
# shellcheck source=_aw_lib.sh
. "$HERE/_aw_lib.sh"

pane_path="$(tmux display -p '#{pane_current_path}' 2>/dev/null || true)"
[[ -n "$pane_path" ]] || exit 0

root="$(git -C "$pane_path" rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$root" ]] || exit 0

spec="$(aw_resolve_spec "$root")"
[[ -f "$spec" ]] || exit 0

n="$(python3 "$SYNC" count --file "$spec" --unchecked-only 2>/dev/null || echo 0)"
[[ "$n" -gt 0 ]] || exit 0

printf '%s todo' "$n"
