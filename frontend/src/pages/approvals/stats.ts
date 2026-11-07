import type { Approval } from "../../types";

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

const decidedAt = (a: Approval) => (a.decided_at ? new Date(a.decided_at).getTime() : null);

/** How many of `decided` got `status` within the last 7 days. */
export function decidedInWeek(
  decided: Approval[],
  status: "approved" | "rejected",
  now = Date.now(),
): number {
  return decided.filter((a) => {
    const t = decidedAt(a);
    return a.status === status && t !== null && now - t <= WEEK_MS;
  }).length;
}

/** Median minutes between request and decision, or null with nothing decided. */
export function medianMinutes(decided: Approval[]): number | null {
  const minutes = decided
    .map((a) => {
      const t = decidedAt(a);
      return t === null ? null : Math.max(0, (t - new Date(a.created_at).getTime()) / 60_000);
    })
    .filter((m): m is number => m !== null)
    .sort((a, b) => a - b);
  if (minutes.length === 0) return null;
  const mid = Math.floor(minutes.length / 2);
  return minutes.length % 2 ? minutes[mid] : (minutes[mid - 1] + minutes[mid]) / 2;
}

/** "45 min", "3.2 h", "2.1 d". */
export function formatMinutes(m: number | null): string {
  if (m === null) return "—";
  if (m < 60) return `${Math.round(m)} min`;
  if (m < 1440) return `${(m / 60).toFixed(1)} h`;
  return `${(m / 1440).toFixed(1)} d`;
}

export function pendingByDepartment(pending: Approval[]) {
  const counts = new Map<string, number>();
  for (const a of pending) counts.set(a.department, (counts.get(a.department) ?? 0) + 1);
  return [...counts]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([label, value]) => ({ label: label[0].toUpperCase() + label.slice(1), value }));
}

export function recentDecisions(decided: Approval[], count = 6): Approval[] {
  return decided
    .filter((a) => a.decided_at)
    .sort((a, b) => (decidedAt(b) ?? 0) - (decidedAt(a) ?? 0))
    .slice(0, count);
}
