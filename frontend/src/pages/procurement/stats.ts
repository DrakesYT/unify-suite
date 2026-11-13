import { compactMoney, majorUnits } from "../../format";
import { largest, monthKey, monthLabel, sumByCurrency } from "../../components/charts/currency";
import type { PurchaseOrder, PurchaseRequest } from "../../types";

const approvedOrders = (orders: PurchaseOrder[]) => orders.filter((o) => o.status === "approved");

export const spendTotals = (orders: PurchaseOrder[]) =>
  sumByCurrency(approvedOrders(orders), (o) => ({
    amount_minor: o.amount_minor,
    currency: o.currency,
  }));

export const pendingOrders = (orders: PurchaseOrder[]) =>
  orders.filter((o) => o.status === "pending_approval").length;

/**
 * Per compared request: average quote total minus the chosen vendor's total (or the cheapest when
 * none is chosen yet). Needs two or more quotes in one currency; summed per currency.
 */
export function rankingSavings(requests: PurchaseRequest[]): Map<string, number> {
  const totals = new Map<string, number>();
  for (const req of requests) {
    const ranking = req.comparison?.ranking ?? [];
    if (ranking.length < 2) continue;
    const currency = ranking[0].currency;
    const same = ranking.filter((r) => r.currency === currency);
    if (same.length < 2) continue;
    const average = same.reduce((sum, r) => sum + r.total_minor, 0) / same.length;
    const picked =
      same.find((r) => r.vendor_id === req.chosen_vendor_id)?.total_minor ??
      Math.min(...same.map((r) => r.total_minor));
    totals.set(currency, (totals.get(currency) ?? 0) + Math.max(0, Math.round(average - picked)));
  }
  return totals;
}

/**
 * Orders that arrived on time, as a percent of every order whose date has passed: the delivered
 * ones plus the ones that are late right now (an order still on its way and not yet due says
 * nothing either way). Null when no order has reached its date.
 */
export function onTimePercent(orders: PurchaseOrder[]): number | null {
  const delivered = orders.filter((o) => o.delivered_on);
  const lateNow = orders.filter((o) => !o.delivered_on && o.delivery_status === "late");
  const due = delivered.length + lateNow.length;
  if (due === 0) return null;
  return (delivered.filter((o) => o.days_late <= 0).length / due) * 100;
}

/** Approved orders as a share of decided (approved + rejected) ones. */
export function approvalPercent(orders: PurchaseOrder[]): number | null {
  const approved = orders.filter((o) => o.status === "approved").length;
  const rejected = orders.filter((o) => o.status === "rejected").length;
  return approved + rejected === 0 ? null : (approved / (approved + rejected)) * 100;
}

/** Approved spend per month in the largest currency (last 6 months with orders). */
export function monthlySpend(orders: PurchaseOrder[]) {
  const top = largest(spendTotals(orders));
  if (!top) return { points: [], currency: null as string | null };
  const byMonth = new Map<string, number>();
  for (const o of approvedOrders(orders)) {
    if (o.currency !== top.currency) continue;
    const key = monthKey(o.ordered_on ?? o.created_at);
    byMonth.set(key, (byMonth.get(key) ?? 0) + o.amount_minor);
  }
  const points = [...byMonth]
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-6)
    .map(([key, minor]) => ({ label: monthLabel(key), value: majorUnits(minor, top.currency) }));
  return { points, currency: top.currency };
}

/** Approved spend by vendor: the top five, the rest folded into "Other" (largest currency). */
export function topVendors(orders: PurchaseOrder[], names: Map<string, string>) {
  const top = largest(spendTotals(orders));
  if (!top) return [];
  const byVendor = new Map<string, number>();
  for (const o of approvedOrders(orders)) {
    if (o.currency === top.currency)
      byVendor.set(o.vendor_id, (byVendor.get(o.vendor_id) ?? 0) + o.amount_minor);
  }
  const sorted = [...byVendor].sort(([, a], [, b]) => b - a);
  const rows = sorted.slice(0, 5).map(([id, value]) => ({
    label: names.get(id) ?? "Unknown vendor",
    value,
  }));
  const rest = sorted.slice(5).reduce((sum, [, v]) => sum + v, 0);
  if (rest > 0) rows.push({ label: "Other", value: rest });
  return rows.map((r) => ({ ...r, display: compactMoney(r.value, top.currency) }));
}
