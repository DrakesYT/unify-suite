# Architecture

```mermaid
flowchart LR
    user([Browser]) -->|HTTPS| proxy[Coolify proxy<br/>TLS + domain]
    subgraph vm[Vultr Cloud Compute VM: docker-compose.yml]
        proxy --> fe[frontend<br/>Caddy: React build + /api pass-through]
        fe -->|/api/*| be[backend<br/>FastAPI + uvicorn<br/>named volume uploads]
        be -->|SQLAlchemy| db[(db<br/>PostgreSQL 16<br/>named volume pgdata)]
    end
    be -->|HTTPS, OpenAI-compatible API| llm[Vultr Serverless Inference<br/>glm-5.3-flash]
```

- Only `frontend:80` is reachable from outside (through Coolify). `backend` and `db` live on the private compose network.
  Uploaded files are stored on the `uploads` volume, outside the web root.
- `GET /api/health` runs `SELECT 1`; Docker uses it as the backend healthcheck.
- Every request gets an `X-Request-ID`; logs are one JSON object per line tagged with it.
- Errors always return `{"error": {"code", "message"}}`.
- Agents (`backend/app/agents/`) get typed input, return typed output and never touch the database.
  The runner checks the caller's permission, retries invalid or timed-out model replies twice (2 s, 8 s),
  and writes an `agent_tasks` + `audit_logs` row for every agent call and every tool call.
  A connection that fails before any reply (a stale keep-alive) is retried at once inside the LLM
  client, within the agent's time limit, so it never counts as a failed task.

  | Agent | Department | Uses the LLM to | Time limit |
  |---|---|---|---|
  | Aura Router | caller's own | pick one route from a fixed list | 10 s |
  | Lead Qualifier | sales | rate a lead hot/warm/cold with a reason | 20 s |
  | Outreach Writer | sales | draft a first email to a qualified lead | 30 s |
  | Invoice Processor | finance | extract invoice fields | 60 s |
  | Resume Parser | hr | extract skills, years, education | 30 s |
  | Resume Screener | hr | quote evidence for each requirement | 30 s |
  | Interview Invite Writer | hr | draft an interview invitation listing code-picked times | 30 s |
  | Ticket Investigator | support | classify a ticket; explain it from the customer's orders | 30 s |
  | Vendor Comparator | procurement | explain the code-computed ranking | 20 s |
  | Payment Reminder Writer | finance | draft a reminder for an overdue customer order | 30 s |
  | Supplier Follow-up Writer | procurement | draft a chase email for a late purchase order | 30 s |
  | Verification Agent | finance | nothing (rules only) | 5 s |
- Uploads (`services/uploads.py`) are refused before anything is stored if the agents could not read
  them: only PDF, CSV and TXT up to 10 MB, type checked by content (magic bytes), images and Word files
  get a message saying what to do, and a PDF with no text layer (a scan) is refused with its reason, so
  no workflow starts on a file that cannot succeed.
- Invoice intake: upload (type checked by content, max 10 MB) → `read_upload` → Invoice Processor (LLM
  extracts the document type, fields, the PO reference as printed and every line item) → `get_po` → code
  (`app/invoice_checks.py`, `services/finance.py`): only a document of type invoice with a total of zero or
  more can be paid (a credit note, quotation or reminder is flagged `not_an_invoice`); the PO reference is
  normalised (`po-1007` → `PO-1007`) and one naming two numbers is ambiguous, never guessed; each line's
  quantity × price and the lines' sum must equal the total; match by PO status (must be approved), vendor,
  currency and amount (and, in Workflow B, the PO the invoice names must be the PO chosen) → duplicate check →
  `save_invoice` or `flag_anomaly` (a `no_po` anomaly records whether the PO was missing, unknown or
  ambiguous). `app/safety.py` (code, no model) scans invoice and call-transcript text for lines aimed at the
  AI; invoice findings are audited (`security.instruction_text_found`) and shown as a prompt-injection warning
  on the run and on the approval card, call findings above the analysis. Duplicates are recorded in
  `invoice_anomalies`, never inserted.
- Receivables (money owed to us): an unpaid customer order is due on its order date + the customer's
  terms (`net_30`). Code computes `days_overdue` and puts a customer with an open refund, billing or legal
  ticket on hold (never chased). For an overdue order the Payment Reminder Writer drafts a reminder that
  must quote the order number; it goes through the shared approve-then-send path (finance manager).
- Workflow B (Supplier Payment Verification) is a plain state machine (`backend/app/orchestrator/`):

  ```mermaid
  flowchart LR
      P1[P1 load PO] --> F2[F2 match invoice to PO]
      F1[F1 extract invoice - LLM] --> F2
      F2 -- mismatch --> F3[F3 discrepancy report]
      F2 -- matched --> A1
      F3 --> A1{{A1 manager approval}}
      A1 -- approved --> F4[F4 submit payment]
      A1 -- rejected --> V1
      F4 --> V1[V1 verification - rules only]
  ```

  A step runs only when the steps it depends on have finished; `when` conditions skip F3 / F4.
  Steps run in a FastAPI background task and the UI polls every 5 s. A1 always pauses the run
  (`waiting_approval`) until a finance manager (or an admin) approves or rejects in the Approval Center; nobody can
  decide their own request. A failed step pauses the run as `failed`; Retry re-runs only failed
  steps with their stored inputs. Payments are created only for an approved request of that invoice.
- Sales: the Lead Qualifier gets only company, email domain, status, priority, value and notes (no
  contact name or full email) and must return hot/warm/cold, a reason of 20+ words and the fields it cited.
  For a qualified lead the Outreach Writer drafts a first email from the same facts; code rejects drafts
  with links, placeholders, email addresses or greetings, then adds "Hi <first name>," and the rep's
  signature. The rep edits and asks for approval (`send_email`, sales manager); only an approved email
  is sent (`app/mailer/`, Resend over HTTPS) by the `mailer → send_email` tool. A failed send is kept as
  `failed` with the provider's reason and can be retried without a new approval. `EMAIL_REDIRECT_TO`
  sends every email to one demo inbox.
- HR: the Resume parser extracts skills, years and education at upload. The Resume Screener only returns
  evidence (requirement + exact quote); code rejects any quote not found in the resume and computes the
  score: 70 × (skills with evidence ÷ required skills) + 30 × min(years ÷ minimum years, 1).
- Interviews: a candidate screened 50+ for an open job can be invited. `app/scheduling.py` (code) picks the
  first free 45-minute start (10, 11, 14, 15 or 16:00 PKT) on each of the next three working days, skipping
  times already held. The slots are held with the draft (`interview_slots`); the Interview Invite Writer must
  copy every time verbatim or the draft is retried. An HR manager approves; a rejected invite frees its times.
- Support: new tickets are saved, then classified (category + urgency). Investigation sends the customer's
  last 20 orders; code rejects any cited order number that is not theirs. Escalating a refund or legal ticket
  creates an approval for a support manager; approved → resolved, rejected → reopened. Replies are drafts only.
- Procurement: vendors quote a unit price per request. Code ranks them: 50% price + 25% lead time + 25%
  on-time rate, each relative to the best offer (ties: cheaper, then name). The Vendor Comparator only
  explains the result and must name the winner. A procurement manager approves the request; every PO
  (from a request or created directly) waits in the Approval Center as `pending_approval`.
  Approval starts delivery tracking: `ordered_on` = today, `expected_delivery` = today + the vendor's
  lead time. Code computes `delivery_status` (on_track / late / delivered) and `days_late`; the buyer
  marks delivery or records a new date the supplier confirmed. For a late order the Supplier Follow-up
  Writer drafts a chase (it must quote the PO number); it goes through the same approve-then-send path
  as sales emails (`services/outbound.py`), approved by a procurement manager.
- Dashboard (managers, executives, admins): KPIs and charts are SQL aggregates; the feed is the latest 20
  audit events. `/api/dashboard/overview` feeds the panels in one read: a hiring board (each candidate in
  the furthest stage their records prove: applied → screened → invite pending → invite sent), the deal
  board (leads per status, win rate, won this quarter vs the quarterly target, which an executive or admin
  sets on the dashboard: `PUT /api/settings/sales-target`, stored in `app_settings`, audited; until then
  `SALES_QUARTER_TARGET` applies), open
  tickets by urgency, money stuck in invoices / customer payments / late deliveries, and an insights line
  worded by code from those numbers (no model). The top-bar search (`/api/search`) applies the same
  read rule as every page, so an employee only finds their own department's records. The Command Center lists every agent/tool call (`/api/agents/activity`), retries failed
  workflow runs, and draws the latest supplier-payment run as a hand-off graph
  (`/api/agents/handoff`, read-only). The Sales page's funnel and weekly trend lines come from
  `/api/sales/summary` (read-only SQL aggregates; weeks are counted in UTC).
- Aura chat: the Aura Router picks one route from a fixed list and names the target; code finds the record,
  checks the user's rights and runs the department agent, so Aura can never do more than the user can.
- Email quality gate (`agents/writing_checks.py`): `check_draft` (all four email writers), the Ticket
  Investigator's customer reply and the Brief Writer run plain-code checks. Hard style findings and any
  amount, reference, date or day count not found in the writer's input facts raise `LLMOutputError`, so the
  runner retries. Soft findings are returned on every email as `style_notes` (computed from the current
  text, so they also cover a person's edits) and listed in the Why? panel.
- Calls (`services/calls.py`, `/api/calls`, table `call_transcripts`, migration 0011): a transcript
  (pasted text or a TXT/PDF upload, same upload checks) belongs to exactly one lead or one ticket, and
  its department decides who may read or add it. The Call Analyzer returns summary, sentiment,
  concerns and action items; `verify` rejects quotes not found in the transcript. Talk share per
  speaker is counted by code from "Name:" lines. A failed analysis keeps the transcript ("Analyse
  again"). Nothing on the lead or ticket changes because of a call.
- "Why?" drawer (`services/explain.py`, `GET /api/explain/...`): read-only, same department read rule as
  the pages. It rebuilds an agent's input with the same function the service used and looks up
  `agent_tasks` rows with the same `input_hash` (runs use `execution_id`), so a match proves the input
  shown is the one the model saw. Output comes from the stored result, rules from code, people from
  `audit_logs`. Categories set by a person (seed data) are not presented as AI output.
- Aura brief and quick actions (`services/brief.py`): code collects the facts for the reader (dashboard
  counts, plus which pending decisions are theirs and which belong to another manager) and a focus line
  from their role. The Brief Writer only words them; `check_brief` rejects a draft with any number that
  no fact contains, so the runner retries and finally the code-written brief is kept. The panel shows the
  code version at once (`?writer=code`) and swaps in the model's when it arrives. Quick actions are built
  from real records (newest open job, unrated lead, pending purchase request, most urgent ticket) and send
  Aura a normal chat message. Voice input uses the browser's own speech recognition (Chrome, Edge);
  only the recognised text reaches the backend.
- Demo data: `python -m app.seed` creates the demo company idempotently (natural keys: email, vendor name, PO
  number, …). AI results are not pre-filled; they come from running the agents. `python -m app.import_demo`
  then adds the fictional data set in `backend/demo_data/` (CSV sheets, resume PDFs, Word call transcripts)
  without changing existing records: repeat leads are merged by email, identical tickets imported once, new
  tickets classified, resumes parsed and screened for the job applied to (4 at a time, each in its own
  session; `candidates.job_id` records the application, and screening a job covers only its applicants
  not yet screened, so no resume is screened twice by accident), and calls attached to the lead or ticket they name and analysed. Word files are turned into text
  by `app/docx_text.py` (standard library only); uploads themselves stay PDF/CSV/TXT.
- Accuracy check: `python -m app.evaluate` runs the same agents and rules on the demo files in a scratch
  SQLite database (seed + the sheet's vendors and jobs) and compares with the answer keys in
  `backend/demo_data/answer_keys/`; the scoring rules are fixed in code and pinned by tests.
- The frontend container serves `index.html` with `Cache-Control: no-cache` and hashed `/assets/*` as immutable, so a
  new release is picked up on the next page load. Its Caddy also sets the security headers (Content Security Policy,
  HSTS, frame denial, `nosniff`, referrer and permissions policies), refuses bodies over 12 MB, and works out the
  visitor's IP from `X-Forwarded-For` trusting only private-network proxies (Coolify's), passing that single address
  to the backend.
- Lists use cursor pagination: `?limit=&cursor=`, newest first.
- Schema is managed by Alembic (`backend/alembic/`) and applied on backend start-up. `audit_logs` is
  append-only: a PostgreSQL trigger rejects `UPDATE` and `DELETE`.
- Auth: `POST /api/auth/login` opens a row in `user_sessions` and sets the HS256 JWT (valid 8 h, names the
  session) as an `HttpOnly`, `Secure`, `SameSite=Strict` cookie on `/api`; bcrypt password hashes. Every request
  checks that the session is still open, so `POST /api/auth/logout` ends the token at once. Cookie requests that
  change data need the `X-Requested-With: unify` header (CSRF); Bearer tokens are accepted for API clients. Failed
  sign-ins and model-backed requests are rate limited in memory (`app/ratelimit.py`; one backend process). Each
  user has one role and one department. `POST /api/auth/demo-switch` lets a signed-in `@demo.example.com` account
  switch to another demo account (closing the old session) (the guided tour and the "View as" menu use it). The demo accounts share
  one password, so this adds no access; admins and real accounts can neither switch nor be switched to,
  and every switch is audited. Department routers use one guard:

  | Role | Own department | Other departments |
  |---|---|---|
  | employee | read + write | none |
  | manager | read + write | read |
  | executive | read | read |
  | admin | read + write | read + write |
