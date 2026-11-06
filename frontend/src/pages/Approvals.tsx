import { useState } from "react";
import { Link } from "react-router";
import { api } from "../api";
import { useAuth } from "../session";
import {
  Badge,
  Card,
  Empty,
  ErrorNote,
  InjectionWarning,
  PageHeader,
  dangerButton,
  inputClass,
  primaryButton,
  Loading,
} from "../components/ui";
import { label, money, when } from "../format";
import type { Approval, Page, User } from "../types";
import { usePoll } from "../usePoll";
import { toast } from "../toast";
import { approvalHeadline } from "../approvalText";

function mayDecide(user: User, a: Approval): boolean {
  if (a.requested_by_id === user.id) return false;
  return (
    user.role === "admin" || (user.role === a.required_role && user.department === a.department)
  );
}

function ApprovalCard({ approval, onDone }: { approval: Approval; onDone: () => void }) {
  const { user } = useAuth();
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const p = approval.payload;
  const isPayment = approval.action === "pay_invoice";
  const isOrder = approval.action === "approve_po";
  const isEmail = approval.action === "send_email";

  const decide = async (verb: "approve" | "reject") => {
    setBusy(true);
    setError(null);
    try {
      await api(`/approvals/${approval.id}/${verb}`, {
        method: "POST",
        body: JSON.stringify({ comment: comment || null }),
      });
      toast(
        `${verb === "approve" ? "Approved" : "Rejected"}: ${approvalHeadline(approval).title}`,
        verb === "approve" ? "success" : "info",
      );
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the decision");
      setBusy(false);
    }
  };

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs text-slate-500 uppercase">
            {label(approval.action)} · {approval.department} {approval.required_role}
          </p>
          {isPayment ? (
            <>
              <p className="mt-1 text-lg font-semibold text-white">
                {money(p.amount_minor, p.currency)}
              </p>
              <p className="text-sm text-slate-300">
                {p.vendor_name} · invoice {p.invoice_number} · {p.po_number}
              </p>
            </>
          ) : isOrder ? (
            <>
              <p className="mt-1 text-lg font-semibold text-white">
                {money(p.amount_minor, p.currency)}
              </p>
              <p className="text-sm text-slate-300">
                {p.po_number} · {p.vendor_name}
                {p.item ? ` · ${p.quantity} × ${p.item}` : ""}
                {p.budget_minor != null ? ` · budget ${money(p.budget_minor, p.currency)}` : ""}
              </p>
            </>
          ) : isEmail ? (
            <>
              <p className="mt-1 text-lg font-semibold text-white">{p.subject}</p>
              <p className="text-sm text-slate-300">
                Email to {p.company ?? "a lead"} · {p.to}
              </p>
            </>
          ) : (
            <>
              <p className="mt-1 text-lg font-semibold text-white">{p.title}</p>
              <p className="text-sm text-slate-300">{p.customer_name ?? "No customer linked"}</p>
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          {p.match_status && <Badge value={p.match_status} />}
          {p.over_budget && <Badge value="over_budget" />}
          {p.category && <Badge value={p.category} />}
          {p.urgency && <Badge value={p.urgency} />}
          <Badge value={approval.status} />
        </div>
      </div>
      {isEmail && p.body && (
        <p className="mt-4 rounded-lg bg-navy-950/70 p-3 text-sm whitespace-pre-wrap text-slate-300">
          {p.body}
        </p>
      )}
      {!isPayment && !isOrder && (p.likely_cause || p.note) && (
        <div className="mt-4 space-y-1 rounded-lg bg-navy-950/70 p-3 text-sm">
          {p.likely_cause && (
            <p className="text-slate-200">
              <span className="text-slate-500">Likely cause: </span>
              {p.likely_cause}
            </p>
          )}
          {p.note && (
            <p className="text-slate-300">
              <span className="text-slate-500">Note: </span>
              {p.note}
            </p>
          )}
        </div>
      )}
      {p.discrepancies && p.discrepancies.length > 0 && (
        <div className="mt-4 rounded-lg bg-amber-500/10 p-3">
          <p className="text-xs font-semibold text-amber-200 uppercase">Discrepancies</p>
          <ul className="mt-1 list-disc pl-5 text-sm text-amber-100">
            {p.discrepancies.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </div>
      )}
      <InjectionWarning lines={p.suspicious_text} />
      <p className="mt-3 text-xs text-slate-500">
        Requested {when(approval.created_at)}
        {approval.execution_id && (
          <>
            {" · "}
            <Link
              to={`/payments/${approval.execution_id}`}
              className="underline hover:text-slate-300"
            >
              view run
            </Link>
          </>
        )}
        {approval.decided_at && ` · decided ${when(approval.decided_at)}`}
        {approval.comment && ` · “${approval.comment}”`}
      </p>
      {approval.status === "pending" && user && mayDecide(user, approval) && (
        <div className="mt-4 space-y-3">
          <input
            className={inputClass}
            placeholder="Comment (required to reject)"
            value={comment}
            maxLength={1000}
            onChange={(e) => setComment(e.target.value)}
          />
          <ErrorNote message={error} />
          <div className="flex gap-2">
            <button disabled={busy} onClick={() => decide("approve")} className={primaryButton}>
              {isPayment
                ? "Approve payment"
                : isOrder
                  ? "Approve order"
                  : isEmail
                    ? "Approve & send"
                    : "Approve"}
            </button>
            <button
              disabled={busy || !comment.trim()}
              onClick={() => decide("reject")}
              className={dangerButton}
            >
              Reject
            </button>
          </div>
        </div>
      )}
      {approval.status === "pending" && user && approval.requested_by_id === user.id && (
        <p className="mt-3 text-xs text-slate-500">
          You started this request, so another manager must decide.
        </p>
      )}
    </Card>
  );
}

export function Approvals() {
  const [tab, setTab] = useState<"pending" | "approved" | "rejected">("pending");
  const { data, error, reload } = usePoll<Page<Approval>>(`/approvals?status=${tab}`);

  return (
    <>
      <PageHeader
        title="Approval Center"
        subtitle="Payments and other sensitive actions wait here for a human decision."
      />
      <div className="mb-4 flex gap-2">
        {(["pending", "approved", "rejected"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-full px-3 py-1 text-sm ${tab === t ? "bg-accent-purple/25 text-white" : "text-slate-400 hover:text-white"}`}
          >
            {label(t)}
          </button>
        ))}
      </div>
      <ErrorNote message={error} />
      <div className="space-y-4" data-tour="approvals">
        {!data && !error && <Loading rows={3} />}
        {data?.items.length === 0 && (
          <Empty
            hint={
              tab === "pending"
                ? "Payments, purchase orders, escalations and emails wait here until a manager decides."
                : undefined
            }
          >
            {tab === "pending" ? "Nothing is waiting for a decision." : `Nothing ${tab} yet.`}
          </Empty>
        )}
        {data?.items.map((a) => (
          <ApprovalCard key={a.id} approval={a} onDone={reload} />
        ))}
      </div>
    </>
  );
}
