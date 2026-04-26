.PHONY: lint test

lint:
	bash -n tmux-agents-workflow.tmux
	bash -n scripts/hook-session-start.sh
	bash -n scripts/hook-stop-diff.sh
	bash -n scripts/aw-pr
	bash -n scripts/aw-init
	bash -n scripts/aw-setup
	bash -n scripts/aw-archive
	bash -n scripts/aw-run
	bash -n scripts/_aw_env.sh
	bash -n scripts/status-todo-count.sh
	bash -n install/install.sh
	python3 -m py_compile \
	  scripts/todos_sync.py \
	  scripts/hook_post_todos.py \
	  scripts/hook_prompt_submit.py \
	  scripts/hook_pre_bash.py
	python3 -c 'import json; json.load(open("install/claude-settings.json.patch"))'
	python3 -c 'import json; json.load(open("install/codex-hooks.json.patch"))'

test: lint
	python3 scripts/todos_sync.py --selftest
