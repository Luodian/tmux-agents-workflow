# Self-review checklist

Before opening a PR:
- [ ] Tests pass locally (or noted why skipped)
- [ ] No commented-out code blocks
- [ ] No `print()` / `console.log` debug left in
- [ ] No secret literals or credentials in diff
- [ ] Surface area unchanged unless intended (no incidental refactors)
- [ ] Public interfaces are backwards-compatible OR breakage documented
- [ ] Net-positive: this diff moves at least one of {features, usability, bugs↓, readability↑}
