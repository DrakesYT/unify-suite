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
