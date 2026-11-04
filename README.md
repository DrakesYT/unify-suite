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
- **Vultr Serverless Inference** — the LLM behind the agents, called through its OpenAI-compatible API
  (default model `glm-5.3-flash`). Agents only read, classify and draft; every reply is validated against a
  schema, and matching, ranking and approvals are plain code.

## Local setup

Requires Docker Desktop. Node.js LTS and [uv](https://docs.astral.sh/uv/) are only needed for running tests/lint outside Docker.

```bash
cp .env.example .env          # then set POSTGRES_PASSWORD and JWT_SECRET (see comments inside)
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

- App: http://localhost:3000 — API docs: http://localhost:3000/api/docs
- Database tables are created/updated automatically when the backend starts (`alembic upgrade head`).
- Add a user (asks for the password):
  `docker compose exec backend python -m app.cli create-user EMAIL "Full Name" ROLE DEPARTMENT`
  — roles: `admin`, `manager`, `employee`, `executive`; departments: `sales`, `finance`, `hr`, `support`, `procurement`.
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
| `JWT_SECRET` | backend | Required. At least 32 random characters; signs login tokens (valid 8 h). |
| `LLM_API_KEY` | backend | Vultr Serverless Inference key. Without it AI endpoints return 503. |
| `LLM_MODEL` | backend | Optional, default `glm-5.3-flash`. |
| `LOG_LEVEL` | backend | Optional, default `INFO`. |

Set them in `.env` locally and in Coolify's Environment Variables page in production. Never commit `.env`.

## License

Copyright © 2026 the UNIFY SUITE authors. All rights reserved — see [LICENSE](LICENSE).
