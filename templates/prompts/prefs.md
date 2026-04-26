# General preferences for this repo

## Style
- Surgical edits — every changed line traces to the request; no adjacent cleanup.
- No emoji in code, commits, or PRs (unless the user explicitly asks).
- Prefer fixing root causes over patching symptoms.
- Net-positive lens — every diff must move at least one of {functionality, usability, bug count down, readability up}. Code-volume up alone is a regression; collapse / extract / prune in the same diff to stay net-positive.

## Don't
- Don't bump versions unless asked.
- Don't add new dependencies without flagging in the PR description.
- Don't touch `AGENTS.md` / `CLAUDE.md` without explicit permission.

## Do
- Write English in all public artifacts (commits, PRs, comments) even when chat is 中文.
- Run tests / linters before claiming done.
- Quote file paths with line numbers when reporting.
