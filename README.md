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

## Demo

Load the demo company (safe to run again; it only adds what is missing). It asks for one password that every
demo user gets:

```bash
docker compose exec backend python -m app.seed
```

| Sign in as | Role | Try this |
|---|---|---|
| `ceo@demo.example.com` | executive | Dashboard, Aura chat, Approval Center (read-only) |
| `finance.clerk@demo.example.com` | finance employee | Supplier payments: upload an invoice for `PO-1007` |
| `finance.manager@demo.example.com` | finance manager | Approval Center: approve or reject the payment |
| `sales.rep@demo.example.com` | sales employee | Sales leads → Qualify with AI |
| `hr.recruiter@demo.example.com` | HR employee | Hiring → Screen all candidates |
| `support.agent@demo.example.com` | support employee | Support tickets → Investigate, Escalate a refund |
| `support.manager@demo.example.com` | support manager | Approve the refund escalation |
| `buyer@demo.example.com` | procurement employee | Procurement → Compare vendors, Create purchase order |
| `procurement.manager@demo.example.com` | procurement manager | Approve the request and the purchase order |

The demo password for the live site is given in the lablab.ai submission.

**Workflow B in two minutes:** as the finance clerk, upload an invoice that references `PO-1007` (ACME, USD 4,250.00).
The AI reads it, code matches it to the PO, and the run pauses at *Manager approval*. Sign in as the finance
manager and approve → the payment is created and the verification step confirms every record is linked. Upload an
invoice for a different amount to see the discrepancy report, and reject it to see the run end with no payment.

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
