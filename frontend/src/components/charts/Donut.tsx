import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { label as pretty } from "../../format";
import { Card, Empty } from "../ui";

export interface Slice {
  key: string;
  value: number;
}

const tooltipStyle = {
  background: "#0c1229",
  border: "1px solid #141c3a",
  borderRadius: 8,
  color: "#e2e8f0",
  fontSize: 12,
};

/** Donut with a centre total. The `accentKey` slice is cyan (or `accentColor`), the rest muted. */
export function Donut({
  title,
  slices,
  accentKey,
  accentColor = "var(--chart-accent)",
  emptyText = "Nothing to chart yet.",
}: {
  title: string;
  slices: Slice[];
  accentKey?: string;
  accentColor?: string;
  emptyText?: string;
}) {
  const shown = slices.filter((s) => s.value > 0);
  const total = shown.reduce((sum, s) => sum + s.value, 0);
  // Muted slices get stepped shades so neighbours stay apart without adding hues.
  const shades = ["#475569", "#334155", "#64748b", "#1e293b"];
  let shade = 0;
  const colours = shown.map((s) => (s.key === accentKey ? accentColor : shades[shade++ % 4]));
  return (
    <Card title={title}>
      {total === 0 ? (
        <Empty>{emptyText}</Empty>
      ) : (
        <div className="flex flex-wrap items-center gap-4">
          <div className="relative h-36 w-36 shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={shown}
                  dataKey="value"
                  nameKey="key"
                  innerRadius="68%"
                  outerRadius="100%"
                  stroke="none"
                  paddingAngle={shown.length > 1 ? 2 : 0}
                >
                  {shown.map((s, i) => (
                    <Cell key={s.key} fill={colours[i]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(v, name) => [String(v), pretty(String(name))]}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 grid place-items-center">
              <span className="text-xl font-semibold text-white tabular-nums">{total}</span>
            </div>
          </div>
          <ul className="min-w-0 flex-1 space-y-1.5 text-sm">
            {shown.map((s, i) => (
              <li key={s.key} className="flex items-center gap-2">
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ background: colours[i] }}
                />
                <span className="truncate text-slate-300 first-letter:uppercase">
                  {pretty(s.key)}
                </span>
                <span className="ml-auto text-slate-500 tabular-nums">{s.value}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
