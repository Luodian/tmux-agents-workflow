#!/usr/bin/env bash
# SessionStart hook: ensure .agentwf/spec.md exists with the three-section
# skeleton, seed automatic todos based on environment, and (when running
# inside tmux) optionally spawn the spec pane via aw-spec.
#
# Auto-todos (idempotent — never duplicate):
#   - "Confirm worktree isolation"  if HEAD is on main / master / amilabs
#   - "Run .agentwf/setup.sh"       if setup.sh exists and .setup-done missing
#   - "Open PR via aw-pr"            sentinel; last to check off
#
# Auto-spawn the Neovim spec pane when:
#   - $TMUX is set (we're inside a tmux session), AND
#   - tmux option `@aw_auto_spec` is on (default: on)

set -euo pipefail
trap '' PIPE

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC="$HERE/todos_sync.py"
TEMPLATES_DIR="$(cd "$HERE/../templates" 2>/dev/null && pwd || true)"

root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$root" ]] || exit 0

aw="$root/.agentwf"
mkdir -p "$aw"
spec="$aw/spec.md"

# Migrate legacy .agentwf/todos.md (if it exists and spec.md doesn't yet).
if [[ -f "$aw/todos.md" && ! -s "$spec" ]]; then
  printf '# Workspace spec\n<!-- last-author: claude -->\n\n## Contexts\n\n## Decisions\n\n## To-dos\n\n' > "$spec"
  cat "$aw/todos.md" >> "$spec"
  mv "$aw/todos.md" "$aw/todos.md.migrated.bak"
fi

# Scaffold from template if missing.
if [[ ! -s "$spec" ]]; then
  if [[ -f "$TEMPLATES_DIR/spec.md" ]]; then
    cp "$TEMPLATES_DIR/spec.md" "$spec"
  else
    printf '# Workspace spec\n<!-- last-author: claude -->\n\n## Contexts\n\n## Decisions\n\n## To-dos\n\n' > "$spec"
  fi
fi

append() {
  python3 "$SYNC" append "$1" --status pending --file "$spec" --idempotent
}

branch="$(git -C "$root" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")"
case "$branch" in
  main|master|amilabs)
    append "Confirm worktree isolation (currently on $branch)" ;;
esac

if [[ -x "$aw/setup.sh" && ! -f "$aw/.setup-done" ]]; then
  append "Run .agentwf/setup.sh"
fi

append "Open PR via aw-pr"

# Auto-spawn the Neovim spec pane.
if [[ -n "${TMUX:-}" ]]; then
  auto="$(tmux show-option -gqv '@aw_auto_spec' 2>/dev/null || true)"
  auto="${auto:-on}"
  if [[ "$auto" == "on" ]]; then
    "$HERE/aw-spec" 2>/dev/null || true
  fi
fi
