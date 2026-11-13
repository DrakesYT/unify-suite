import { shortDay } from "../../format";
import type { Ticket } from "../../types";

export const STATUSES = ["open", "investigating", "escalated", "resolved"] as const;

/** Ticket counts per status; "closed" is folded into "resolved". */
export function statusCounts(tickets: Ticket[]): Record<(typeof STATUSES)[number], number> {
  const counts = { open: 0, investigating: 0, escalated: 0, resolved: 0 };
  for (const t of tickets) counts[t.status === "closed" ? "resolved" : t.status] += 1;
  return counts;
}

/** Slices by category; unclassified tickets are listed as "unclassified". */
export function categorySlices(tickets: Ticket[]) {
  const counts = new Map<string, number>();
  for (const t of tickets) {
    const key = t.category ?? "unclassified";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts].sort(([, a], [, b]) => b - a).map(([key, value]) => ({ key, value }));
}

const dayKey = (d: Date) => d.toLocaleDateString("en-CA");

/** Last `days` days: tickets created, and tickets resolved/closed (by last update) per day. */
export function createdVsResolved(tickets: Ticket[], days = 14, now = new Date()) {
  const points = Array.from({ length: days }, (_, i) => {
    const d = new Date(now);
    d.setDate(d.getDate() - (days - 1 - i));
    return { key: dayKey(d), label: shortDay(dayKey(d)), created: 0, resolved: 0 };
  });
  const byKey = new Map(points.map((p) => [p.key, p]));
  for (const t of tickets) {
    const created = byKey.get(dayKey(new Date(t.created_at)));
    if (created) created.created += 1;
    if (t.status === "resolved" || t.status === "closed") {
      const resolved = byKey.get(dayKey(new Date(t.updated_at)));
      if (resolved) resolved.resolved += 1;
    }
  }
  return points.map(({ label, created, resolved }) => ({ label, created, resolved }));
}
