import { Card, Empty } from "../ui";

export interface Bucket {
  label: string;
  value: number;
  /** Text shown at the right, e.g. a formatted amount. */
  display: string;
}

/** Labelled progress bars; the largest bucket is cyan, the rest muted. */
export function AgingBars({
  title,
  buckets,
  emptyText = "Nothing to chart yet.",
}: {
  title: string;
  buckets: Bucket[];
  emptyText?: string;
}) {
  const max = Math.max(0, ...buckets.map((b) => b.value));
  return (
    <Card title={title} icon={<ChartIcon size={16} />}>
      {max === 0 ? (
        <Empty>{emptyText}</Empty>
      ) : (
        <ul className="space-y-3">
          {buckets.map((b) => (
            <li key={b.label}>
              <div className="mb-1 flex justify-between text-xs">
                <span className="text-slate-400">{b.label}</span>
                <span className="text-slate-300 tabular-nums">{b.display}</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-navy-800">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${(b.value / max) * 100}%`,
                    background: b.value === max ? "var(--chart-accent)" : "var(--chart-bar)",
                  }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
import { ChartIcon } from "../icons";
