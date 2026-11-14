import { useState, type FormEvent } from "react";
import { FileIcon, ListIcon, WalletIcon } from "../components/icons";
import { Link, useNavigate } from "react-router";
import { api } from "../api";
import { canWrite, useAuth } from "../session";
import {
  Badge,
  Card,
  Empty,
  ErrorNote,
  PageHeader,
  dangerButton,
  inputClass,
  primaryButton,
  Loading,
} from "../components/ui";
import { Receivables } from "../components/Receivables";
import { PaymentsDashboard } from "./payments/PaymentsDashboard";
import { money, when } from "../format";
import type { Execution, ExecutionSummary, Invoice } from "../types";
import { usePollAll } from "../usePoll";
import { toast } from "../toast";

function StartForm() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [poNumber, setPoNumber] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    const body = new FormData();
    body.append("file", file);
    body.append("po_number", poNumber);
    try {
      const run = await api<Execution>("/workflows/supplier-payment/start", {
        method: "POST",
        body,
      });
      toast("Invoice uploaded. The agents are checking it now.", "info");
      navigate(`/payments/${run.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start");
      setBusy(false);
    }
  };

  return (
    <Card title="Verify a supplier invoice" icon={<FileIcon size={16} />} tour="upload-invoice">
      <form onSubmit={submit} className="grid gap-4 md:grid-cols-[1fr_200px_auto] md:items-end">
        <label className="space-y-1 text-sm">
          <span className="text-slate-300">Invoice (PDF or TXT, max 10 MB)</span>
          <input
            type="file"
            accept=".pdf,.txt"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className={`${inputClass} file:mr-3 file:rounded-md file:border-0 file:bg-navy-800 file:px-3 file:py-1 file:text-slate-200`}
            required
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-slate-300">PO number (optional)</span>
          <input
            className={inputClass}
            placeholder="Read from the invoice"
            value={poNumber}
            onChange={(e) => setPoNumber(e.target.value)}
          />
        </label>
        <button type="submit" disabled={busy || !file} className={primaryButton}>
          {busy ? "Starting…" : "Start verification"}
        </button>
      </form>
      <p className="mt-3 text-xs text-slate-500">
        The AI reads the invoice, code matches it to the PO, and a finance manager approves before
        any payment. Leave the PO number empty to use the one printed on the invoice.
      </p>
      <div className="mt-3">
        <ErrorNote message={error} />
      </div>
    </Card>
  );
}

/** Invoices code could not match (no PO, a mismatch outside a payment run). A finance manager
 *  settles the ones that will not be paid, so the review list and the unpaid total stay true. */
function InvoicesToReview({ canDecide }: { canDecide: boolean }) {
  const { data, error, reload } = usePollAll<Invoice>("/finance/invoices?status=needs_review");
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  if (!data || data.items.length === 0) return <ErrorNote message={error} />;

  const reject = async (invoice: Invoice) => {
    setBusy(invoice.id);
    setFailed(null);
    try {
      await api(`/finance/invoices/${invoice.id}/reject`, {
        method: "POST",
        body: JSON.stringify({ reason: reasons[invoice.id] ?? "" }),
      });
      toast(`Invoice ${invoice.number} rejected`, "info");
      void reload();
    } catch (err) {
      setFailed(err instanceof Error ? err.message : "Could not reject the invoice");
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card title="Invoices that need a human check" icon={<FileIcon size={16} />}>
      <p className="mb-3 text-xs text-slate-500">
        An invoice whose payment is waiting for approval is decided in the Approval Center. The
        others stay here until a finance manager rejects them.
      </p>
      <ErrorNote message={error ?? failed} />
      <ul className="divide-y divide-navy-800">
        {data.items.map((invoice) => (
          <li key={invoice.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
            <span className="min-w-0 flex-1">
              <span className="text-slate-100">{invoice.number}</span>{" "}
              <span className="text-slate-400">
                · {money(invoice.amount_minor, invoice.currency)} · {invoice.po_number ?? "no PO"} ·{" "}
                {when(invoice.created_at)}
              </span>
            </span>
            {invoice.match_status && <Badge value={invoice.match_status} />}
            {canDecide && (
              <>
                <input
                  className={`${inputClass} max-w-56`}
                  placeholder="Reason (required)"
                  aria-label={`Reason for rejecting ${invoice.number}`}
                  maxLength={500}
                  value={reasons[invoice.id] ?? ""}
                  onChange={(e) => setReasons({ ...reasons, [invoice.id]: e.target.value })}
                />
                <button
                  disabled={busy === invoice.id || (reasons[invoice.id] ?? "").trim().length < 3}
                  onClick={() => void reject(invoice)}
                  className={dangerButton}
                >
                  {busy === invoice.id ? "Saving…" : "Reject"}
                </button>
              </>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function Payments() {
  const { user } = useAuth();
  const { data, error } = usePollAll<ExecutionSummary>("/workflows");

  return (
    <>
      <PageHeader
        eyebrow="Finance · Invoice Processor agent"
        icon={<WalletIcon size={22} />}
        live
        title="Payments"
        subtitle="Supplier invoices (Workflow B: invoice → PO match → manager approval → payment) and customer payments due"
      />
      <div className="space-y-6">
        <PaymentsDashboard />
        {user && canWrite(user, "finance") && <StartForm />}
        <Card title="Recent supplier payment runs" icon={<ListIcon size={16} />}>
          <ErrorNote message={error} />
          {!data && !error && <Loading rows={4} />}
          {data && data.items.length === 0 && (
            <Empty hint="Upload a supplier invoice above to start one.">No payment runs yet.</Empty>
          )}
          {data && data.items.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-slate-500">
                  <tr>
                    <th className="py-2 pr-4">Started</th>
                    <th className="py-2 pr-4">Invoice file</th>
                    <th className="py-2 pr-4">PO</th>
                    <th className="py-2">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-navy-800">
                  {data.items.map((run) => (
                    <tr key={run.id} className="hover:bg-navy-800/40">
                      <td className="py-2.5 pr-4 whitespace-nowrap text-slate-400">
                        <Link to={`/payments/${run.id}`} className="hover:text-white">
                          {when(run.created_at)}
                        </Link>
                      </td>
                      <td className="py-2.5 pr-4">
                        <Link
                          to={`/payments/${run.id}`}
                          className="text-slate-200 hover:text-white"
                        >
                          {run.input.file_name}
                        </Link>
                      </td>
                      <td className="py-2.5 pr-4 text-slate-300">{run.input.po_number}</td>
                      <td className="py-2.5">
                        <Badge value={run.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <InvoicesToReview
          canDecide={Boolean(user && canWrite(user, "finance") && user.role !== "employee")}
        />
        <Receivables editable={Boolean(user && canWrite(user, "finance"))} />
      </div>
    </>
  );
}
