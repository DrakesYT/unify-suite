/** Shared look for the dashboard charts and urgency colours. */

export const ACCENT = "var(--chart-ai)"; // the one accent; charts use it for the series that matters
export const FAILED = "var(--chart-danger)";
export const QUIET = "var(--chart-quiet)"; // secondary series and small trend lines
export const AXIS = { stroke: "var(--chart-axis)", fontSize: 11, tickLine: false, axisLine: false };
export const TOOLTIP = {
  contentStyle: {
    background: "var(--tooltip-bg)",
    border: "1px solid var(--tooltip-border)",
    boxShadow: "var(--card-shadow)",
    borderRadius: 10,
    fontSize: 12,
  },
  itemStyle: { color: "var(--tooltip-text)" },
  labelStyle: { color: "var(--tooltip-label)" },
};

export const URGENCY_TONE: Record<string, string> = {
  critical: "bg-red-400",
  high: "bg-amber-400",
  normal: "bg-sky-400",
  low: "bg-slate-500",
  unrated: "bg-slate-700",
};
