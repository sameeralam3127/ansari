# Contributing to ANSARI

Thanks for your interest in ANSARI! This project started as a **learning and
educational exploration** of platform-engineering patterns (golden-path
scaffolding, drift detection, fleet-wide sync). It's free to use, free to
fork, and contributions of any size are welcome — from fixing a typo to
proposing a new template type.

By participating in this project you agree to abide by the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Before you start

- For anything more than a trivial fix, please open an issue first to discuss
  the change. This avoids duplicated effort and lets maintainers weigh in on
  design before you invest time in an implementation.
- Search existing [issues](../../issues) and [pull requests](../../pulls) to
  avoid duplicates.
- Security issues should **never** be reported as public issues — see
  [SECURITY.md](SECURITY.md) instead.

## Development setup

ANSARI uses [`uv`](https://docs.astral.sh/uv/) for dependency management.

```bash
git clone https://github.com/sameeralam3127/ansari.git
cd ansari
make setup      # uv sync --extra dev + install pre-commit hooks
```

Common tasks:

```bash
make lint        # ruff check
make format      # ruff format
make typecheck   # mypy --strict
make test        # pytest with coverage
make check       # lint + typecheck + test
make up          # docker compose up --build (local Postgres + API)
make migrate     # alembic upgrade head
```

Pre-commit hooks (ruff lint/format, trailing whitespace, large-file checks,
merge-conflict markers) run automatically once you've run `make setup`. CI
runs the same checks plus a `docker build` and a Trivy vulnerability scan on
the built image, so please run `make check` locally before pushing.

## Making a change

1. Fork the repository and create a branch off `main`:
   `git checkout -b feat/short-description`.
2. Make your change, with tests for any new behavior and updated
   documentation where relevant.
3. If you changed a SQLAlchemy model, generate an Alembic migration
   (`uv run alembic revision --autogenerate -m "..."`) — CI fails the build
   if models and migrations have diverged.
4. Run `make check` and confirm everything passes.
5. Commit using clear, descriptive messages (conventional commit prefixes
   like `feat:`, `fix:`, `docs:`, `chore:` are appreciated but not required).
6. Push your branch and open a pull request against `main` using the
   [pull request template](PULL_REQUEST_TEMPLATE.md).

## Pull request expectations

- Keep PRs focused — one logical change per PR is easier to review and
  revert if needed.
- Link the issue the PR addresses, if any.
- Make sure CI (lint, type check, tests, migration check, image build/scan)
  is green.
- A maintainer will review your PR. Please be patient and responsive to
  review feedback — this is a small, community-driven project.
- All commits to `main` land through pull requests; direct pushes to `main`
  are disabled by branch protection (see below).

## Branch protection & repository hygiene

To keep `main` releasable at all times, this repository enforces (or is
recommended to enforce, once configured by a repository admin under
**Settings → Branches**):

- No direct pushes to `main` — all changes go through a pull request.
- At least one approving review required before merging.
- Status checks (`lint-type-test`, `build-and-scan`) must pass before
  merging.
- Branches must be up to date with `main` before merging.
- Force-pushes and branch deletion are blocked on `main`.
- Conversation resolution required before merging.

See [`.github/settings.yml`](settings.yml) for the rules as configured
if the [Settings app](https://github.com/apps/settings) is installed, and
[`SECURITY.md`](SECURITY.md) for the project's broader security posture.

## Reporting bugs and requesting features

Please use the [issue templates](ISSUE_TEMPLATE) — they help us get the
information we need to act on your report quickly.

## A note on scope

ANSARI is shared **for learning and educational purposes and is free for
anyone to use, study, modify, and build on** (see [LICENSE](../LICENSE)).
It is not an officially supported commercial product, so response times are
best-effort. That said, thoughtful contributions and issue reports are
genuinely appreciated and help make it a better reference for everyone.
