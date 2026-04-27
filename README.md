# A.N.S.A.R.I.

**Advanced Network SRE & Automated Remediation Interface**

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Linted with Ruff](https://img.shields.io/badge/lint-ruff-46a758.svg)](https://github.com/astral-sh/ruff)
[![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC.svg)](https://pytest.org)

> **Ansari** means "the helper." This project brings that idea into DevOps, SRE, and platform engineering by helping teams investigate infrastructure issues and move toward safe automated remediation from one readable CLI.

ANSARI is a Python command line tool for engineers who want one friendly entry point to inspect networks, cloud resources, Kubernetes workloads, Terraform state, and CI/CD signals. The long-term goal is to turn scattered operational checks into consistent answers and remediation guidance that are easy to run locally, in GitHub Actions, or inside a platform engineering workflow.

## What Issue ANSARI Solves

During production support or daily platform operations, engineers often lose time switching between cloud consoles, Kubernetes commands, Terraform state, dashboards, alerts, and runbooks. That slows down triage and makes it harder to answer the basic question: "what is wrong, and what should I check next?"

ANSARI is designed to reduce that friction by collecting network, service, and resource signals and presenting them in a simple operational format:

- What resource am I checking?
- Is it healthy, degraded, unhealthy, or unknown?
- What signals matter right now?
- What should I check or fix next?
- Can this be automated in CI, incident response, or platform workflows?

In simple words: ANSARI helps an engineer move from **alert** to **understanding** to **next action** faster.

## How It Helps DevOps, SRE, and Platform Teams

- **Faster triage:** Start with `ansari check <resource>` instead of remembering multiple commands.
- **Consistent output:** Every check returns a status, summary, signals, and next steps.
- **Lower context switching:** Bring cloud, Kubernetes, Terraform, and CI/CD checks into one CLI flow.
- **Automation ready:** Run checks manually, from GitHub Actions, or as scheduled reliability audits.
- **Easy to extend:** Add new resource checkers without changing the user-facing command style.

## Why It Is Easy to Use

ANSARI is intentionally built around a small command set:

```bash
poetry run ansari check eks-cluster-01
poetry run ansari check payment-pod
poetry run ansari check prod-rds-db
```

The output is written for humans first:

| Output Area | What It Means |
| --- | --- |
| Resource Type | What kind of infrastructure ANSARI recognized. |
| Status | `healthy`, `degraded`, `unhealthy`, or `unknown`. |
| Summary | One-line operational meaning of the check. |
| Signals | Facts gathered from the resource or integration. |
| Next Steps | Practical checks or fixes an engineer can take next. |

## Current Features

- **Readable CLI:** Built with `Typer` and `Rich` for clean terminal output.
- **Reliability Check Model:** Normalized health states, resource types, signals, and recommendations.
- **SRE-Friendly Output:** Shows summary, signals, and next steps instead of raw status only.
- **Extensible Module Layout:** New checkers can be added under `ansari/modules/`.
- **Compatibility Layer:** The old `ResourceChecker` import still works while the clearer `ReliabilityChecker` name is introduced.

## Best-Fit GitHub Tool Map

These are the best GitHub-facing tools and integrations to make ANSARI easy to adopt across DevOps, SRE, and platform teams:

| Need             | Recommended Tool                 | How ANSARI Can Use It                                                    |
| ---------------- | -------------------------------- | ------------------------------------------------------------------------ |
| CI checks        | GitHub Actions                   | Run `ansari check` during pull requests or scheduled reliability audits. |
| Packaging        | Poetry                           | Manage Python dependencies, scripts, and reproducible installs.          |
| Releases         | GitHub Releases                  | Publish versioned CLI builds and changelogs.                             |
| Security         | Dependabot                       | Keep Typer, Rich, Pydantic, and future SDKs patched.                     |
| Code quality     | Ruff, Black, Pytest              | Add linting, formatting, and automated test gates.                       |
| Project planning | GitHub Issues and Projects       | Track phase-wise roadmap and platform integration tasks.                 |
| Documentation    | README, GitHub Wiki, MkDocs      | Explain supported checks, runbooks, and examples.                        |
| Adoption         | Issue templates and PR templates | Make contributions predictable for SRE and platform engineers.           |

## Quick Start

Install dependencies with Poetry:

```bash
git clone https://github.com/sameeralam3127/ansari.git
cd ansari
poetry install
```

Display CLI help:

```bash
poetry run ansari --help
```

Check an example Kubernetes cluster:

```bash
poetry run ansari check eks-cluster-01
```

Check an example pod with verbose output:

```bash
poetry run ansari check payment-pod -v
```

Check an example database resource:

```bash
poetry run ansari check prod-rds-db
```

Display version information:

```bash
poetry run ansari version
```

## Naming Guide

| Name               | Full Form or Meaning                                    | Why It Fits                                                                      |
| ------------------ | ------------------------------------------------------- | -------------------------------------------------------------------------------- |
| ANSARI             | Advanced Network SRE & Automated Remediation Interface | Explains that the tool focuses on SRE workflows, network/resource checks, and remediation guidance. |
| ReliabilityChecker | Main checker class                                      | Clearer than a generic resource checker because the goal is reliability insight. |
| ResourceHealth     | Normalized check result                                 | Keeps status, summary, signals, and recommendations in one model.                |
| signals            | Observed facts                                          | Matches how SREs reason from telemetry and resource state.                       |
| recommendations    | Suggested next steps                                    | Turns checks into action and portfolio value.                                    |

## Phase-Wise Development Roadmap

### Phase 1: Foundation

- Finalize CLI naming, help text, README, and package metadata.
- Add `pytest` and `ruff` configuration.
- Add unit tests for `ReliabilityChecker` and CLI commands.
- Add GitHub Actions for linting and tests.
- Add issue templates for bugs, feature requests, and new checkers.

### Phase 2: Local and Kubernetes Checks

- Add Kubernetes client support for pods, deployments, nodes, events, and namespaces.
- Detect common reliability issues such as crash loops, pending pods, high restarts, and node pressure.
- Add `--namespace`, `--context`, and `--output json` options.
- Generate copy-pasteable troubleshooting hints for common Kubernetes failures.

### Phase 3: Cloud Provider Integrations

- Add AWS checks for EKS, EC2, RDS, Lambda, IAM, and CloudWatch alarms.
- Add Azure and GCP integration interfaces after AWS patterns stabilize.
- Support profile, region, and account discovery.
- Keep provider-specific code isolated under dedicated modules.

### Phase 4: Terraform and Platform Engineering

- Add Terraform state inspection and drift detection helpers.
- Validate remote state locking, encryption, workspace naming, and backend configuration.
- Add platform scorecards for service readiness, ownership metadata, SLO coverage, and deployment hygiene.
- Support reusable team profiles for different environments.

### Phase 5: Automation and Adoption

- Add GitHub Actions examples for pull request checks and scheduled audits.
- Publish release artifacts through GitHub Releases.
- Add JSON and Markdown report outputs for CI comments and runbooks.
- Add Slack, PagerDuty, or incident-management hooks for alert context.
- Document contribution standards so other DevOps and SRE engineers can add checks easily.

## Built With

- **Python 3.11+** for the CLI foundation.
- **Typer** for command line ergonomics.
- **Rich** for terminal formatting.
- **Pydantic** for typed check results and configuration.
- **Poetry** for packaging and dependency management.

## Portfolio Positioning

ANSARI can stand out as a GitHub portfolio project because it is not only a script collection. It shows:

- CLI design for real engineering workflows.
- SRE thinking through status, signals, and recommendations.
- Platform engineering direction through reusable checks and standardized output.
- Cloud, Kubernetes, Terraform, CI/CD, and incident-readiness roadmap.
- Clean structure that future contributors can understand quickly.

## License

This project is licensed under the MIT License.
