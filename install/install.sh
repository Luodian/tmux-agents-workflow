#!/usr/bin/env bash
# Print ready-to-paste hook patches for both Claude Code and Codex CLI,
# with the plugin path resolved. We deliberately do NOT modify the user's
# settings files — most users have other hooks (peon-ping, preflight,
# memory-curator, etc.) that blind-merging would clobber.
#
# Usage:
#   install.sh                # print both patches with section headers
#   install.sh --claude       # print only the Claude Code patch
#   install.sh --codex        # print only the Codex CLI patch

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$HERE")"

mode="both"
case "${1:-}" in
  --claude) mode="claude" ;;
  --codex)  mode="codex" ;;
  --both|"") mode="both" ;;
  -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
  *) echo "unknown arg: $1" >&2; exit 2 ;;
esac

emit_section() {
  local label="$1" target_path="$2" patch_file="$3"
  cat >&2 <<EOF
# ──────────────────────────────────────────────────────────────────
# $label
# Target file: $target_path
# Merge hint:  append each event's hook entries to the existing
#              .hooks.<EventName>[].hooks array; do NOT replace.
# Plugin dir:  $PLUGIN_DIR
# ──────────────────────────────────────────────────────────────────
EOF
  sed "s#{{PLUGIN_DIR}}#${PLUGIN_DIR}#g" "$HERE/$patch_file"
}

if [[ "$mode" == "claude" || "$mode" == "both" ]]; then
  emit_section "Claude Code patch" "~/.claude/settings.json" "claude-settings.json.patch"
fi

if [[ "$mode" == "both" ]]; then
  echo
  echo "═══════════════════════════════════════════════════════════════"
  echo
fi

if [[ "$mode" == "codex" || "$mode" == "both" ]]; then
  emit_section "Codex CLI patch" "~/.codex/hooks.json" "codex-hooks.json.patch"
fi
