.PHONY: lint test

lint:
	bash -n tmux-agents-workflow.tmux
	bash -n scripts/hook-session-start.sh
	bash -n scripts/hook-stop-diff.sh
	bash -n scripts/aw-pr
	python3 -m py_compile scripts/todos_sync.py scripts/hook_post_todo_write.py scripts/hook_prompt_submit.py

test: lint
	python3 scripts/todos_sync.py --selftest
