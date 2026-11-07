import { compactMoney, majorUnits } from "../../format";
import { largest, monthKey, monthLabel, sumByCurrency } from "../../components/charts/currency";
import type { Anomaly, Invoice, Receivable } from "../../types";

export const outstanding = (r: Receivable[]) =>
  sumByCurrency(r, (x) => ({ amount_minor: x.amount_minor, currency: x.currency }));

export const overdueTotals = (r: Receivable[]) =>
  sumByCurrency(r, (x) =>
    x.status === "overdue" ? { amount_minor: x.amount_minor, currency: x.currency } : null,
  );

/** Share of invoices with a PO decision that matched, 0-100, or null with none. */
export function matchedPercent(invoices: Invoice[]): number | null {
  const judged = invoices.filter((i) => i.match_status !== null);
  if (judged.length === 0) return null;
  return (judged.filter((i) => i.match_status === "matched").length / judged.length) * 100;
}

export function matchSlices(invoices: Invoice[]) {
  const counts = new Map<string, number>();
  for (const i of invoices) {
    const key = i.match_status ?? "unchecked";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts].map(([key, value]) => ({ key, value }));
}

const BUCKETS = [
  { label: "1-30 days", min: 1, max: 30 },
  { label: "31-60 days", min: 31, max: 60 },
  { label: "61-90 days", min: 61, max: 90 },
  { label: "90+ days", min: 91, max: Infinity },
];

/** Overdue receivables by age, amounts in the largest currency only. */
export function agingBuckets(receivables: Receivable[]) {
  const overdue = receivables.filter((r) => r.status === "overdue" && r.days_overdue > 0);
  const top = largest(outstanding(overdue));
  return BUCKETS.map((b) => {
    const total = overdue
      .filter(
        (r) => r.currency === top?.currency && r.days_overdue >= b.min && r.days_overdue <= b.max,
      )
      .reduce((sum, r) => sum + r.amount_minor, 0);
    return { label: b.label, value: total, display: top ? compactMoney(total, top.currency) : "" };
  });
}

/** Invoiced amount per month (last 6 months with data), in the largest currency. */
export function monthlyInvoiced(invoices: Invoice[]) {
  const top = largest(
    sumByCurrency(invoices, (i) => ({ amount_minor: i.amount_minor, currency: i.currency })),
  );
  if (!top) return { points: [], currency: null as string | null };
  const byMonth = new Map<string, number>();
  for (const i of invoices) {
    if (i.currency !== top.currency) continue;
    const key = monthKey(i.invoice_date);
    byMonth.set(key, (byMonth.get(key) ?? 0) + i.amount_minor);
  }
  const points = [...byMonth]
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-6)
    .map(([key, minor]) => ({ label: monthLabel(key), value: majorUnits(minor, top.currency) }));
  return { points, currency: top.currency };
}

export const anomalyCount = (a: Anomaly[]) => a.length;
