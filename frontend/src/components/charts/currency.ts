import { compactMoney } from "../../format";

/** Sum minor units per currency; different currencies are never added together. */
export function sumByCurrency<T>(
  items: T[],
  pick: (item: T) => { amount_minor: number; currency: string } | null,
): Map<string, number> {
  const totals = new Map<string, number>();
  for (const item of items) {
    const m = pick(item);
    if (m) totals.set(m.currency, (totals.get(m.currency) ?? 0) + m.amount_minor);
  }
  return totals;
}

/** The currency with the largest total, or null when there is nothing. */
export function largest(
  totals: Map<string, number>,
): { currency: string; amount_minor: number } | null {
  let best: { currency: string; amount_minor: number } | null = null;
  for (const [currency, amount_minor] of totals) {
    if (!best || amount_minor > best.amount_minor) best = { currency, amount_minor };
  }
  return best;
}

/** "$48K" for the largest currency, "—" when empty; `+N more` when other currencies exist. */
export function showLargest(totals: Map<string, number>): string {
  const top = largest(totals);
  if (!top) return "—";
  return compactMoney(top.amount_minor, top.currency);
}

export function otherCurrencies(totals: Map<string, number>): string | undefined {
  return totals.size > 1
    ? `+${totals.size - 1} more currenc${totals.size === 2 ? "y" : "ies"}`
    : undefined;
}

/** "2026-11" for a date or ISO string. */
export function monthKey(iso: string): string {
  return iso.slice(0, 7);
}

/** "Nov" style label for a "2026-11" key. */
export function monthLabel(key: string): string {
  return new Date(`${key}-01T00:00:00`).toLocaleString(undefined, { month: "short" });
}
