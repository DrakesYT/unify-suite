/** Shared look for the dashboard charts and urgency colours. */

export const ACCENT = "#8b5cf6"; // the one accent; charts use it for the series that matters
export const FAILED = "#f87171";
export const QUIET = "#64748b"; // secondary series and small trend lines
export const AXIS = { stroke: "#475569", fontSize: 11, tickLine: false, axisLine: false };
export const TOOLTIP = {
  contentStyle: {
    background: "#0c1229",
    border: "1px solid rgb(255 255 255 / 0.1)",
    borderRadius: 10,
    fontSize: 12,
  },
  itemStyle: { color: "#e2e8f0" },
  labelStyle: { color: "#94a3b8" },
};

export const URGENCY_TONE: Record<string, string> = {
  critical: "bg-red-400",
  high: "bg-amber-400",
  normal: "bg-sky-400",
  low: "bg-slate-500",
  unrated: "bg-slate-700",
};
