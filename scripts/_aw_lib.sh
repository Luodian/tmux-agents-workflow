# _aw_lib.sh — shared resolution helpers for tmux-agents-workflow.
# Sourced, not executed. Source AFTER setting `HERE` if you need it; this
# file uses the path of the *sourced* script (BASH_SOURCE[0]) to find its
# siblings.
#
# Public functions:
#   aw_repo_root              echo git toplevel; nonzero if not in a repo
#   aw_active_spec_name <root>  echo the chosen spec filename (no path)
#   aw_resolve_spec <root>      echo the absolute spec path (creates dir; not the file)
#   aw_list_specs <root>        echo every `*_spec.md` + `spec.md` in .agentwf/
#
# Resolution order (must stay in lockstep with todos_sync.resolve_spec_path):
#   1. AW_SPEC env var (absolute or root-relative). Used to pin a spec for
#      a single command without touching state.
#   2. $root/.agentwf/active-spec exists, non-empty → name on first non-blank
#      line (whitespace stripped).
#   3. $root/.agentwf/spec.md exists (regular file or symlink) → use it.
#      Covers the legacy single-spec layout and the symlink-to-named-file
#      workaround.
#   4. Exactly one $root/.agentwf/*_spec.md hit → use it. Means a worktree
#      with a single named spec works without any extra wiring.
#   5. Otherwise default to spec.md (callers will create from template).

aw_repo_root() {
  git rev-parse --show-toplevel 2>/dev/null
}

# Trim whitespace and reject anything with a `/` to avoid escapes.
_aw_sanitize_name() {
  local name="$1"
  name="${name#"${name%%[![:space:]]*}"}"
  name="${name%"${name##*[![:space:]]}"}"
  case "$name" in
    */*|"") return 1 ;;
  esac
  printf '%s' "$name"
}

aw_list_specs() {
  local root="$1"
  local aw="$root/.agentwf"
  [[ -d "$aw" ]] || return 0
  # Print spec.md first if present, then each *_spec.md once. Skip duplicates
  # (e.g. when spec.md is a symlink whose target also matches the glob).
  local seen=""
  if [[ -e "$aw/spec.md" ]]; then
    printf '%s\n' "spec.md"
    seen=$'\nspec.md\n'
  fi
  local f base
  shopt -s nullglob
  for f in "$aw"/*_spec.md; do
    base="${f##*/}"
    case "$seen" in
      *$'\n'"$base"$'\n'*) continue ;;
    esac
    seen+="$base"$'\n'
    printf '%s\n' "$base"
  done
  shopt -u nullglob
}

aw_active_spec_name() {
  local root="$1"
  local aw="$root/.agentwf"

  # 1. AW_SPEC env var pin (absolute → basename; relative → as-given).
  if [[ -n "${AW_SPEC:-}" ]]; then
    local pinned="${AW_SPEC##*/}"
    pinned="$(_aw_sanitize_name "$pinned")" || true
    if [[ -n "$pinned" ]]; then
      printf '%s\n' "$pinned"
      return 0
    fi
  fi

  # 2. .agentwf/active-spec pointer.
  local pointer="$aw/active-spec"
  if [[ -s "$pointer" ]]; then
    local name
    name="$(grep -m1 -v '^[[:space:]]*$' "$pointer" 2>/dev/null || true)"
    name="$(_aw_sanitize_name "$name")" || name=""
    if [[ -n "$name" && -e "$aw/$name" ]]; then
      printf '%s\n' "$name"
      return 0
    fi
  fi

  # 3. spec.md (regular file or symlink) wins legacy and symlink workflows.
  if [[ -e "$aw/spec.md" ]]; then
    printf 'spec.md\n'
    return 0
  fi

  # 4. Single named spec.
  shopt -s nullglob
  local hits=("$aw"/*_spec.md)
  shopt -u nullglob
  if [[ "${#hits[@]}" -eq 1 ]]; then
    printf '%s\n' "${hits[0]##*/}"
    return 0
  fi

  # 5. Default. Caller (e.g. aw-spec / hook-session-start) will create.
  printf 'spec.md\n'
}

aw_resolve_spec() {
  local root="$1"
  local aw="$root/.agentwf"
  mkdir -p "$aw"
  local name
  name="$(aw_active_spec_name "$root")"
  printf '%s/%s\n' "$aw" "$name"
}
