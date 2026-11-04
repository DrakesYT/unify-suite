# UNIFY SUITE

AI-powered enterprise workforce platform. Five departments (Sales, Finance, HR, Support, Procurement),
one AI agent each, a rule-based orchestrator, a human Approval Center, and an agent activity log.

Built for the lablab.ai **Vultr Agent Rush** hackathon (Challenge 2, "Powering the Future of Work").

## Architecture

React (Vite) → Caddy (static files + `/api` pass-through) → FastAPI → PostgreSQL 16, all in one `docker-compose.yml`.
See [docs/architecture.md](docs/architecture.md).

## How Vultr is used

- **Vultr Cloud Compute** — one VM runs the whole stack.
- **Coolify** (Vultr Marketplace image) — builds `docker-compose.yml` from this repository and serves it over HTTPS.
- **Vultr Serverless Inference** — the LLM behind the agents.

## Local setup

Requires Docker Desktop. Node.js LTS and [uv](https://docs.astral.sh/uv/) are only needed for running tests/lint outside Docker.

```bash
cp .env.example .env          # then put a letters-and-digits password in POSTGRES_PASSWORD
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

- App: http://localhost:3000 — API docs: http://localhost:3000/api/docs
- Frontend with hot reload: `cd frontend && npm install && npm run dev` (http://localhost:5173, forwards `/api` to the backend on port 8000)

### Tests and lint

```bash
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd frontend && npm run lint && npm run format:check && npm run build
```

## Deploy

Coolify on the Vultr VM builds `docker-compose.yml` from this repository on every push. The public domain is
attached to the `frontend` service (port 80); no other service is exposed.

## Environment variables

| Name | Used by | Notes |
|---|---|---|
| `POSTGRES_PASSWORD` | db, backend | Required. Letters and digits only. |
| `LOG_LEVEL` | backend | Optional, default `INFO`. |

Set them in `.env` locally and in Coolify's Environment Variables page in production. Never commit `.env`.

## License

Copyright © 2026 the UNIFY SUITE authors. All rights reserved — see [LICENSE](LICENSE).
