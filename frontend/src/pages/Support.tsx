import { useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router";
import { api } from "../api";
import {
  Badge,
  Card,
  Empty,
  ErrorNote,
  PageHeader,
  ghostButton,
  inputClass,
  primaryButton,
} from "../components/ui";
import { when } from "../format";
import { canWrite, useAuth } from "../session";
import type { Approval, Customer, Page, Ticket } from "../types";
import { usePoll } from "../usePoll";
import { WhyButton } from "../components/WhyDrawer";
import { CallsPanel } from "../components/CallsPanel";

const NEEDS_APPROVAL = new Set(["refund", "legal"]);

function NewTicket({
  customers,
  onCreated,
}: {
  customers: Customer[];
  onCreated: (t: Ticket) => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const ticket = await api<Ticket>("/support/tickets", {
        method: "POST",
        body: JSON.stringify({ title, description, customer_id: customerId || null }),
      });
      setTitle("");
      setDescription("");
      onCreated(ticket);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the ticket");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      <select
        className={inputClass}
        value={customerId}
        onChange={(e) => setCustomerId(e.target.value)}
      >
        <option value="">No customer linked</option>
        {customers.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
            {c.company ? ` · ${c.company}` : ""}
          </option>
        ))}
      </select>
      <input
        className={inputClass}
        placeholder="Subject"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        required
      />
      <textarea
        className={inputClass}
        rows={4}
        maxLength={5000}
        placeholder="What the customer wrote"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <button type="submit" disabled={busy} className={`${primaryButton} w-full`}>
        {busy ? "Saving and classifying…" : "Create ticket"}
      </button>
      <ErrorNote message={error} />
    </form>
  );
}

function TicketDetail({
  ticket,
  customer,
  editable,
  onChange,
}: {
  ticket: Ticket;
  customer: Customer | undefined;
  editable: boolean;
  onChange: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [approval, setApproval] = useState<Approval | null>(null);
  const inv = ticket.investigation;
  const closed = ticket.status === "resolved" || ticket.status === "closed";

  const run = async (what: string, path: string, body?: unknown) => {
    setBusy(what);
    setError(null);
    try {
      const res = await api<{ approval?: Approval | null }>(path, {
        method: "POST",
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (what === "escalate") setApproval(res.approval ?? null);
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card title="Ticket">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-white">{ticket.title}</h3>
          <p className="text-xs text-slate-500">
            {customer
              ? `${customer.name}${customer.company ? ` · ${customer.company}` : ""}`
              : "No customer"}{" "}
            · opened {when(ticket.created_at)}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {ticket.category && <Badge value={ticket.category} />}
          {ticket.urgency && <Badge value={ticket.urgency} />}
          <Badge value={ticket.status} />
          {(ticket.category || inv) && <WhyButton path={`ticket/${ticket.id}`} />}
        </div>
      </div>
      {ticket.description && (
        <p className="mt-3 text-sm whitespace-pre-wrap text-slate-300">{ticket.description}</p>
      )}

      {editable && !closed && (
        <div className="mt-4 flex flex-wrap gap-2">
          {!ticket.category && (
            <button
              disabled={!!busy}
              onClick={() => run("classify", `/support/tickets/${ticket.id}/classify`)}
              className={ghostButton}
            >
              {busy === "classify" ? "Classifying…" : "Classify with AI"}
            </button>
          )}
          <button
            disabled={!!busy || !ticket.customer_id}
            title={ticket.customer_id ? undefined : "Link a customer first"}
            onClick={() => run("investigate", `/support/tickets/${ticket.id}/investigate`)}
            className={ghostButton}
          >
            {busy === "investigate"
              ? "Investigating…"
              : inv
                ? "Investigate again"
                : "Investigate orders"}
          </button>
        </div>
      )}
      <ErrorNote message={error} />

      {inv && (
        <div className="mt-5 space-y-3">
          <h4 className="text-xs font-semibold text-slate-400 uppercase">Likely causes</h4>
          <ul className="space-y-2">
            {inv.likely_causes.map((c) => (
              <li key={c.cause} className="rounded-lg bg-navy-950/70 p-3 text-sm text-slate-200">
                {c.cause}
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {c.order_numbers.map((n) => (
                    <span
                      key={n}
                      className="rounded bg-navy-800 px-1.5 py-0.5 font-mono text-xs text-accent-cyan"
                    >
                      {n}
                    </span>
                  ))}
                </div>
              </li>
            ))}
          </ul>
          <p className="text-sm text-slate-300">
            <span className="text-slate-500">Next step: </span>
            {inv.next_step}
          </p>
          <div>
            <h4 className="text-xs font-semibold text-slate-400 uppercase">
              Draft reply (not sent)
            </h4>
            <p className="mt-1 rounded-lg border border-navy-800 p-3 text-sm whitespace-pre-wrap text-slate-300">
              {inv.draft_reply}
            </p>
          </div>
          <p className="text-xs text-slate-500">
            Orders checked: {inv.order_numbers_used.join(", ") || "none"}
          </p>
        </div>
      )}

      {editable && !closed && ticket.status !== "escalated" && (
        <div className="mt-5 space-y-2 border-t border-navy-800 pt-4">
          <input
            className={inputClass}
            placeholder="Escalation note (optional)"
            value={note}
            maxLength={1000}
            onChange={(e) => setNote(e.target.value)}
          />
          <button
            disabled={!!busy}
            onClick={() => run("escalate", `/support/tickets/${ticket.id}/escalate`, { note })}
            className={primaryButton}
          >
            {busy === "escalate" ? "Escalating…" : "Escalate"}
          </button>
          {ticket.category && NEEDS_APPROVAL.has(ticket.category) && (
            <p className="text-xs text-amber-200">
              {ticket.category} escalations wait for a support manager's approval.
            </p>
          )}
        </div>
      )}
      {(approval || ticket.status === "escalated") && (
        <p className="mt-4 text-sm text-amber-200">
          {approval ? "Sent to the " : "Escalated. Any approval waits in the "}
          <Link to="/approvals" className="underline">
            Approval Center
          </Link>
          .
        </p>
      )}
      <CallsPanel ticketId={ticket.id} editable={editable} />
    </Card>
  );
}

const TICKET_HASH = "#ticket-";

export function Support() {
  const { user } = useAuth();
  const editable = Boolean(user && canWrite(user, "support"));
  const tickets = usePoll<Page<Ticket>>("/support/tickets?limit=100");
  const customers = usePoll<Customer[]>("/support/customers");
  // A link to /support#ticket-<id> (search, dashboard) opens that ticket.
  const { hash } = useLocation();
  const linked = hash.startsWith(TICKET_HASH) ? hash.slice(TICKET_HASH.length) : null;
  const [picked, setPicked] = useState<string | null>(linked);
  const [seenHash, setSeenHash] = useState(hash);
  if (hash !== seenHash) {
    setSeenHash(hash);
    if (linked) setPicked(linked);
  }
  const ticket = tickets.data?.items.find((t) => t.id === picked) ?? tickets.data?.items[0];
  const customerById = new Map((customers.data ?? []).map((c) => [c.id, c]));

  return (
    <>
      <PageHeader
        title="Support tickets"
        subtitle="The Ticket Investigator classifies each ticket and checks the customer's orders. Refunds and legal escalations need a manager."
      />
      <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
        <div className="space-y-6">
          {editable && (
            <Card title="New ticket">
              <NewTicket
                customers={customers.data ?? []}
                onCreated={(t) => (setPicked(t.id), void tickets.reload())}
              />
            </Card>
          )}
          <Card title="Queue">
            <ErrorNote message={tickets.error} />
            {tickets.data?.items.length === 0 && <Empty>No tickets.</Empty>}
            <ul className="space-y-1">
              {tickets.data?.items.map((t) => (
                <li key={t.id} id={`ticket-${t.id}`}>
                  <button
                    onClick={() => setPicked(t.id)}
                    className={`w-full rounded-lg px-3 py-2 text-left text-sm ${
                      t.id === ticket?.id
                        ? "bg-accent-purple/20 text-white"
                        : "text-slate-300 hover:bg-navy-800"
                    }`}
                  >
                    <span className="block truncate">{t.title}</span>
                    <span className="mt-1 flex flex-wrap gap-1">
                      {t.category && <Badge value={t.category} />}
                      {t.urgency && <Badge value={t.urgency} />}
                      <Badge value={t.status} />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
        </div>
        {ticket ? (
          <TicketDetail
            key={ticket.id}
            ticket={ticket}
            customer={ticket.customer_id ? customerById.get(ticket.customer_id) : undefined}
            editable={editable}
            onChange={() => void tickets.reload()}
          />
        ) : (
          <Card>
            <Empty>Create a ticket to get started.</Empty>
          </Card>
        )}
      </div>
    </>
  );
}
