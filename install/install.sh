#!/usr/bin/env bash
# Print a ready-to-paste settings.json hook block with the plugin path
# resolved. The user is expected to merge this into ~/.claude/settings.json
# by hand — we do NOT modify their settings file in place, because most
# users already have hook entries there (peon-ping, preflight, etc.) and
# blind merging would either duplicate or destroy them.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$HERE")"

cat >&2 <<EOF
# tmux-agents-workflow — paste the JSON below into ~/.claude/settings.json.
#
# Merge under .hooks — append entries to the existing event arrays. Do NOT
# replace your settings file: most users have other hooks (peon-ping,
# preflight, worktree-gatekeeper, etc.) that would be clobbered.
#
# Plugin path resolved to: $PLUGIN_DIR
# ----------------------------------------------------------------------
EOF

sed "s#{{PLUGIN_DIR}}#${PLUGIN_DIR}#g" "$HERE/settings.json.patch"
