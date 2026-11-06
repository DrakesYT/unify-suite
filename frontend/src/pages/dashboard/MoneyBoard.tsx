import type { ReactNode } from "react";
import { Link } from "react-router";
import { Badge } from "../../components/ui";
import { CartIcon, TruckIcon, WalletIcon } from "../../components/icons";
import { compactMoney, money } from "../../format";
import type { Money, Overview } from "../../types";
import { Panel, Stat } from "./parts";

function sumText(values: Money[], empty = "—"): string {
  return values.length
    ? values.map((v) => compactMoney(v.amount_minor, v.currency)).join(" + ")
    : empty;
}

function Row({
  to,
  icon,
  title,
  detail,
  right,
}: {
  to: string;
  icon: ReactNode;
  title: string;
  detail: string;
  right: ReactNode;
}) {
  return (
    <li>
      <Link
        to={to}
        className="-mx-2 flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-white/[0.03]"
      >
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-white/5 text-slate-400">
          {icon}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm text-slate-100">{title}</span>
          <span className="block truncate text-xs text-slate-500">{detail}</span>
        </span>
        <span className="flex shrink-0 items-center gap-2">{right}</span>
      </Link>
    </li>
  );
}

/** Supplier invoices, customer payments and supplier deliveries: where money and goods are stuck. */
export function MoneyBoard({ data }: { data: Overview["money"] }) {
  const attention = data.late_deliveries.length + data.overdue.length;
  return (
    <Panel title="Payments & orders" icon={<WalletIcon size={17} />} to="/payments">
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
        <Stat
          label="Supplier invoices"
          value={sumText(data.unpaid_invoices, compactMoney(0, "USD"))}
          hint={`${data.invoices_to_review} to review · ${data.invoices_to_pay} to pay`}
        />
        <Stat
          label="Customer payments"
          value={data.receivables_overdue ? sumText(data.overdue_amount) : "None overdue"}
          tone={data.receivables_overdue ? "text-rose-300" : "text-emerald-300"}
          hint={`${data.receivables_overdue} overdue · ${data.receivables_on_hold} on hold · ${data.receivables_open} open`}
        />
        <Stat
          label="Supplier deliveries"
          value={`${data.deliveries_open} in transit`}
          tone={data.late_deliveries.length ? "text-amber-300" : "text-white"}
          hint={data.late_deliveries.length ? `${data.late_deliveries.length} late` : "all on time"}
        />
      </div>
      {attention > 0 && (
        <>
          <p className="mt-4 mb-1 text-[11px] text-slate-500">Needs attention</p>
          <ul className="divide-y divide-white/5">
            {data.late_deliveries.map((d) => (
              <Row
                key={d.po_number}
                to={`/procurement#po-${d.po_number}`}
                icon={<TruckIcon size={15} />}
                title={`${d.po_number} · ${d.vendor_name}`}
                detail="supplier delivery past its expected date"
                right={
                  <span className="text-xs font-medium text-red-300">{d.days_late} d late</span>
                }
              />
            ))}
            {data.overdue.map((r) => (
              <Row
                key={r.order_number}
                to={`/payments#order-${r.order_number}`}
                icon={<CartIcon size={15} />}
                title={`${r.order_number} · ${r.customer_name}`}
                detail={`${money(r.amount_minor, r.currency)} unpaid`}
                right={
                  <span className="text-xs font-medium text-red-300">
                    {r.days_overdue} d overdue
                  </span>
                }
              />
            ))}
          </ul>
        </>
      )}
      <p className="mt-4 mb-1 text-[11px] text-slate-500">Latest supplier invoices</p>
      <ul className="divide-y divide-white/5">
        {data.recent_invoices.map((inv) => (
          <Row
            key={inv.invoice_id}
            to="/payments"
            icon={<WalletIcon size={15} />}
            title={`${inv.number} · ${inv.vendor_name}`}
            detail={money(inv.amount_minor, inv.currency)}
            right={
              <>
                {inv.match_status && <Badge value={inv.match_status} />}
                <Badge value={inv.status} />
              </>
            }
          />
        ))}
        {data.recent_invoices.length === 0 && (
          <li className="py-3 text-sm text-slate-500">No supplier invoices yet.</li>
        )}
      </ul>
    </Panel>
  );
}
