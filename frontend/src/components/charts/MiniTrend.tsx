import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
} from "recharts";
import { Card, Empty } from "../ui";

export interface Point {
  label: string;
  [series: string]: string | number;
}

const tooltipStyle = {
  background: "var(--tooltip-bg)",
  border: "1px solid var(--tooltip-border)",
  borderRadius: 8,
  color: "var(--tooltip-text)",
  fontSize: 12,
};
const axis = { fill: "var(--chart-quiet)", fontSize: 11 };

/** Area chart: `accent` series in cyan, optional `muted` series in slate. */
export function MiniTrend({
  title,
  points,
  accent,
  muted,
  names,
  emptyText = "Nothing to chart yet.",
}: {
  title: string;
  points: Point[];
  accent: string;
  muted?: string;
  names?: Record<string, string>;
  emptyText?: string;
}) {
  const any = points.some((p) => Number(p[accent]) > 0 || (muted && Number(p[muted]) > 0));
  return (
    <Card title={title}>
      {!any ? (
        <Empty>{emptyText}</Empty>
      ) : (
        <div className="h-44">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={points} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
              <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
              <XAxis
                dataKey="label"
                tick={axis}
                tickLine={false}
                axisLine={false}
                interval="preserveStartEnd"
              />
              <Tooltip
                contentStyle={tooltipStyle}
                formatter={(v, name) => [String(v), names?.[String(name)] ?? String(name)]}
              />
              {muted && (
                <Area
                  dataKey={muted}
                  stroke="var(--chart-quiet)"
                  fill="var(--chart-quiet)"
                  fillOpacity={0.12}
                  strokeWidth={1.5}
                  isAnimationActive={false}
                />
              )}
              <Area
                dataKey={accent}
                stroke="var(--chart-accent)"
                fill="var(--chart-accent)"
                fillOpacity={0.18}
                strokeWidth={2}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}

/** Vertical bars from `points`; bars flagged by `accentLabel` (default: the largest) are cyan. */
export function MiniBars({
  title,
  points,
  dataKey = "value",
  accentLabel,
  emptyText = "Nothing to chart yet.",
}: {
  title: string;
  points: Point[];
  dataKey?: string;
  accentLabel?: string;
  emptyText?: string;
}) {
  const max = Math.max(0, ...points.map((p) => Number(p[dataKey])));
  return (
    <Card title={title}>
      {max === 0 ? (
        <Empty>{emptyText}</Empty>
      ) : (
        <div className="h-44">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={points} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
              <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
              <XAxis
                dataKey="label"
                tick={axis}
                tickLine={false}
                axisLine={false}
                interval="preserveStartEnd"
              />
              <Tooltip
                contentStyle={tooltipStyle}
                cursor={{ fill: "var(--chart-cursor)" }}
                formatter={(v) => [String(v), ""]}
              />
              <Bar
                dataKey={dataKey}
                radius={[4, 4, 0, 0]}
                fill="var(--chart-bar)"
                isAnimationActive={false}
                shape={(props: {
                  x?: number;
                  y?: number;
                  width?: number;
                  height?: number;
                  payload?: Point;
                }) => {
                  const hot = accentLabel
                    ? props.payload?.label === accentLabel
                    : Number(props.payload?.[dataKey]) === max;
                  return (
                    <rect
                      x={props.x}
                      y={props.y}
                      width={props.width}
                      height={props.height}
                      rx={4}
                      fill={hot ? "var(--chart-accent)" : "var(--chart-bar)"}
                    />
                  );
                }}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}
