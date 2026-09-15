<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset=".github/assets/hero-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset=".github/assets/hero-light.svg">
  <img alt="ANSARI" src=".github/assets/hero-light.svg" width="100%">
</picture>

**Golden paths that don't rot.**

Scaffold services and infrastructure from versioned templates, then keep every
repo current as the templates change.

[![CI](https://github.com/sameeralam3127/ansari/actions/workflows/ci.yml/badge.svg)](https://github.com/sameeralam3127/ansari/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12+-3776AB.svg)](pyproject.toml)

</div>

## Why

A platform team publishes a golden template: a hardened Dockerfile, CI with
vulnerability scanning, a sensible Helm chart. Dozens of repos are scaffolded
from it. The template keeps improving, and the repos never catch up, because
nobody updates forty repos by hand.

Scaffolding tools generate once and walk away. ANSARI keeps track, and answers
the fleet question: **who is behind, and on what?**

## What it does

```bash
ansari new payment-api --type python-service   # scaffold a repo
ansari attach --type k8s-scaling payment-api   # add another template to it
ansari check                                   # is this repo behind? edited?
ansari check --fleet ~/src                     # every repo under a directory
ansari sync --fleet --pr ~/src                 # upgrade stale repos, one PR each
ansari dashboard ~/src                         # the fleet as an HTML page
```

```console
$ ansari check payment-api
Template: python-service
Version:  1.0.0 → 1.1.0 (behind)

1 file(s) modified locally:
  Dockerfile

Locally edited files will be three-way merged, never overwritten.
```

`check` exits non-zero on drift, so a repo can fail its own CI when it falls
behind.

## Templates

| Template | Generates |
|---|---|
| `python-service` | Multi-stage Dockerfile, GitHub Actions CI with Trivy, Helm chart |
| `k8s-scaling` | HorizontalPodAutoscaler and PodDisruptionBudget, attached to a service |
| `terraform-module` | Module skeleton for aws, google or azurerm, with `fmt` and `validate` in CI |
| `ansible-role` | Galaxy role layout, `ansible-lint` and `yamllint` in CI, optional Molecule |

A template is a directory with a `template.yaml`; adding one needs no code
change. `ansari templates` lists what's available.

## Quick start

```bash
git clone https://github.com/sameeralam3127/ansari && cd ansari
uv sync --extra dev

make demo                    # seed a drifted fleet, then check, sync --dry-run, dashboard
open .demo/dashboard.html
```

## How it works

Every generated repo commits a `.ansari/manifest.yaml`:

```yaml
schema: 2
templates:
  - template: python-service
    version: 1.1.0
    variables:
      name: payment-api
      database: postgres
    files:
      Dockerfile: sha256:a1b2c3…
      helm/payment-api/values.yaml: sha256:d4e5f6…
```

The **version** says whether the repo is behind, the **variables** let a newer
version render with the same inputs, and the **file hashes** tell a hand-edited
file from an untouched one:

| File on disk | `check` reports | `sync` does |
|---|---|---|
| matches its hash | unchanged | replaces it with the new version |
| differs | edited | three-way merges, keeping the local change |
| missing | deleted | leaves it deleted |

`check` is read-only and works offline. `sync` merges against the originally
generated file, found in the repo's git history, and never opens a pull request
with conflict markers.

ANSARI writes and compares files. It doesn't run CI, apply Terraform, run
Ansible, or deploy anything.

## Documentation

- [Architecture](docs/architecture.md): components, command flows, the manifest
  and template formats
- [Roadmap](docs/roadmap.md): what's shipped and what's next

## Development

```bash
make setup                   # install dependencies and pre-commit hooks
make check                   # lint, type-check, test
docker compose up --build    # API + Postgres at localhost:8000/docs
```

The API has no authentication, so run it locally only.

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING](.github/CONTRIBUTING.md),
the [Code of Conduct](.github/CODE_OF_CONDUCT.md), and [SECURITY](.github/SECURITY.md)
for reporting vulnerabilities privately.

## License

[MIT](LICENSE)
