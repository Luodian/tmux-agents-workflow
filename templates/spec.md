# Workspace spec
<!-- last-author: claude -->

## Contexts

<!--
Agent observations, discovered constraints, premises that should survive
across turns. Free-form bullets. Add as you learn things.

Examples:
  - Repo uses uv (uv.lock present), not pip.
  - Test runner is pytest, configured in pyproject.toml.
  - HEAD branch policy: amilabs is private working trunk.
-->

## Decisions

<!--
For each cross-turn decision the agent surfaces, append a `### Dn: <title>`
block with checkbox options. The [x]-marked option is the active choice
(defaults to **Recommended** until the user edits). Status: pending |
resolved.

Format:
  ### D1: Pick a database
  **Status**: pending · **Recommended**: Postgres
  - [x] Postgres — best fit for relational + jsonb
  - [ ] SQLite — single-file, but losing concurrency story
  - [ ] DynamoDB — overkill for this size
-->

## To-dos

<!--
Bidirectionally synced with the agent's TodoWrite (Claude) / update_plan
(Codex). Markdown checkbox grammar:
  - [ ] pending
  - [~] in_progress
  - [x] completed
-->
