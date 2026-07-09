# A.N.S.A.R.I.

**Advanced Network SRE & Automated Remediation Interface**

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Linted with Ruff](https://img.shields.io/badge/lint-ruff-46a758.svg)](https://github.com/astral-sh/ruff)
[![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC.svg)](https://pytest.org)

> **Ansari** means "the helper." This project brings that idea into DevOps, SRE, and platform engineering by helping teams investigate infrastructure issues and move toward safe automated remediation from one readable CLI.

ANSARI is a Python command-line tool for engineers who want one friendly entry point to inspect networks, cloud resources, Kubernetes workloads, Terraform state, and CI/CD signals. The long-term goal is to turn scattered operational checks into consistent answers and remediation guidance that are easy to run locally, in GitHub Actions, or inside a platform engineering workflow.

---

## Table of Contents

- [What Issue ANSARI Solves](#what-issue-ansari-solves)
- [How It Helps DevOps, SRE, and Platform Teams](#how-it-helps-devops-sre-and-platform-teams)
- [Why It Is Easy to Use](#why-it-is-easy-to-use)
- [Current Features](#current-features)
  - [Adding Your Own Checker](#adding-your-own-checker)
- [Quick Start](#quick-start)
- [Naming Guide](#naming-guide)
- [Phase-Wise Development Roadmap](#phase-wise-development-roadmap)
- [Built With](#built-with)
- [License](#license)

---

## What Issue ANSARI Solves

During production support or daily platform operations, engineers often lose time switching between cloud consoles, Kubernetes commands, Terraform state, dashboards, alerts, and runbooks. That slows down triage and makes it harder to answer the basic question: **"What is wrong, and what should I check next?"**

ANSARI is designed to reduce that friction by collecting network, service, and resource signals and presenting them in a simple operational format:

- **What resource am I checking?**
- **Is it healthy, degraded, unhealthy, or unknown?**
- **What signals matter right now?**
- **What should I check or fix next?**
- **Can this be automated in CI, incident response, or platform workflows?**

**In simple words:** ANSARI helps an engineer move from **alert** → **understanding** → **next action** faster.

### Real-World Example

Imagine an on-call engineer receives an alert for `eks-cluster-01`. Without a helper, they may jump between Kubernetes commands, dashboards, cloud consoles, and runbooks before they know what to inspect first.

With ANSARI, the first check is intentionally simple:

```bash
ansari check eks-cluster-01
```

The CLI responds with a readable overview:

- The resource name and detected type
- A health status such as `healthy`, `degraded`, `unhealthy`, or `unknown`
- Important signals such as ready nodes, running pods, backup state, or drift state
- Next steps the engineer can take immediately

> **Note:** This does not replace full monitoring or cloud-native tooling. It gives teams a faster, clearer first step during triage, reliability reviews, and platform demos.

---

## How It Helps DevOps, SRE, and Platform Teams

- **Faster triage:** Start with `ansari check <resource>` instead of remembering multiple commands.
- **Consistent output:** Every check returns a status, summary, signals, and next steps.
- **Lower context switching:** Bring cloud, Kubernetes, Terraform, and CI/CD checks into one CLI flow.
- **Automation ready:** Run checks manually, from GitHub Actions, or as scheduled reliability audits.
- **Easy to extend:** Add new resource checkers without changing the user-facing command style.

---

## Why It Is Easy to Use

ANSARI is intentionally built around a small command set, and after
installing with `uv` (see [Quick Start](#quick-start)) it runs directly —
no `poetry run` or `uv run` prefix needed:

```bash
ansari examples
ansari check eks-cluster-01
ansari check payment-pod
ansari check prod-rds-db
```

### Output Format

The output is written for humans first. Each check result includes:

| Output Area       | What It Means                                        |
| :---------------- | :--------------------------------------------------- |
| **Resource Type** | What kind of infrastructure ANSARI recognized.       |
| **Status**        | `healthy`, `degraded`, `unhealthy`, or `unknown`.    |
| **Summary**       | One-line operational meaning of the check.           |
| **Signals**       | Facts gathered from the resource or integration.     |
| **Next Steps**    | Practical checks or fixes an engineer can take next. |

---

## Current Features

- **Readable CLI:** Built with `Typer` and `Rich` for clean terminal output.
- **Helpful Examples Command:** `ansari examples` shows copy-pasteable commands for common checks.
- **Reliability Check Model:** Normalized health states, resource types, signals, and recommendations.
- **SRE-Friendly Output:** Shows an overview, signals, and next steps instead of raw status only.
- **Friendly Help and Errors:** Running `ansari` shows command help, and invalid input gives a practical next command.
- **Pluggable Checkers:** Each resource type (Kubernetes, database, Terraform) is its own `Checker` class under `ansari/modules/checkers/`. Adding support for a new resource means writing one small class — no changes to the CLI or existing checkers.

> **Current limitation:** the bundled checkers return deterministic demo data today, not live infrastructure state — they exist to prove out the CLI contract and the checker interface. Wiring them to real Kubernetes/AWS/Terraform APIs is Phase 2+ (see the roadmap below).

### Adding Your Own Checker

Every checker implements a two-method interface:

```python
from ansari.models import ResourceHealth
from ansari.modules.checkers.base import Checker


class MyChecker(Checker):
    def matches(self, resource_name: str) -> bool:
        """Return True if this checker owns the given resource name."""

    def check(self, resource_name: str) -> ResourceHealth:
        """Run the check and return a normalized ResourceHealth."""
```

Hand it to `ReliabilityChecker` alongside (or instead of) the built-in checkers:

```python
from ansari.modules.checkers import DEFAULT_CHECKERS
from ansari.modules.reliability_checker import ReliabilityChecker

checker = ReliabilityChecker(checkers=(*DEFAULT_CHECKERS, MyChecker()))
```

See [`examples/custom_checker.py`](examples/custom_checker.py) for a complete, runnable example that adds an AWS Lambda checker:

```bash
uv run python examples/custom_checker.py payments-lambda-fn
```

### Best-Fit GitHub Tool Map

These are the best GitHub-facing tools and integrations to make ANSARI easy to adopt across DevOps, SRE, and platform teams:

| Need             | Recommended Tool                 | How ANSARI Can Use It                                                    |
| :--------------- | :------------------------------- | :----------------------------------------------------------------------- |
| CI checks        | GitHub Actions                   | Run `ansari check` during pull requests or scheduled reliability audits. |
| Packaging        | uv                                | Manage Python dependencies, scripts, and reproducible installs.          |
| Releases         | GitHub Releases                  | Publish versioned CLI builds and changelogs.                             |
| Security         | Dependabot                       | Keep Typer, Rich, Pydantic, and future SDKs patched.                     |
| Code quality     | Ruff, Black, Pytest              | Add linting, formatting, and automated test gates.                       |
| Project planning | GitHub Issues and Projects       | Track phase-wise roadmap and platform integration tasks.                 |
| Documentation    | README, GitHub Wiki, MkDocs      | Explain supported checks, runbooks, and examples.                        |
| Adoption         | Issue templates and PR templates | Make contributions predictable for SRE and platform engineers.           |

---

## Quick Start

ANSARI uses [`uv`](https://docs.astral.sh/uv/) for dependency management and
packaging — no Poetry required. If you don't have `uv` yet:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Installation and Setup

Clone the repository and install `ansari` as a direct CLI command:

```bash
git clone https://github.com/sameeralam3127/ansari.git
cd ansari
uv tool install --editable .
```

`uv tool install` puts `ansari` straight on your `PATH` — every command below
runs as plain `ansari ...`, no `poetry run` or `uv run` prefix. `--editable`
means changes you make to the source take effect immediately, without
reinstalling.

> If `ansari` isn't found after installing, run `uv tool update-shell` and
> restart your shell so `uv`'s tool directory is on `PATH`.

If you're contributing to ANSARI rather than just using it, `uv sync`
creates a project-local `.venv` with the dev dependencies (`pytest`, `ruff`)
included:

```bash
uv sync
```

### Running Tests and Linting

The same checks that run in CI can be run locally:

```bash
uv run pytest
uv run ruff check .
```

### Basic Commands

Display CLI help:

```bash
ansari --help
```

Show example commands:

```bash
ansari examples
```

### Example Checks

Check an example Kubernetes cluster:

```bash
ansari check eks-cluster-01
```

Check an example pod with verbose output:

```bash
ansari check payment-pod -v
```

Check an example database resource:

```bash
ansari check prod-rds-db
```

Display version information:

```bash
ansari version
```

---

## Naming Guide

| Name                   | Full Form or Meaning                                   | Why It Fits                                                                                         |
| :--------------------- | :----------------------------------------------------- | :-------------------------------------------------------------------------------------------------- |
| **ANSARI**             | Advanced Network SRE & Automated Remediation Interface | Explains that the tool focuses on SRE workflows, network/resource checks, and remediation guidance. |
| **ReliabilityChecker** | Main checker class                                     | Clearer than a generic resource checker because the goal is reliability insight.                    |
| **ResourceHealth**     | Normalized check result                                | Keeps status, summary, signals, and recommendations in one model.                                   |
| **signals**            | Observed facts                                         | Matches how SREs reason from telemetry and resource state.                                          |
| **recommendations**    | Suggested next steps                                   | Turns checks into action and portfolio value.                                                       |

---

## Phase-Wise Development Roadmap

### Phase 1: Foundation

- [x] Finalize CLI naming, help text, README, and package metadata.
- [x] Add `pytest` and `ruff` configuration.
- [x] Add unit tests for `ReliabilityChecker`, each checker module, and CLI commands.
- [x] Add GitHub Actions for linting and tests.
- [x] Add issue templates for bugs, feature requests, and new checkers.

### Phase 2: Local and Kubernetes Checks

- [ ] Add Kubernetes client support for pods, deployments, nodes, events, and namespaces.
- [ ] Detect common reliability issues such as crash loops, pending pods, high restarts, and node pressure.
- [ ] Add `--namespace`, `--context`, and `--output json` options.
- [ ] Generate copy-pasteable troubleshooting hints for common Kubernetes failures.

### Phase 3: Cloud Provider Integrations

- [ ] Add AWS checks for EKS, EC2, RDS, Lambda, IAM, and CloudWatch alarms.
- [ ] Add Azure and GCP integration interfaces after AWS patterns stabilize.
- [ ] Support profile, region, and account discovery.
- [ ] Keep provider-specific code isolated under dedicated modules.

### Phase 4: Terraform and Platform Engineering

- [ ] Add Terraform state inspection and drift detection helpers.
- [ ] Validate remote state locking, encryption, workspace naming, and backend configuration.
- [ ] Add platform scorecards for service readiness, ownership metadata, SLO coverage, and deployment hygiene.
- [ ] Support reusable team profiles for different environments.

### Phase 5: Automation and Adoption

- [ ] Add GitHub Actions examples for pull request checks and scheduled audits.
- [ ] Publish release artifacts through GitHub Releases.
- [ ] Add JSON and Markdown report outputs for CI comments and runbooks.
- [ ] Add Slack, PagerDuty, or incident-management hooks for alert context.
- [ ] Document contribution standards so other DevOps and SRE engineers can add checks easily.

---

## Built With

- **Python 3.11+** for the CLI foundation.
- **Typer** for command line ergonomics.
- **Rich** for terminal formatting.
- **Pyfiglet** for the ANSARI wordmark banner.
- **Pydantic** for typed check results and configuration.
- **uv** for packaging and dependency management.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
