# Contributing to Aethelburg

Thank you for helping. Aethelburg is a small project in beta: issues and focused pull requests are the easiest to review.

## Reporting a problem

Open an issue with the **Bug report** form. Include the version (top bar of the app, or `pyproject.toml`), the operating system, the steps that lead to the problem and the error id shown by the app (the full error is in `logs/aethelburg.log` inside the data folder). Never paste API keys, and remove personal data from logs and screenshots.

Security problems go through [private vulnerability reporting](SECURITY.md), not public issues.

## Proposing a change

1. Open an issue first for anything larger than a small fix, so the approach can be agreed.
2. Set up the environment (Python 3.13):

   ```powershell
   py -3.13 -m venv .venv
   .venv\Scripts\python.exe -m pip install -e . pytest pytest-asyncio ruff
   ```

3. Run the checks before opening the pull request. Tests must run on a **copy** of a database, never on your working data:

   ```powershell
   $env:SQLITE_PATH = "$env:TEMP\aethelburg-test.sqlite"
   .venv\Scripts\python.exe -m pytest -q
   .venv\Scripts\python.exe -m ruff check src tests config migrations
   ```

4. Keep one change per pull request, add a test for new behaviour, and add a line to the `[Unreleased]` section of [CHANGELOG.md](CHANGELOG.md).
5. Write code, comments, documentation and commit messages in English.

## Data

Do not commit data files, databases, exports or downloaded documents: they stay in the local data folder. Third-party data keeps its own licence (see [NOTICE](NOTICE) and [docs/LEGAL.md](docs/LEGAL.md)).

## Conduct

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
