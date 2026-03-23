# Contributing Guide

Thanks for helping improve **proxmox_srvbackup**. The sections below cover the day-to-day workflow, repository automation, and the checks that must pass before a change is merged.

## 1. Workflow Overview

1. Fork and branch -- use short, imperative branch names (`feature/backup-retention`, `fix/ssh-timeout`).
2. Make focused commits -- keep unrelated refactors out of the same change.
3. Run `make test` locally before pushing.
4. Update documentation and changelog entries affected by the change.
5. Open a pull request referencing any relevant issues.

## 2. Commits & Pushes

- Commit messages should be imperative (`Add ZFS backup retry`, `Fix SSH key permissions`).
- The test harness (`make test`) runs the full lint/type/test pipeline but leaves the repository untouched; create commits yourself before pushing.
- `make push` runs tests, commits, and pushes in one step. It accepts trailing arguments as the commit message.

## 3. Coding Standards

- Apply the repository's Clean Architecture / SOLID rules (see `CLAUDE.md` and the system prompts listed there).
- Prefer small, single-purpose modules and functions; avoid mixing orthogonal concerns.
- Free functions and modules use `snake_case`; classes are `PascalCase`.
- Keep runtime dependencies minimal. Use the standard library where practical.

## 4. Tests & Tooling

- `make test` runs Ruff (lint + format check), Pyright, and Pytest with coverage.
- `make testintegration` runs integration tests that require external resources (SMTP servers, SSH connectivity).
- Tests follow a narrative style: prefer names like `test_when_<condition>_<outcome>()`, keep each case laser-focused, and mark OS constraints with the provided markers (`@pytest.mark.os_agnostic`, `@pytest.mark.os_windows`, etc.).
- Mark tests requiring external resources with `@pytest.mark.local_only` so they are excluded from CI runs.
- Whenever you add a CLI behaviour or change backup logic, update the relevant tests so the specification remains complete.

## 5. Documentation Checklist

Before opening a PR, confirm the following:

- [ ] `make test` passes locally.
- [ ] Relevant documentation (`README.md`, `CONFIG.md`, `DEVELOPMENT.md`, `docs/systemdesign/*`) is updated.
- [ ] No generated artefacts or virtual environments are committed.
- [ ] Version bumps, when required, touch **only** `pyproject.toml`, `__init__conf__.py`, and `CHANGELOG.md`.

## 6. Security & Configuration

- Never commit secrets. Tokens (Codecov, PyPI), SSH keys, and passwords belong in `.env` (ignored by git) or CI secrets.
- SSH key paths and bootstrap keys should use configuration, not hardcoded paths.
- Sanitise any payloads you emit via logging.

Happy hacking!
