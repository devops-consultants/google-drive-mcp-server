# Task Completion Checklist

When a task is completed, run through these steps:

1. **Run tests**: `pytest tests/ -v` — all 68 tests must pass
2. **Check for unused imports**: Review changed files for any unused imports
3. **Verify no regressions**: Ensure existing functionality isn't broken
4. **Update docs if needed**:
   - `README.md` — user-facing documentation
   - `CLAUDE.md` — Claude Code guidance
   - `CONTRIBUTING.md` — developer setup instructions
5. **Commit with descriptive message**: Include what changed and why
6. **Push to branch**: `git push origin <branch-name>`

## No linter/formatter configured
There is no automated linter or formatter in the project currently. Manual review for style consistency.

## CI Pipeline
CI runs on push to main, v* tags, and PRs:
- Test job: `pip install -e ".[dev]"` → `pytest tests/ -v`
- Build job: Builds Docker image, pushes to ghcr.io on main/tags (not PRs)
