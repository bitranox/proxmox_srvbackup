# Development

## Make Targets

All targets delegate to `uvx bmk@latest`. Trailing arguments are forwarded automatically.

| Target                     | Aliases           | Description                                                |
|----------------------------|-------------------|------------------------------------------------------------|
| `test`                     | `t`               | Lint, format, type-check, run tests with coverage          |
| `testintegration`          | `testi`, `ti`     | Run integration tests only (SMTP, SSH, external resources) |
| `codecov`                  | `coverage`, `cov` | Upload coverage report to Codecov                          |
| `build`                    | `bld`             | Build wheel/sdist artifacts                                |
| `clean`                    | `cln`, `cl`       | Remove caches, coverage, and build artifacts               |
| `run`                      |                   | Run the project CLI via uvx                                |
| `bump-major`               |                   | Increment major version ((X+1).0.0)                        |
| `bump-minor`               |                   | Increment minor version (X.Y.Z -> X.(Y+1).0)               |
| `bump-patch`               |                   | Increment patch version (X.Y.Z -> X.Y.(Z+1))               |
| `bump`                     |                   | Bump patch version (default)                               |
| `commit`                   | `c`               | Create a git commit with timestamped message               |
| `push`                     | `psh`, `p`        | Run tests, commit, and push to remote                      |
| `release`                  | `rel`, `r`        | Tag vX.Y.Z, push, create GitHub release                    |
| `dependencies`             | `deps`, `d`       | Check and list project dependencies                        |
| `dependencies-update`      |                   | Update dependencies to latest versions                     |
| `config`                   |                   | Show current merged configuration                          |
| `config-deploy`            |                   | Deploy configuration to system/user directories            |
| `config-generate-examples` |                   | Generate example configuration files                       |
| `send-email`               |                   | Send an email via configured SMTP                          |
| `send-notification`        |                   | Send a plain-text notification email                       |
| `custom`                   |                   | Run a custom bmk command (`make custom <name> [args...]`)  |
| `info`                     |                   | Print resolved package metadata                            |
| `hello`                    |                   | Emit the canonical greeting                                |
| `logdemo`                  |                   | Run logging demonstration                                  |
| `version-current`          |                   | Print current version                                      |
| `dev`                      |                   | Editable install (`uv pip install -e .`)                   |
| `install`                  |                   | Editable install (no dev extras)                           |
| `help`                     |                   | Show make targets                                          |

### Target Details

- `test`: single entry point for local CI -- runs ruff lint + format check, pyright, pytest (including doctests) with coverage (enabled by default).
- `testintegration`: runs only tests marked `@pytest.mark.local_only` (SMTP, SSH connectivity, external resources).
- `build`: creates wheel/sdist artifacts.
- `version-current`: prints current version from `pyproject.toml`.
- `bump`: updates `pyproject.toml` version, `__init__conf__.py`, and `CHANGELOG.md`.

## Running Integration Tests

Some tests require external resources (SMTP servers, SSH connectivity) and are excluded from the default test run. These are marked with `@pytest.mark.local_only`.

### Quick Reference

| Command                | What it runs                                   |
|------------------------|------------------------------------------------|
| `make test`            | All tests EXCEPT `local_only` (default for CI) |
| `make testintegration` | ONLY `local_only` integration tests            |
| `pytest tests/`        | ALL tests (no marker filter)                   |

### Email Integration Tests

To run email tests that actually send messages:

1. **Create a `.env` file** in the project root with your SMTP settings:

```bash
# .env (copy from .env.example)
EMAIL__SMTP_HOSTS=smtp.example.com:587
EMAIL__FROM_ADDRESS=sender@example.com
EMAIL__RECIPIENTS=recipient@example.com
EMAIL__SMTP_USERNAME=your_username
EMAIL__SMTP_PASSWORD=your_password
```

   Alternatively, use `--env-file` to point at an existing `.env` file:

```bash
proxmox-srvbackup --env-file /path/to/my/.env send-notification --subject "Test" --message "Hello"
```

2. **Run the integration tests**:

```bash
make testintegration
```

3. **Or run specific email tests**:

```bash
pytest tests/test_cli_email_smtp.py -v
```

### Adding New Integration Tests

Mark tests that require external resources:

```python
@pytest.mark.local_only
@pytest.mark.os_agnostic
def test_real_external_service(...):
    """Integration test requiring external service."""
    ...
```

These tests will be skipped in CI but run with `make testintegration`.

## Development Workflow

```bash
make test                 # ruff + pyright + pytest + coverage (default ON)
SKIP_BOOTSTRAP=1 make test  # skip auto-install of dev deps
COVERAGE=off make test       # disable coverage locally
COVERAGE=on make test        # force coverage and generate coverage.xml/codecov.xml
```

**Automation notes**

- `make push` runs the full test suite (`python -m scripts.test`), checks pip and dependency versions, prompts for a commit message (or reads `COMMIT_MESSAGE="..."`), and always pushes, creating an empty commit when there are no staged changes. The Textual menu (`make menu -> push`) shows the same behaviour via an input field.

### Versioning & Metadata

- Single source of truth for package metadata is `pyproject.toml` (`[project]`).
- The library reads its own metadata from static constants (see `src/proxmox_srvbackup/__init__conf__.py`).
- Do not duplicate the version in code; bump only `pyproject.toml` and update `CHANGELOG.md`.
- Console script name is discovered from entry points; defaults to `proxmox-srvbackup`.

### Dependency Auditing

- `make test` invokes `pip-audit` to check for known vulnerabilities. If pip-audit reports vulnerabilities, address them by pinning fixed versions in `[project.optional-dependencies.dev]`.

### CI & Publishing

GitHub Actions workflows are included:

- `.github/workflows/ci.yml` -- lint/type/test, build wheel/sdist, and verify pipx and uv installs (CI-only; no local install required).
- `.github/workflows/release.yml` -- on tags `v*.*.*`, builds artifacts and publishes to PyPI when `PYPI_API_TOKEN` secret is set.

To publish a release:
1. Bump `pyproject.toml` version and update `CHANGELOG.md`.
2. Tag the commit (`git tag v0.1.1 && git push --tags`).
3. Ensure `PYPI_API_TOKEN` secret is configured in the repo.
4. Release workflow uploads wheel/sdist to PyPI.

### Local Codecov uploads

- `make test` (with coverage enabled) generates `coverage.xml` and `codecov.xml`, then attempts to upload via the Codecov CLI or the bash uploader.
- For private repos, set `CODECOV_TOKEN` (see `.env.example`) or export it in your shell.
- For public repos, a token is typically not required.
- Because Codecov requires a revision, the test harness commits (allow-empty) immediately before uploading. Remove or amend that commit after the run if you do not intend to keep it.
