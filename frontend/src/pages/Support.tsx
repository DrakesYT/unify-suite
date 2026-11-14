import { useState, type FormEvent } from "react";
import { ListIcon, PlusIcon, TicketIcon } from "../components/icons";
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
  Loading,
} from "../components/ui";
import { label, money, when } from "../format";
import { canWrite, useAuth } from "../session";
import type { Approval, Customer, Order, Staff, Ticket } from "../types";
import { usePoll, usePollAll } from "../usePoll";
import { WhyButton } from "../components/WhyDrawer";
import { CallsPanel } from "../components/CallsPanel";
import { EmailPanel } from "../components/EmailPanel";
import { toast } from "../toast";
import { SupportDashboard } from "./support/SupportDashboard";

const RUN_DONE: Record<string, string> = {
  classify: "Ticket classified",
  investigate: "Investigation done: see the likely causes",
  escalate: "Escalated",
  resolve: "Ticket resolved",
  close: "Ticket closed",
  reopen: "Ticket reopened",
};

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
      toast(
        ticket.category
          ? `Ticket saved and classified: ${ticket.category}, ${ticket.urgency}`
          : "Ticket saved",
      );
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

function InsightsPanel({ ticket, customer }: { ticket: Ticket; customer: Customer | undefined }) {
  const inv = ticket.investigation;
  return (
    <aside className="h-fit rounded-lg border border-navy-800 bg-navy-950/60 p-4">
      <h4 className="text-xs font-semibold text-slate-400">AI insights</h4>
      <dl className="mt-3 space-y-3 text-sm">
        <div>
          <dt className="text-xs text-slate-500">Summary</dt>
          <dd className="mt-0.5 text-slate-200">
            {inv
              ? (inv.likely_causes[0]?.cause ?? inv.next_step)
              : "Not investigated yet. Run “Investigate orders” to get one."}
          </dd>
        </div>
        {inv && (
          <div>
            <dt className="text-xs text-slate-500">Next step</dt>
            <dd className="mt-0.5 text-slate-200">{inv.next_step}</dd>
          </div>
        )}
        <div className="flex items-center justify-between">
          <dt className="text-xs text-slate-500">Category</dt>
          <dd>{ticket.category ? <Badge value={ticket.category} /> : "Not set"}</dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="text-xs text-slate-500">Priority</dt>
          <dd>{ticket.urgency ? <Badge value={ticket.urgency} /> : "Not set"}</dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="text-xs text-slate-500">Status</dt>
          <dd>
            <Badge value={ticket.status} />
          </dd>
        </div>
        {customer && (
          <div className="flex items-center justify-between gap-2">
            <dt className="text-xs text-slate-500">Customer</dt>
            <dd className="truncate text-slate-300">{customer.name}</dd>
          </div>
        )}
        {inv && (
          <div className="flex items-center justify-between">
            <dt className="text-xs text-slate-500">Orders checked</dt>
            <dd className="text-slate-300">{inv.order_numbers_used.length}</dd>
          </div>
        )}
      </dl>
      {inv && (
        <p className="mt-3 text-xs text-slate-500">Investigated {when(inv.investigated_at)}</p>
      )}
    </aside>
  );
}

function TicketDetail({
  ticket,
  customer,
  staff,
  editable,
  onChange,
}: {
  ticket: Ticket;
  customer: Customer | undefined;
  staff: Staff[];
  editable: boolean;
  onChange: () => void;
}) {
  const { user } = useAuth();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [approval, setApproval] = useState<Approval | null>(null);
  const [refundOrder, setRefundOrder] = useState("");
  const inv = ticket.investigation;
  const closed = ticket.status === "resolved" || ticket.status === "closed";
  const isRefund = ticket.category === "refund";
  // A refund names the order the money goes back on; approval then marks that order refunded.
  const orders = usePoll<Order[]>(
    isRefund && ticket.customer_id && !closed
      ? `/support/customers/${ticket.customer_id}/orders`
      : null,
  );
  const refundable = (orders.data ?? []).filter((o) => o.status !== "refunded");

  const run = async (what: string, path: string, body?: unknown) => {
    setBusy(what);
    setError(null);
    try {
      const res = await api<{ approval?: Approval | null }>(path, {
        method: "POST",
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (what === "escalate") setApproval(res.approval ?? null);
      toast(RUN_DONE[what] ?? "Done");
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(null);
    }
  };

  const assign = async (assigneeId: string | null) => {
    setBusy("assign");
    setError(null);
    try {
      await api(`/support/tickets/${ticket.id}`, {
        method: "PATCH",
        body: JSON.stringify({ assignee_id: assigneeId }),
      });
      toast(assigneeId ? "Ticket assigned" : "Ticket back in the queue");
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not assign the ticket");
    } finally {
      setBusy(null);
    }
  };

  const main = (
    <>
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
      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-xs text-slate-500">Owner</span>
        {editable ? (
          <select
            className="rounded-md border border-navy-800 bg-navy-950 px-2 py-1 text-xs"
            aria-label="Ticket owner"
            value={ticket.assignee_id ?? ""}
            disabled={!!busy || ticket.status === "closed"}
            onChange={(e) => void assign(e.target.value || null)}
          >
            <option value="">Nobody yet</option>
            {staff.map((s) => (
              <option key={s.id} value={s.id}>
                {s.full_name}
              </option>
            ))}
          </select>
        ) : (
          <span className="text-slate-300">
            {staff.find((s) => s.id === ticket.assignee_id)?.full_name ?? "Nobody yet"}
          </span>
        )}
        {editable &&
          user &&
          ticket.assignee_id !== user.id &&
          staff.some((s) => s.id === user.id) && (
            <button
              disabled={!!busy || ticket.status === "closed"}
              onClick={() => void assign(user.id)}
              className={ghostButton}
            >
              Assign to me
            </button>
          )}
      </div>
      {editable && (
        <div className="mt-3 flex flex-wrap gap-2">
          {!closed && (
            <button
              disabled={!!busy}
              onClick={() => run("resolve", `/support/tickets/${ticket.id}/resolve`, {})}
              className={primaryButton}
            >
              {busy === "resolve" ? "Saving…" : "Mark resolved"}
            </button>
          )}
          {ticket.status !== "closed" && (
            <button
              disabled={!!busy}
              onClick={() => run("close", `/support/tickets/${ticket.id}/close`, {})}
              className={ghostButton}
              title="Nothing more to do: file it away"
            >
              {busy === "close" ? "Saving…" : "Close"}
            </button>
          )}
          {closed && (
            <button
              disabled={!!busy}
              onClick={() => run("reopen", `/support/tickets/${ticket.id}/reopen`, {})}
              className={ghostButton}
            >
              {busy === "reopen" ? "Saving…" : "Reopen"}
            </button>
          )}
        </div>
      )}
      <ErrorNote message={error} />

      {inv && (
        <div className="mt-5 space-y-3">
          <h4 className="text-xs font-semibold text-slate-400">Likely causes</h4>
          <ul className="space-y-2">
            {inv.likely_causes.map((c) => (
              <li key={c.cause} className="rounded-lg bg-navy-950/70 p-3 text-sm text-slate-200">
                {c.cause}
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {c.order_numbers.map((n) => (
                    <span
                      key={n}
                      className="rounded bg-navy-800 px-1.5 py-0.5 font-mono text-xs text-accent-soft"
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
            <h4 className="text-xs font-semibold text-slate-400">Draft reply (not sent)</h4>
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
          {isRefund && refundable.length > 0 && (
            <select
              className={inputClass}
              value={refundOrder}
              aria-label="Order to refund"
              onChange={(e) => setRefundOrder(e.target.value)}
            >
              <option value="">Order to refund (none named)</option>
              {refundable.map((o) => (
                <option key={o.id} value={o.order_number}>
                  {o.order_number} · {money(o.amount_minor, o.currency)} · {label(o.status)}
                </option>
              ))}
            </select>
          )}
          <button
            disabled={!!busy}
            onClick={() =>
              run("escalate", `/support/tickets/${ticket.id}/escalate`, {
                note,
                order_number: isRefund && refundOrder ? refundOrder : null,
              })
            }
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
      {ticket.status !== "closed" && (
        <EmailPanel
          title="Reply to the customer"
          intro="Start a reply from the investigation's draft, edit it, and send it for approval. Nothing goes to the customer until a support manager approves it."
          listPath={`/support/tickets/${ticket.id}/emails`}
          emailsPath="/support/emails"
          managerLabel="a support manager"
          editable={editable}
          draftLabel="Write a reply"
        />
      )}
      <CallsPanel ticketId={ticket.id} editable={editable} />
    </>
  );

  return (
    <Card title="Ticket" icon={<TicketIcon size={16} />}>
      <div className="@container">
        <div className="grid gap-5 @3xl:grid-cols-[1fr_250px]">
          <div className="min-w-0">{main}</div>
          <InsightsPanel ticket={ticket} customer={customer} />
        </div>
      </div>
    </Card>
  );
}

const TICKET_HASH = "#ticket-";

export function Support() {
  const { user } = useAuth();
  const editable = Boolean(user && canWrite(user, "support"));
  const tickets = usePollAll<Ticket>("/support/tickets");
  const customers = usePoll<Customer[]>("/support/customers");
  const staff = usePoll<Staff[]>("/support/staff");
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
        eyebrow="Support · Ticket Investigator agent"
        icon={<TicketIcon size={22} />}
        live
        title="Support tickets"
        subtitle="The Ticket Investigator classifies each ticket and checks the customer's orders. Refunds and legal escalations need a manager."
      />
      <SupportDashboard tickets={tickets.data?.items ?? []} />
      <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
        <div className="min-w-0 space-y-6">
          {editable && (
            <Card title="New ticket" icon={<PlusIcon size={16} />}>
              <NewTicket
                customers={customers.data ?? []}
                onCreated={(t) => (setPicked(t.id), void tickets.reload())}
              />
            </Card>
          )}
          <Card title="Queue" icon={<ListIcon size={16} />}>
            <ErrorNote message={tickets.error} />
            {!tickets.data && !tickets.error && <Loading rows={4} />}
            {tickets.data?.items.length === 0 && <Empty>No tickets yet.</Empty>}
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
            staff={staff.data ?? []}
            editable={editable}
            onChange={() => void tickets.reload()}
          />
        ) : (
          <Card>
            {tickets.data ? (
              <Empty hint="The AI classifies each new ticket and can investigate the customer's orders.">
                Create a ticket to get started.
              </Empty>
            ) : (
              <Loading rows={5} />
            )}
          </Card>
        )}
      </div>
    </>
  );
}
