# ANSARI

**Your self-hosted AI support engineer.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Backend: uv](https://img.shields.io/badge/backend-uv%20%2B%20FastAPI-2E6E9E.svg)](https://docs.astral.sh/uv/)
[![Frontend: Next.js](https://img.shields.io/badge/frontend-Next.js-000000.svg)](https://nextjs.org)

> **Ansari** (Arabic) means "the helper." This project is an open-source,
> self-hosted AI support platform: upload your knowledge, embed one script
> tag, and get an AI chat widget answering questions on any website.

IT support is the first use case — but the architecture (knowledge base,
LLM gateway, widget, admin) is deliberately generic, so the same platform
can later power HR assistants, docs bots, or internal knowledge assistants
without a rewrite.

> **Status: M0 — scaffold.** Backend health check, admin shell, and widget
> shell are wired together. Real ingestion and chat land in M1–M2 (see
> [Milestones](#milestones)). This repo previously held a Python SRE
> reliability-checker CLI; that code is preserved at the `legacy-sre-cli`
> git tag.

---

## Quick Start

Requires [Docker](https://www.docker.com/) and Docker Compose.

```bash
git clone https://github.com/sameeralam3127/ansari.git
cd ansari
cp .env.example .env
docker compose up --build
```

Then open:

- **Admin dashboard** — <http://localhost:3000>
- **Backend health check** — <http://localhost:8001/health>
- **Widget demo** — open `widget/demo.html` directly in a browser (points
  at `widget.js` in the same folder; no server required to preview it)

## Architecture

```
Any website
     │ embeds
     ▼
widget.js (vanilla JS)     Admin dashboard (Next.js)
     │                              │
     └───────────► FastAPI backend ◄┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
     Postgres + pgvector        LLM Gateway
     (docs, chunks, chat)     (one interface,
                                one adapter: OpenAI)
```

One backend service, one database, one static JS file. No message queue,
object store, or dedicated vector database yet — `pgvector` handles
retrieval at this scale, and the `LLMProvider` interface has exactly one
adapter until M6 proves it holds with a second.

## Milestones

- [x] **M0** — Scaffold: Docker Compose, health check, CI, `.env.example`
- [ ] **M1** — Ingestion: upload txt/md/pdf → chunk → embed → pgvector
- [ ] **M2** — Chat endpoint: retrieval + OpenAI completion, cited sources
- [ ] **M3** — Widget wired to `/api/v1/chat`, Markdown rendering
- [ ] **M4** — Admin: document upload/list/delete, embed snippet, conversation log
- [ ] **M5** — Streaming responses (SSE) + typing indicator
- [ ] **M6** — Second LLM provider (Ollama) — proves the adapter interface
- [ ] **M7** — Widget theme toggle, basic usage counts, one-command install script

Everything past M7 (SSO, multi-tenancy, Kubernetes/Helm, a plugin
marketplace, additional providers and knowledge sources) is intentionally
deferred until the core loop — upload → answer → embed — is proven in
real use.

## Development

```bash
# Backend
cd backend && uv sync
uv run pytest
uv run ruff check .

# Create the pgvector extension + tables (schema isn't wired to any
# endpoint yet — this is prep for M1's ingestion pipeline)
uv run python -m app.db.init_db

# Frontend
cd frontend && npm ci
npm run lint
npm run build
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
