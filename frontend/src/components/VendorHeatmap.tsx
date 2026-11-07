import { Card, Empty } from "./ui";
import type { PurchaseOrder, PurchaseRequest } from "../types";

const COLUMNS = [
  { key: "price_score", label: "Price" },
  { key: "lead_time_score", label: "Delivery speed" },
  { key: "delivery_score", label: "On-time record" },
] as const;

type Row = {
  id: string;
  name: string;
  compared: number;
  parts: Record<(typeof COLUMNS)[number]["key"], number>;
  late: number;
  delivered: number;
};

/** Average each vendor's saved comparison scores (0 to 1) and count its late and delivered orders. */
function build(requests: PurchaseRequest[], orders: PurchaseOrder[]): Row[] {
  const byVendor = new Map<string, Row & { sums: number[] }>();
  for (const req of requests) {
    for (const r of req.comparison?.ranking ?? []) {
      const row = byVendor.get(r.vendor_id) ?? {
        id: r.vendor_id,
        name: r.vendor_name,
        compared: 0,
        parts: { price_score: 0, lead_time_score: 0, delivery_score: 0 },
        late: 0,
        delivered: 0,
        sums: [0, 0, 0],
      };
      row.compared += 1;
      COLUMNS.forEach((c, i) => (row.sums[i] += Number(r[c.key])));
      byVendor.set(r.vendor_id, row);
    }
  }
  for (const o of orders) {
    const row = byVendor.get(o.vendor_id);
    if (!row) continue;
    if (o.delivery_status === "late") row.late += 1;
    if (o.delivered_on) row.delivered += 1;
  }
  return [...byVendor.values()]
    .map((row) => {
      COLUMNS.forEach((c, i) => (row.parts[c.key] = row.sums[i] / row.compared));
      return row;
    })
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** Flat purple ramp: the stronger the score, the stronger the fill. */
const fill = (score: number) =>
  `rgb(139 92 246 / ${(0.12 + Math.min(1, Math.max(0, score)) * 0.68).toFixed(2)})`;

/** Vendors by price, delivery speed and on-time record, from the saved vendor comparisons. */
export function VendorHeatmap({
  requests,
  orders,
}: {
  requests: PurchaseRequest[];
  orders: PurchaseOrder[];
}) {
  const rows = build(requests, orders);
  return (
    <Card title="Supplier performance">
      {rows.length === 0 ? (
        <Empty hint="Run “Compare vendors” on a request with two or more quotes.">
          No vendor comparisons yet.
        </Empty>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[540px] border-separate border-spacing-1 text-sm">
              <thead className="text-xs text-slate-500">
                <tr>
                  <th className="px-2 py-1 text-left font-medium">Vendor</th>
                  {COLUMNS.map((c) => (
                    <th key={c.key} className="px-2 py-1 text-center font-medium">
                      {c.label}
                    </th>
                  ))}
                  <th className="px-2 py-1 text-center font-medium">Late now</th>
                  <th className="px-2 py-1 text-center font-medium">Delivered</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <th className="max-w-[12rem] truncate px-2 py-2 text-left font-medium text-slate-200">
                      {row.name}
                      <span className="block text-[11px] font-normal text-slate-500">
                        {row.compared} comparison{row.compared === 1 ? "" : "s"}
                      </span>
                    </th>
                    {COLUMNS.map((c) => (
                      <td
                        key={c.key}
                        className="rounded-md px-2 py-2 text-center font-semibold text-white tabular-nums"
                        style={{ background: fill(row.parts[c.key]) }}
                        title={`${row.name}, ${c.label}: ${(row.parts[c.key] * 100).toFixed(0)} of 100`}
                      >
                        {(row.parts[c.key] * 100).toFixed(0)}
                      </td>
                    ))}
                    <td
                      className={`rounded-md bg-navy-950/60 px-2 py-2 text-center tabular-nums ${
                        row.late > 0 ? "font-semibold text-red-300" : "text-slate-400"
                      }`}
                    >
                      {row.late}
                    </td>
                    <td className="rounded-md bg-navy-950/60 px-2 py-2 text-center text-slate-400 tabular-nums">
                      {row.delivered}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-slate-500">
            Scores are each vendor&apos;s average across the saved comparisons, each relative to the
            best offer (100 is best). Late now counts approved orders past their expected delivery
            date that have not arrived; Delivered counts orders received.
          </p>
        </>
      )}
    </Card>
  );
}
