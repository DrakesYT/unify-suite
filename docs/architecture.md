# Architecture

```mermaid
flowchart LR
    user([Browser]) -->|HTTPS| proxy[Coolify proxy<br/>TLS + domain]
    subgraph vm[Vultr Cloud Compute VM — docker-compose.yml]
        proxy --> fe[frontend<br/>Caddy: React build + /api pass-through]
        fe -->|/api/*| be[backend<br/>FastAPI + uvicorn]
        be -->|SQLAlchemy| db[(db<br/>PostgreSQL 16<br/>named volume pgdata)]
    end
```

- Only `frontend:80` is reachable from outside (through Coolify). `backend` and `db` live on the private compose network.
- `GET /api/health` runs `SELECT 1`; Docker uses it as the backend healthcheck and the frontend polls it every 5 s.
- Every request gets an `X-Request-ID`; logs are one JSON object per line tagged with it.
- Errors always return `{"error": {"code", "message"}}`.
- Agents (`backend/app/agents/`) get typed input, return typed output and never touch the database.
  The runner checks the caller's permission, retries invalid or timed-out model replies twice (2 s, 8 s),
  and writes an `agent_tasks` + `audit_logs` row for every agent call and every tool call.
- Invoice intake: upload (type checked by content, max 10 MB) → `read_upload` → Invoice Processor (LLM
  extracts fields) → `get_po` → match by vendor, currency and amount (code) → duplicate check (code) →
  `save_invoice` or `flag_anomaly`. Duplicates are recorded in `invoice_anomalies`, never inserted.
- Lists use cursor pagination: `?limit=&cursor=`, newest first.
- Schema is managed by Alembic (`backend/alembic/`) and applied on backend start-up. `audit_logs` is
  append-only: a PostgreSQL trigger rejects `UPDATE` and `DELETE`.
- Auth: `POST /api/auth/login` returns an HS256 JWT valid 8 h (bcrypt password hashes). Each user has one
  role and one department. Department routers use one guard:

  | Role | Own department | Other departments |
  |---|---|---|
  | employee | read + write | none |
  | manager | read + write | read |
  | executive | read | read |
  | admin | read + write | read + write |
