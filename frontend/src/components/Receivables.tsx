import { useState } from "react";
import { api } from "../api";
import { money } from "../format";
import type { Receivable } from "../types";
import { usePoll } from "../usePoll";
import { EmailPanel } from "./EmailPanel";
import { Badge, Card, Empty, ErrorNote, ghostButton } from "./ui";

const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

function ReceivableRow({
  item,
  editable,
  onChange,
}: {
  item: Receivable;
  editable: boolean;
  onChange: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const markPaid = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/finance/receivables/${item.order_id}/paid`, { method: "POST" });
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update the order");
      setBusy(false);
    }
  };

  return (
    <li className="rounded-lg border border-navy-800 px-3 py-2 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 text-slate-300">
        <span className="font-mono text-xs">{item.order_number}</span>
        <span>{item.customer_company ?? item.customer_name}</span>
        <span>{money(item.amount_minor, item.currency)}</span>
        <span className="flex items-center gap-2 text-xs text-slate-400">
          due {day(item.due_on)}
          <Badge value={item.status} />
          {item.days_overdue > 0 && (
            <span className="font-semibold text-red-300">{item.days_overdue} days</span>
          )}
        </span>
      </div>
      {item.hold_reason && (
        <p className="mt-1 text-xs text-amber-200">
          Not chased while there is an {item.hold_reason}
        </p>
      )}
      {editable && (
        <div className="mt-2 flex flex-wrap gap-2">
          <button disabled={busy} onClick={() => void markPaid()} className={ghostButton}>
            {busy ? "Saving…" : "Mark paid"}
          </button>
          {item.status === "overdue" && (
            <button onClick={() => setOpen(!open)} className={ghostButton}>
              {open ? "Hide reminder" : "Send payment reminder"}
            </button>
          )}
        </div>
      )}
      <ErrorNote message={error} />
      {open && (
        <EmailPanel
          title="Payment reminder"
          intro="The Payment Reminder Writer drafts a polite reminder quoting the order, amount and days overdue. Nothing is sent until a finance manager approves it."
          listPath={`/finance/receivables/${item.order_id}/emails`}
          emailsPath="/finance/emails"
          managerLabel="a finance manager"
          editable={editable}
        />
      )}
    </li>
  );
}

/** Money owed to us: unpaid customer orders, with due dates and holds computed by code. */
export function Receivables({ editable }: { editable: boolean }) {
  const { data, error, reload } = usePoll<Receivable[]>("/finance/receivables");

  return (
    <Card title="Customer payments due">
      <ErrorNote message={error} />
      {data && data.length === 0 && <Empty>No unpaid customer orders.</Empty>}
      <ul className="space-y-2">
        {data?.map((item) => (
          <ReceivableRow
            key={item.order_id}
            item={item}
            editable={editable}
            onChange={() => void reload()}
          />
        ))}
      </ul>
      <p className="mt-3 text-xs text-slate-500">
        Due date = order date + the customer&apos;s payment terms. Customers with an open refund,
        billing or legal ticket are never chased.
      </p>
    </Card>
  );
}
