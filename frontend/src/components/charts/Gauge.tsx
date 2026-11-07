import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";
import { Card, Empty } from "../ui";

/** Half-donut for a 0-100 % rate; `percent` null means there is no data to rate. */
export function Gauge({
  title,
  percent,
  caption,
}: {
  title: string;
  percent: number | null;
  /** Shown instead of the gauge when there is no data. */
  caption?: string;
}) {
  const value = percent === null ? 0 : Math.min(100, Math.max(0, percent));
  return (
    <Card title={title}>
      {percent === null ? (
        <Empty>{caption ?? "No data yet."}</Empty>
      ) : (
        <div className="relative mx-auto h-24 w-full max-w-[200px]">
          <ResponsiveContainer width="100%" height="200%">
            <PieChart>
              <Pie
                data={[{ v: value }, { v: 100 - value }]}
                dataKey="v"
                startAngle={180}
                endAngle={0}
                innerRadius="72%"
                outerRadius="100%"
                stroke="none"
                cy="50%"
              >
                <Cell fill="var(--chart-accent)" />
                <Cell fill="var(--chart-muted)" />
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          <div className="absolute inset-x-0 bottom-0 text-center">
            <span className="text-2xl font-semibold text-white tabular-nums">
              {Math.round(value)}%
            </span>
          </div>
        </div>
      )}
    </Card>
  );
}
