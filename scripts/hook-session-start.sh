#!/usr/bin/env bash
# SessionStart hook: ensure .agentwf/spec.md exists with the three-section
# skeleton, seed automatic todos based on environment, and (opt-in only)
# spawn the spec pane via aw-spec.
#
# Auto-todos (idempotent — never duplicate):
#   - "Confirm worktree isolation"  if HEAD is on main / master / amilabs
#   - "Run .agentwf/setup.sh"       if setup.sh exists and .setup-done missing
#   - "Open PR via aw-pr"            sentinel; last to check off
#
# Auto-spawn the Neovim spec pane is OFF by default at SessionStart.
# Rationale: at session start the agent has not yet touched the spec this
# session, so any existing `.agentwf/spec.md` is stale-by-default for the
# current task — popping nvim on it conflates "spec exists" with "spec is
# for this task". The Stop hook (hook-stop-diff.sh) handles spec-pane
# spawn on first commit when the agent actually edited the spec this
# session (mtime moved past the SessionStart baseline this hook records).
# Set `@aw_auto_spec=on` to restore legacy eager-open at boot.

set -euo pipefail
trap '' PIPE

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC="$HERE/todos_sync.py"
TEMPLATES_DIR="$(cd "$HERE/../templates" 2>/dev/null && pwd || true)"
# shellcheck source=_aw_lib.sh
. "$HERE/_aw_lib.sh"

root="$(aw_repo_root)"
[[ -n "$root" ]] || exit 0

aw="$root/.agentwf"
mkdir -p "$aw"
spec="$(aw_resolve_spec "$root")"

# Capture the tmux pane/window/session that launched this Claude/Codex agent
# session. Later Stop hooks may run while another tmux session is active, so
# pane/window creation must target these stable IDs instead of tmux defaults.
aw_tmux_capture_origin "$root"

# Record spec mtime baseline. The Stop hook (hook-stop-diff.sh) compares
# against this to decide whether the spec is the editor target on commit —
# only when the agent actually touched it this session. 0 marks "no spec
# at session start". Portable across BSD (macOS) and GNU stat.
if [[ -e "$spec" ]]; then
  baseline_mtime="$(stat -f '%m' -- "$spec" 2>/dev/null \
    || stat -c '%Y' -- "$spec" 2>/dev/null \
    || echo 0)"
else
  baseline_mtime=0
fi
echo "$baseline_mtime" > "$aw/.spec-mtime-at-session-start"

# Migrate legacy .agentwf/todos.md (if it exists and the active spec is empty).
if [[ -f "$aw/todos.md" && ! -s "$spec" ]]; then
  printf '# Workspace spec\n<!-- last-author: claude -->\n\n## Contexts\n\n## Decisions\n\n## To-dos\n\n' > "$spec"
  cat "$aw/todos.md" >> "$spec"
  mv "$aw/todos.md" "$aw/todos.md.migrated.bak"
fi

# Spec-gated: if no spec exists yet, this worktree is in "simple task" mode —
# don't scaffold, don't seed todos, don't auto-spawn the nvim pane, don't
# propose Linear bindings. Create a spec explicitly via `aw-spec new <name>`
# (or the agent's `/spec` slash command) when the task warrants tracking.
if [[ ! -s "$spec" ]]; then
  exit 0
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

# Auto-spawn the Neovim spec pane (opt-in only). Default OFF — see the
# rationale in the file header. Manual on-demand: `prefix + t` (or
# `aw-spec`). Legacy eager-open: `set -g @aw_auto_spec on`.
if [[ -n "${TMUX:-}" ]]; then
  auto="$(tmux show-option -gqv '@aw_auto_spec' 2>/dev/null || true)"
  if [[ "$auto" == "on" ]]; then
    "$HERE/aw-spec" || true
  fi
fi

# ── Linear V2: search + propose Decision block ─────────────
# When the worktree isn't yet linked and consent != skip, run a fuzzy
# search using branch + last commit subject and append a `### D-bind:`
# block to spec.md > Decisions so the agent / user can pick on the next
# turn (non-blocking — agent proceeds without binding until user [x]'s).
if [[ ! -f "$aw/.linear-issue" ]]; then
  consent="$(tmux show-option -gqv '@aw_linear_consent' 2>/dev/null || true)"
  consent="${consent:-ask}"
  has_token=0
  [[ -n "${LINEAR_API_KEY:-}" ]] && has_token=1
  [[ "$has_token" -eq 0 && -f "$HOME/.claude/credentials/linear-api-key" ]] && has_token=1

  if [[ "$consent" != "skip" && "$has_token" -eq 1 ]]; then
    last_subject="$(git -C "$root" log -1 --pretty=%s 2>/dev/null || true)"
    query="${branch:-} ${last_subject:-}"
    query="${query# }"
    candidates=""
    if [[ -n "$query" ]]; then
      candidates="$("$HERE/aw-link" --search "$query" 2>/dev/null || true)"
    fi
    AW_SCRIPTS="$HERE" AW_SPEC="$spec" AW_CANDIDATES="$candidates" python3 - <<'PY'
import os, sys
sys.path.insert(0, os.environ["AW_SCRIPTS"])
from todos_sync import get_section, set_section

spec_path = os.environ["AW_SPEC"]
raw = os.environ.get("AW_CANDIDATES", "").strip()
lines = [l for l in raw.splitlines() if l.strip() and not l.startswith("(no matches)")]

with open(spec_path, "r", encoding="utf-8") as f:
    text = f.read()
if "D-bind" in get_section(text, "Decisions"):
    sys.exit(0)  # already proposed once; don't re-add on later sessions

candidates = []
for ln in lines:
    parts = ln.split(None, 2)
    if len(parts) < 3:
        continue
    candidates.append({"id": parts[0], "state": parts[1], "title": parts[2]})

block: list[str] = ["### D-bind: Bind this task to a Linear issue?"]
if candidates:
    rec = f"top match `{candidates[0]['id']}`"
else:
    rec = "Create new from this spec.md"
block += [f"**Status**: pending · **Recommended**: {rec}", ""]

for i, c in enumerate(candidates):
    mark = "x" if i == 0 else " "
    block.append(
        f"- [{mark}] `{c['id']}` — {c['title']} ({c['state']})  "
        f"← run `aw-link --bind {c['id']}`"
    )
if candidates:
    block.append("- [ ] Create new instead  ← run `aw-link`")
else:
    block.append("- [x] Create new (no related issues found)  ← run `aw-link`")
block.append("- [ ] Skip Linear for this task")

new_block = "\n".join(block)
existing = get_section(text, "Decisions").strip()
new_dec = (existing + "\n\n" + new_block) if existing else new_block
new_text = set_section(text, "Decisions", new_dec)
with open(spec_path, "w", encoding="utf-8") as f:
    f.write(new_text)
PY
  fi
fi
