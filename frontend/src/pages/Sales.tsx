import { useState, type FormEvent } from "react";
import { ChartIcon, ListIcon, PlusIcon } from "../components/icons";
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
import { EmailPanel } from "../components/EmailPanel";
import { label, money, when } from "../format";
import { canWrite, useAuth } from "../session";
import type { Lead, LeadStatus, Page, Priority, SalesSummary } from "../types";
import { SalesInsights } from "../components/SalesInsights";
import { usePoll } from "../usePoll";
import { WhyButton } from "../components/WhyDrawer";
import { CallsPanel } from "../components/CallsPanel";
import { toast } from "../toast";

const STATUSES: LeadStatus[] = ["new", "contacted", "qualified", "won", "lost"];
const PRIORITIES: Priority[] = ["low", "medium", "high"];
const EMPTY = {
  name: "",
  company: "",
  email: "",
  value: "",
  priority: "medium" as Priority,
  notes: "",
};

function NewLead({ onCreated }: { onCreated: () => void }) {
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (key: keyof typeof EMPTY) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api<Lead>("/sales/leads", {
        method: "POST",
        body: JSON.stringify({
          name: form.name,
          company: form.company,
          email: form.email,
          priority: form.priority,
          value_minor: Math.round(Number(form.value || 0) * 100),
          currency: "USD",
          notes: form.notes,
        }),
      });
      toast(`Lead added: ${form.company}`);
      setForm(EMPTY);
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the lead");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="New lead" icon={<PlusIcon size={16} />}>
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-3">
        <input
          className={inputClass}
          placeholder="Contact name"
          value={form.name}
          onChange={set("name")}
          required
        />
        <input
          className={inputClass}
          placeholder="Company"
          value={form.company}
          onChange={set("company")}
          required
        />
        <input
          className={inputClass}
          type="email"
          placeholder="Email"
          value={form.email}
          onChange={set("email")}
          required
        />
        <input
          className={inputClass}
          type="number"
          min="0"
          step="0.01"
          placeholder="Estimated value (USD)"
          value={form.value}
          onChange={set("value")}
        />
        <select className={inputClass} value={form.priority} onChange={set("priority")}>
          {PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {label(p)} priority
            </option>
          ))}
        </select>
        <button type="submit" disabled={busy} className={primaryButton}>
          {busy ? "Saving…" : "Add lead"}
        </button>
        <textarea
          className={`${inputClass} md:col-span-3`}
          rows={2}
          maxLength={4000}
          placeholder="Notes: need, budget, timeline, who decides…"
          value={form.notes}
          onChange={set("notes")}
        />
      </form>
      <div className="mt-3">
        <ErrorNote message={error} />
      </div>
    </Card>
  );
}

function LeadRow({
  lead,
  editable,
  onChange,
}: {
  lead: Lead;
  editable: boolean;
  onChange: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [callsOpen, setCallsOpen] = useState(false);

  const run = async (path: string, init: RequestInit) => {
    setBusy(true);
    setError(null);
    try {
      const updated = await api<Lead>(path, init);
      toast(`${updated.company} rated ${updated.rating ?? "(no rating)"}`);
      setOpen(true);
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <tr id={`lead-${lead.id}`} className="align-top">
        <td className="py-3 pr-4">
          <div className="text-slate-100">{lead.company}</div>
          <div className="text-xs text-slate-500">
            {lead.name} · {lead.email}
          </div>
        </td>
        <td className="py-3 pr-4 whitespace-nowrap text-slate-300">
          {money(lead.value_minor, lead.currency)}
        </td>
        <td className="py-3 pr-4">
          {editable ? (
            <select
              className="rounded-md border border-navy-800 bg-navy-950 px-2 py-1 text-xs"
              value={lead.status}
              disabled={busy}
              onChange={(e) =>
                run(`/sales/leads/${lead.id}`, {
                  method: "PATCH",
                  body: JSON.stringify({ status: e.target.value }),
                })
              }
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {label(s)}
                </option>
              ))}
            </select>
          ) : (
            <Badge value={lead.status} />
          )}
        </td>
        <td className="py-3 pr-4 text-xs text-slate-400">{label(lead.priority)}</td>
        <td className="py-3 pr-4">
          {lead.rating ? (
            <span className="flex flex-wrap items-center gap-1.5">
              <button onClick={() => setOpen(!open)} title="Show the reason">
                <Badge value={lead.rating} />
              </button>
              {lead.qualification && <WhyButton path={`lead/${lead.id}`} />}
            </span>
          ) : (
            <span className="text-xs text-slate-600">not rated</span>
          )}
        </td>
        <td className="py-3 text-right whitespace-nowrap">
          <button
            onClick={() => setCallsOpen(!callsOpen)}
            className={`${ghostButton} mr-2`}
            aria-expanded={callsOpen}
          >
            Calls
          </button>
          {editable && (
            <button
              disabled={busy}
              onClick={() => run(`/sales/leads/${lead.id}/qualify`, { method: "POST" })}
              className={ghostButton}
            >
              {busy ? "Thinking…" : lead.rating ? "Re-qualify" : "Qualify with AI"}
            </button>
          )}
        </td>
      </tr>
      {(error || callsOpen || (open && lead.qualification)) && (
        <tr>
          <td colSpan={6} className="pb-3">
            <ErrorNote message={error} />
            {open && lead.qualification && (
              <div className="anim-rise rounded-lg bg-navy-950/70 p-3 text-sm">
                <p className="text-slate-200">{lead.qualification.reason}</p>
                <p className="mt-2 text-xs text-slate-500">
                  Based on: {lead.qualification.cited_fields.map(label).join(", ")} ·{" "}
                  {lead.qualification.model} · {when(lead.qualification.qualified_at)}
                </p>
              </div>
            )}
            {open && lead.qualification && (
              <EmailPanel
                title="Outreach email"
                intro="The Outreach Writer drafts a first email from the qualification. Nothing is sent until a sales manager approves it."
                listPath={`/sales/leads/${lead.id}/emails`}
                emailsPath="/sales/emails"
                managerLabel="a sales manager"
                editable={editable}
              />
            )}
            {callsOpen && <CallsPanel leadId={lead.id} editable={editable} />}
          </td>
        </tr>
      )}
    </>
  );
}

export function Sales() {
  const { user } = useAuth();
  const [rating, setRating] = useState("");
  const { data, error, reload } = usePoll<Page<Lead>>(
    `/sales/leads?limit=100${rating ? `&rating=${rating}` : ""}`,
  );
  const summary = usePoll<SalesSummary>("/sales/summary");
  const editable = Boolean(user && canWrite(user, "sales"));

  return (
    <>
      <PageHeader
        eyebrow="Sales · Lead Qualifier agent"
        icon={<ChartIcon size={22} />}
        live
        title="Sales leads"
        subtitle="The Lead Qualifier rates each lead hot, warm or cold and explains why."
      />
      {summary.data && <SalesInsights summary={summary.data} onTargetChanged={summary.reload} />}
      <div className="space-y-6">
        {editable && <NewLead onCreated={reload} />}
        <Card
          title="Pipeline"
          icon={<ListIcon size={16} />}
          actions={
            <select
              className="rounded-md border border-navy-800 bg-navy-950 px-2 py-1 text-sm"
              value={rating}
              onChange={(e) => setRating(e.target.value)}
            >
              <option value="">All ratings</option>
              <option value="hot">Hot</option>
              <option value="warm">Warm</option>
              <option value="cold">Cold</option>
            </select>
          }
        >
          <ErrorNote message={error} />
          {!data && !error && <Loading rows={5} />}
          {data?.items.length === 0 && (
            <Empty hint="Add one above. The Lead Qualifier can then rate it hot, warm or cold.">
              No leads yet.
            </Empty>
          )}
          {data && data.items.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-slate-500">
                  <tr>
                    <th className="py-2 pr-4">Company</th>
                    <th className="py-2 pr-4">Value</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2 pr-4">Priority</th>
                    <th className="py-2 pr-4">Rating</th>
                    <th className="py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-navy-800">
                  {data.items.map((lead) => (
                    <LeadRow key={lead.id} lead={lead} editable={editable} onChange={reload} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
