# _aw_env.sh — shared env setup for aw-setup / aw-archive / aw-run.
# Sourced, not executed. Resolves AW_ROOT and AW_WORKSPACE from git state.

aw_resolve_env() {
  AW_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  if [[ -z "$AW_ROOT" ]]; then
    echo "aw: not inside a git repo" >&2
    return 1
  fi
  # Worktree branch (or "(detached)" if HEAD is unattached).
  AW_WORKSPACE="$(git -C "$AW_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo detached)"
  export AW_ROOT AW_WORKSPACE
}

# Find a free TCP port via Python (portable, no `nc` dependency).
aw_alloc_port() {
  python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()' 2>/dev/null \
    || echo 0
}
