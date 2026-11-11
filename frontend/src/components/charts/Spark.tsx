import { useId } from "react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { ACCENT } from "../../pages/dashboard/chartStyle";

/** A small filled trend line for a stat card (real weekly numbers only). */
export function Spark({
  series,
  name,
  className = "h-8 min-w-12 flex-1",
}: {
  series: number[];
  name: string;
  className?: string;
}) {
  const id = useId().replace(/:/g, "");
  const data = series.map((v, i) => ({ i, v }));
  return (
    <div
      className={className}
      role="img"
      aria-label={`${name}, last ${series.length} weeks: ${series.join(", ")}`}
      title={`${name}, last ${series.length} weeks`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 3, right: 2, bottom: 2, left: 2 }}>
          <defs>
            <linearGradient id={`spark-${id}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={ACCENT} stopOpacity={0.28} />
              <stop offset="100%" stopColor={ACCENT} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="v"
            stroke={ACCENT}
            strokeWidth={2}
            fill={`url(#spark-${id})`}
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
