/** Shared look for the dashboard charts and urgency colours. */

export const PALETTE = [
  "#8b5cf6",
  "#22d3ee",
  "#f59e0b",
  "#34d399",
  "#f472b6",
  "#94a3b8",
  "#60a5fa",
];
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
