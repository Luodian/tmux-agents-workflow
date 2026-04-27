#!/usr/bin/env bash
# TPM entry point for tmux-agents-workflow.
#
# Sibling to tmux-autoname-agent-sessions and tmux-coding-agents. Adds:
#   - Conductor-style per-worktree spec file (.agentwf/<name>_spec.md),
#     bidirectionally synced with Claude Code's TodoWrite and Codex's
#     update_plan via hooks. Multi-spec aware: a worktree may carry several
#     specs, with the active one tracked in .agentwf/active-spec.
#   - lifecycle scripts (.agentwf/{setup,archive,run}.sh) executed via aw-* CLIs
#     bound to tmux keys (prefix + S / A / R / r).
#   - repo-specific prompts (.agentwf/prompts/*.md) with just-in-time injection
#     into PreToolUse(Bash) for `gh pr create`, `git commit`, etc.
#   - a soft merge gate (aw-pr) that refuses to ship with unchecked todos.
#
# Hook scripts under scripts/ are wired into Claude Code via
# install/install.sh — this .tmux file only registers tmux-side keybindings
# and the optional status-line widget.

CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

tmux_opt() {
  local value
  value="$(tmux show-option -gqv "$1" 2>/dev/null)"
  printf '%s\n' "${value:-$2}"
}

normalize_key() {
  case "$1" in
    ''|off|none|disabled|disable) printf '\n' ;;
    *) printf '%s\n' "$1" ;;
  esac
}

# Resolve worktree root from the focused pane's cwd. Evaluated by run-shell
# inside each binding, which inherits the pane's working directory.
git_root_expr='$(git -C "$(tmux display -p "#{pane_current_path}")" rev-parse --show-toplevel 2>/dev/null)'

# ── prefix + t : open the active .agentwf/<spec> in nvim split pane (right) ──
# Idempotent: if a spec pane is already alive, re-select it.
spec_key="$(normalize_key "$(tmux_opt '@aw_bind_spec' 't')")"
if [[ -n "$spec_key" ]]; then
  tmux bind-key "$spec_key" run-shell \
    "root=$git_root_expr; cd \"\$root\" && $CURRENT_DIR/scripts/aw-spec"
fi

# ── prefix + T : interactive spec switcher (fzf if available) ──
# Only registered when fzf is on PATH; otherwise the keybind is left untouched
# so other plugins / user bindings keep working. Override or disable with
# `set -g @aw_bind_spec_switch off`.
spec_switch_key="$(normalize_key "$(tmux_opt '@aw_bind_spec_switch' 'T')")"
if [[ -n "$spec_switch_key" ]] && command -v fzf >/dev/null 2>&1; then
  tmux bind-key "$spec_switch_key" display-popup -E -w 60% -h 40% \
    "root=$git_root_expr; cd \"\$root\" && $CURRENT_DIR/scripts/aw-spec switch"
fi

# ── prefix + e : popup-edit fallback (raw editor on the active spec) ────────
edit_key="$(normalize_key "$(tmux_opt '@aw_bind_edit' 'e')")"
if [[ -n "$edit_key" ]]; then
  tmux bind-key "$edit_key" display-popup -E -w 80% -h 80% \
    "root=$git_root_expr; spec=\$($CURRENT_DIR/scripts/aw-spec --print-active 2>/dev/null); spec=\"\${spec:-\$root/.agentwf/spec.md}\"; mkdir -p \"\$(dirname \"\$spec\")\"; \${EDITOR:-vi} \"\$spec\""
fi

# ── prefix + D : git diff popup (on-demand fallback) ────────
diff_key="$(normalize_key "$(tmux_opt '@aw_bind_diff' 'D')")"
if [[ -n "$diff_key" ]]; then
  tmux bind-key "$diff_key" display-popup -E -w 90% -h 90% \
    "root=$git_root_expr; cd \"\$root\" && (git -c color.ui=always diff --stat HEAD; echo; git -c color.ui=always diff HEAD) | less -R"
fi

# ── prefix + S : run aw-setup in popup ──────────────────────
setup_key="$(normalize_key "$(tmux_opt '@aw_bind_setup' 'S')")"
if [[ -n "$setup_key" ]]; then
  tmux bind-key "$setup_key" display-popup -E -w 90% -h 80% \
    "root=$git_root_expr; cd \"\$root\" && $CURRENT_DIR/scripts/aw-setup; echo; echo 'Press q to close'; read -n 1"
fi

# ── prefix + A : run aw-archive in popup ────────────────────
archive_key="$(normalize_key "$(tmux_opt '@aw_bind_archive' 'A')")"
if [[ -n "$archive_key" ]]; then
  tmux bind-key "$archive_key" display-popup -E -w 80% -h 60% \
    "root=$git_root_expr; cd \"\$root\" && $CURRENT_DIR/scripts/aw-archive; echo; echo 'Press q to close'; read -n 1"
fi

# ── prefix + R : aw-run (start dev process in new window) ───
run_key="$(normalize_key "$(tmux_opt '@aw_bind_run' 'R')")"
if [[ -n "$run_key" ]]; then
  tmux bind-key "$run_key" run-shell \
    "root=$git_root_expr; cd \"\$root\" && $CURRENT_DIR/scripts/aw-run"
fi

# ── prefix + r : aw-run --kill (stop the dev process) ───────
kill_key="$(normalize_key "$(tmux_opt '@aw_bind_kill' 'M-r')")"
if [[ -n "$kill_key" ]]; then
  tmux bind-key "$kill_key" run-shell \
    "root=$git_root_expr; cd \"\$root\" && $CURRENT_DIR/scripts/aw-run --kill"
fi

# ── prefix + L : aw-link (auto: create if unlinked, update if linked) ──
link_key="$(normalize_key "$(tmux_opt '@aw_bind_link' 'L')")"
if [[ -n "$link_key" ]]; then
  tmux bind-key "$link_key" display-popup -E -w 90% -h 70% \
    "root=$git_root_expr; cd \"\$root\" && if [[ -f .agentwf/.linear-issue ]]; then $CURRENT_DIR/scripts/aw-link --update; else $CURRENT_DIR/scripts/aw-link; fi; echo; echo 'Press q to close'; read -n 1"
fi

# ── prefix + I : aw-init (bootstrap .agentwf/ in popup) ─────
init_key="$(normalize_key "$(tmux_opt '@aw_bind_init' 'I')")"
if [[ -n "$init_key" ]]; then
  tmux bind-key "$init_key" display-popup -E -w 80% -h 70% \
    "root=$git_root_expr; cd \"\$root\" && $CURRENT_DIR/scripts/aw-init; echo; echo 'Press q to close'; read -n 1"
fi

# ── status-line widget (optional, user wires manually) ──────
chmod +x "$CURRENT_DIR/scripts/status-todo-count.sh" 2>/dev/null || true
