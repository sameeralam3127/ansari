# Security Policy

## Project status

ANSARI is a **learning and educational project** — a reference implementation
of platform-engineering patterns (golden-path scaffolding, drift detection,
fleet-wide sync). It is **free for anyone to use, study, fork, and build on**
under the [MIT License](../LICENSE). It is not a commercially supported
product, and there is no SLA on fixes — but security reports are taken
seriously and handled promptly on a best-effort basis, because a project used
for learning should still be safe to run and safe to learn from.

## Supported versions

ANSARI is currently pre-1.0 and developed on a single rolling `main` branch.
Security fixes are made against the latest commit on `main`; there are no
long-term-supported release branches at this time.

| Version        | Supported          |
| -------------- | ------------------ |
| `main` (latest)| :white_check_mark: |
| tagged releases < 1.0 | :x: (upgrade to latest `main`) |

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**
Publicly disclosing a vulnerability before a fix is available puts every user
of the project at risk.

Instead, report it privately using one of the following channels, in order
of preference:

1. **GitHub Security Advisories** (preferred): open a
   [private security advisory](../../security/advisories/new) for this
   repository. This notifies maintainers directly and keeps the discussion
   confidential until a fix is ready.
2. **Email**: if you cannot use GitHub Security Advisories, contact the
   maintainer directly at the email address on the
   [GitHub profile of the repository owner](https://github.com/sameeralam3127).

When reporting, please include as much of the following as you can:

- A description of the vulnerability and its potential impact.
- Steps to reproduce, or a proof-of-concept.
- The affected file(s)/commit/version.
- Any suggested mitigation, if you have one.

### What to expect

- **Acknowledgement**: best-effort within 3 business days.
- **Triage**: we'll confirm the issue, assess severity, and let you know
  next steps.
- **Fix & disclosure**: once a fix is available, we'll credit reporters (if
  they wish) in the release notes / advisory, and coordinate a disclosure
  timeline with you. We ask that you give us a reasonable window to ship a
  fix before any public disclosure.

## Scope

This policy covers the ANSARI codebase in this repository: the CLI/API
(`src/ansari`), database migrations (`alembic/`), the Dockerfile, and CI/CD
workflows (`.github/workflows`). Vulnerabilities in third-party dependencies
should generally be reported upstream, but please let us know too so we can
track and update pinned versions.

## Security practices in this repository

To keep the project reasonably secure by default:

- **Dependency scanning**: dependency versions are pinned via `uv.lock`;
  update dependencies regularly and review `dependabot`/security alerts.
- **Container scanning**: every CI run builds the Docker image and scans it
  with [Trivy](https://github.com/aquasecurity/trivy-action), failing the
  build on CRITICAL/HIGH findings.
- **Static analysis**: `ruff` (lint) and `mypy --strict` (type checking) run
  on every push and pull request.
- **No secrets in source control**: configuration is provided via
  environment variables (see `.env.example`); never commit real credentials,
  API keys, or database URLs. Report any accidental secret leak immediately
  via the private channels above so it can be rotated.
- **Branch protection**: `main` requires passing CI and at least one review
  before merge — see [CONTRIBUTING.md](CONTRIBUTING.md#branch-protection--repository-hygiene).
- **Least privilege**: the container image and any runtime deployment
  examples should run as a non-root user and expose only the ports they need.

## Disclaimer

ANSARI is provided "as is", for learning and educational purposes, without
warranty of any kind, as described in the [MIT License](../LICENSE). If you
deploy it beyond a learning/experimentation context, review the code and
apply the hardening appropriate for your own environment.
