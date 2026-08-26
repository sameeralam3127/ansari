<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset=".github/assets/hero-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset=".github/assets/hero-light.svg">
  <img alt="ANSARI" src=".github/assets/hero-light.svg" width="100%">
</picture>

[![CI](https://img.shields.io/badge/status-v0.1--pipeline-4FD9A6.svg)](ROADMAP.md)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

</div>

---

## What is ANSARI

ANSARI is a self-hosted, open-source developer delivery platform: an
orchestration layer over CI, container builds, GitOps deployment to
Kubernetes, and observability — built entirely on open-source components
(GitHub Actions, Docker, Trivy, Argo CD, Helm, Prometheus/Grafana/Loki,
OpenTofu). ANSARI itself is the API + CLI + dashboard that ties them
together, not a replacement for any of them.

See [ROADMAP.md](ROADMAP.md) for the full phased plan (v0.1 → v1.0) and the
skills each phase demonstrates, and [ARCHITECTURE.md](ARCHITECTURE.md) for
how the pieces fit together.

## Status: v0.1 — Pipeline

What exists today:

- **API** (`src/ansari/api`) — FastAPI + SQLAlchemy + Alembic + PostgreSQL.
  Resources: `Project`, `Environment`, `PipelineRun`, `Deployment`.
  Structured JSON logging, request-ID middleware, `/healthz` + `/readyz`.
- **CLI** (`src/ansari/cli`) — `ansari new <name>` scaffolds a new service
  with a production Dockerfile, a GitHub Actions pipeline (lint → type-check
  → test → build → Trivy scan), and a Helm chart.
- **CI** (`.github/workflows/ci.yml`) — lint (ruff), format check, type
  check (mypy), tests against a real Postgres service container, then a
  Docker build + Trivy scan.

## Quickstart

```bash
uv sync --extra dev
docker compose up -d db
uv run alembic upgrade head
uv run uvicorn ansari.api.main:app --reload
```

Or run the whole stack (API + Postgres) in containers:

```bash
docker compose up --build
```

Scaffold a new service:

```bash
uv run ansari new payment-api --language python --database postgres
```

## Development

```bash
make setup    # install deps + pre-commit hooks
make check    # lint + typecheck + test
```

## Roadmap

Next up: Kubernetes deployment (v0.2) and GitOps via Argo CD (v0.3). Full
plan in [ROADMAP.md](ROADMAP.md).
