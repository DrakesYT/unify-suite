# UNIFY SUITE

AI-powered enterprise workforce platform. Five departments (Sales, Finance, HR, Support, Procurement),
one AI agent each, a rule-based orchestrator, a human Approval Center, an agent activity log (Command Center),
an executive dashboard and the Aura chat assistant.

Built for the lablab.ai **Vultr Agent Rush** hackathon (Challenge 2, "Powering the Future of Work").

**Live demo:** https://unify.65.20.84.171.sslip.io — API docs at `/api/docs`.

## How Vultr is used

| Vultr service | What it does here |
|---|---|
| **Vultr Cloud Compute** | One VM (4 vCPU, 8 GB, Mumbai) runs the whole platform: web app, API, orchestrator, agents and PostgreSQL. A Vultr firewall group allows only SSH and HTTP(S); the database is never exposed. |
| **Coolify** (Vultr Marketplace app) | Installed on the same VM. Every push to GitHub triggers a webhook; Coolify rebuilds `docker-compose.yml` and serves the app over HTTPS (Let's Encrypt). |
| **Vultr Serverless Inference** | The model behind every agent: `glm-5.3-flash` through the OpenAI-compatible API at `https://api.vultrinference.com/v1` (`backend/app/llm/vultr.py`). Temperature 0, JSON output, a timeout per agent, and every call logged with model, latency and tokens. |

The VM is not just hosting: the orchestrator, the approval logic and every agent run there, and all workflow state
lives in PostgreSQL on the VM.

## Architecture

```mermaid
flowchart LR
    user([Browser]) -->|HTTPS| proxy[Coolify proxy<br/>TLS + domain]
    subgraph vm[Vultr Cloud Compute VM — docker-compose.yml]
        proxy --> fe[frontend<br/>Caddy: React build + /api pass-through]
        fe -->|/api/*| be[backend<br/>FastAPI: routers → services<br/>orchestrator + agents]
        be -->|SQLAlchemy| db[(PostgreSQL 16<br/>named volume)]
    end
    be -->|OpenAI-compatible API| llm[Vultr Serverless Inference<br/>glm-5.3-flash]
    git[GitHub] -->|push webhook| coolify[Coolify on the VM] -->|build + deploy| vm
```

- **frontend** — React + Vite + Tailwind, served by Caddy. Only this container is reachable from the internet.
- **backend** — FastAPI. Thin routers call services, the only code that writes data. Long work (agent calls,
  workflow steps) runs as FastAPI background tasks; the UI polls every 5 s.
- **db** — PostgreSQL 16, schema managed by Alembic. The audit log is append-only (a trigger rejects edits).
- Auth is a JWT with one role (`admin`, `manager`, `employee`, `executive`) and one department per user; the backend
  checks both on every endpoint and every tool call.

More detail (agent time limits, ranking formulas, permission table): [docs/architecture.md](docs/architecture.md).

## Agents: use case and how they execute real tasks

**Use case.** A mid-size company runs sales, finance, HR, support and procurement in separate tools. UNIFY SUITE
gives each department an agent that does the repetitive reading and drafting, while people keep every decision that
moves money or makes a commitment. The rule throughout: **AI reads, code decides, humans approve.**

**How an agent call runs** (`backend/app/agents/runner.py`):

1. The backend checks the user's role and department before the agent starts.
2. The agent sends the document or record to Vultr Serverless Inference and asks for JSON matching a Pydantic schema.
3. The reply is validated. Invalid or timed-out replies are retried twice (after 2 s, then 8 s); after that the
   task fails visibly.
4. The agent can only call the tools on its allowlist. Tools are service functions that check permissions again
   and write to the database. Agents never write data themselves.
5. Every agent call and every tool call writes an `agent_tasks` row (input hash, output, status, duration) and an
   audit row. The Command Center page shows them.

**"Why?" on every AI result.** Lead ratings, candidate scores, ticket investigations, vendor rankings, invoice runs
and drafted emails each have a **Why?** button. It opens a panel with what the AI read, what it said, what plain code
decided and who was involved (from the audit log). Agent calls store only a SHA-256 hash of their input, so the
panel rebuilds the input and shows **Verified** when the hash matches the logged call, or says plainly that the
record has changed since.

Invoices, resumes and tickets are treated as untrusted text: they can only shape schema-validated output, never
permissions or actions. Tags inside a document are stripped so it cannot close its own fence. For invoices, plain
code also scans the text for lines aimed at the AI ("ignore previous instructions", "SYSTEM:", "approve this payment
immediately", …); they are logged to the audit trail and shown to the manager as a red "possible prompt injection"
warning on the run and in the Approval Center.

| Agent | Department | Real task it performs | What plain code does |
|---|---|---|---|
| Invoice Processor | Finance | Reads an uploaded invoice PDF and extracts vendor, number, date, PO and total | Matches it to the PO (approved, same vendor, currency, amount), blocks duplicates, saves the invoice |
| Lead Qualifier | Sales | Rates a lead hot / warm / cold with a 20+ word reason and the fields it relied on | Sends only business fields (no contact name or full email); saves the rating |
| Outreach Writer | Sales | Drafts a first email to a qualified lead | Rejects drafts with links, placeholders or addresses; adds greeting and signature; a sales manager approves; then it is **really sent** through Resend |
| Resume Parser + Screener | HR | Extracts skills and experience; quotes the resume as evidence for each required skill | Rejects quotes not found in the resume, computes the score, ranks candidates |
| Interview Invite Writer | HR | Drafts an interview invitation for a strong candidate | Only candidates screened 50+ qualify; code holds 3 free 45-min office-hour times (never double-booked) and rejects a draft that changes any time; an HR manager approves; then it is sent |
| Ticket Investigator | Support | Classifies new tickets; investigates against the customer's last 20 orders; drafts a reply | Rejects cited orders that are not the customer's; refund/legal escalations need a manager |
| Vendor Comparator | Procurement | Explains why the top vendor wins | Ranks vendors: 50% price + 25% lead time + 25% on-time rate |
| Payment Reminder Writer | Finance | Drafts a reminder for an overdue customer order | Due date = order date + payment terms; customers with an open refund/billing/legal ticket are never chased; a finance manager approves; then it is sent |
| Supplier Follow-up Writer | Procurement | Drafts a chase email to the supplier of a late order | Decides what is late (expected date = order date + vendor lead time); the draft must quote the PO; a procurement manager approves; then it is sent |
| Aura Router | Any | Picks one route for a plain-English request ("compare vendors for the laptops") | Finds the record, checks the user's rights, runs the department agent |
| Brief Writer | Any (managers, executives) | Words a 2-sentence morning brief in Aura from the facts it is given | Collects the facts (live counts, who must decide what), rejects a draft that states any number no fact contains, and shows a code-written brief instantly and whenever the model is unavailable |
| Verification Agent | Finance | — (rules only, no model) | Checks every record of a payment run is linked correctly |

**Workflow B — supplier payment verification**, end to end (`backend/app/orchestrator/`):

1. A finance clerk uploads an invoice and names the PO.
2. **P1** loads the PO; **F1** (Invoice Processor) reads the invoice.
3. **F2** matches invoice and PO in code and checks for duplicates. A mismatch makes **F3** write a discrepancy report.
4. **A1** always pauses the run (`waiting_approval`). A finance manager approves or rejects in the Approval Center;
   nobody can decide their own request.
5. Approved → **F4** creates the payment. Rejected → no payment.
6. **V1** verifies every link (invoice ↔ PO ↔ approval ↔ payment) and the run ends `completed` or `rejected`.

A failed step pauses the run as `failed`; Retry in the UI re-runs only the failed steps with their stored inputs.

## Demo

Load the demo company (safe to run again; it only adds what is missing). It asks for one password that every
demo user gets:

```bash
docker compose exec backend python -m app.seed
```

| Sign in as | Role | Try this |
|---|---|---|
| `ceo@demo.example.com` | executive | Dashboard, Aura chat, Approval Center (read-only) |
| `finance.clerk@demo.example.com` | finance employee | Payments: upload an invoice for `PO-1007`; Customer payments due → SO-1101 → Send payment reminder |
| `finance.manager@demo.example.com` | finance manager | Approval Center: approve or reject the payment and the payment reminder |
| `sales.rep@demo.example.com` | sales employee | Sales leads → Qualify with AI → open the rating → Draft email with AI → Send for approval |
| `sales.manager@demo.example.com` | sales manager | Approval Center: approve & send the email (or reject it) |
| `hr.recruiter@demo.example.com` | HR employee | Hiring → Screen all candidates → Invite to interview (top candidate) |
| `hr.manager@demo.example.com` | HR manager | Approval Center: approve & send the interview invite (or reject it, which frees the times) |
| `support.agent@demo.example.com` | support employee | Support tickets → Investigate, Escalate a refund |
| `support.manager@demo.example.com` | support manager | Approve the refund escalation |
| `buyer@demo.example.com` | procurement employee | Procurement → Compare vendors, Create purchase order; PO-2001 is late → Follow up with supplier |
| `procurement.manager@demo.example.com` | procurement manager | Approve the request, the purchase order and the supplier follow-up email |

The demo password for the live site is given in the lablab.ai submission.

**Guided tour and role switcher:** after signing in with any demo account, press **Tour** in the top bar. Five
steps walk through the dashboard, an invoice upload (as the finance clerk), the approval pause (as the finance
manager), Aura and the Command Center, switching to the right demo account at each step. The account menu's
**View as** list switches between demo roles at any time. Both exist only for `@demo.example.com` accounts.

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
| `RESEND_API_KEY` | backend | Optional. [Resend](https://resend.com) key for sending approved emails. Without it, approved emails are marked failed ("not configured"). |
| `EMAIL_FROM` | backend | Optional, default `UNIFY SUITE <onboarding@resend.dev>`. |
| `EMAIL_REDIRECT_TO` | backend | Optional demo safety: every email goes to this one inbox, with the real recipient noted at the top. |
| `SALES_QUARTER_TARGET` | backend | Optional, default `250000`. Quarterly sales target (whole units) for the dashboard gauge. |
| `SALES_TARGET_CURRENCY` | backend | Optional, default `USD`. Currency of the sales target. |
| `LOG_LEVEL` | backend | Optional, default `INFO`. |

Set them in `.env` locally and in Coolify's Environment Variables page in production. Never commit `.env`.

## License

MIT — see [LICENSE](LICENSE).
