## What and why

<!-- One change per pull request. Link the issue it closes: "Closes #123". -->

## Checks

- [ ] `pytest -q` passes, run with `SQLITE_PATH` pointing to a copy of a database
- [ ] `ruff check src tests config migrations` passes
- [ ] New behaviour has a test
- [ ] A line in the `[Unreleased]` section of `CHANGELOG.md`
- [ ] User-visible changes are described in `docs/guide/`
- [ ] No API keys, personal data or data files in the diff
