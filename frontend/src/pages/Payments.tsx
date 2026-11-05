import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { api } from "../api";
import { canWrite, useAuth } from "../session";
import {
  Badge,
  Card,
  Empty,
  ErrorNote,
  PageHeader,
  inputClass,
  primaryButton,
} from "../components/ui";
import { Receivables } from "../components/Receivables";
import { when } from "../format";
import type { Execution, ExecutionSummary, Page } from "../types";
import { usePoll } from "../usePoll";

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
      navigate(`/payments/${run.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start");
      setBusy(false);
    }
  };

  return (
    <Card title="Verify a supplier invoice" tour="upload-invoice">
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
          <span className="text-slate-300">PO number</span>
          <input
            className={inputClass}
            placeholder="PO-1007"
            value={poNumber}
            onChange={(e) => setPoNumber(e.target.value)}
            required
          />
        </label>
        <button type="submit" disabled={busy || !file} className={primaryButton}>
          {busy ? "Starting…" : "Start verification"}
        </button>
      </form>
      <p className="mt-3 text-xs text-slate-500">
        The AI reads the invoice, code matches it to the PO, and a finance manager approves before
        any payment.
      </p>
      <div className="mt-3">
        <ErrorNote message={error} />
      </div>
    </Card>
  );
}

export function Payments() {
  const { user } = useAuth();
  const { data, error } = usePoll<Page<ExecutionSummary>>("/workflows?limit=50");

  return (
    <>
      <PageHeader
        title="Payments"
        subtitle="Supplier invoices (Workflow B: invoice → PO match → manager approval → payment) and customer payments due"
      />
      <div className="space-y-6">
        {user && canWrite(user, "finance") && <StartForm />}
        <Card title="Recent supplier payment runs">
          <ErrorNote message={error} />
          {data && data.items.length === 0 && <Empty>No runs yet.</Empty>}
          {data && data.items.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-slate-500 uppercase">
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
        <Receivables editable={Boolean(user && canWrite(user, "finance"))} />
      </div>
    </>
  );
}
