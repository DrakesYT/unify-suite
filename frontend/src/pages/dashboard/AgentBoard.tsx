import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BoltIcon } from "../../components/icons";
import { ago, label } from "../../format";
import type { ActivityItem, Charts, Overview } from "../../types";
import { AXIS, TOOLTIP } from "./chartStyle";
import { Panel, Skeleton } from "./parts";

const FEED_ROWS = 6;

function describe(item: ActivityItem): string {
  const [entity, verb] = item.action.split(".");
  return `${label(verb ?? item.action)} ${label(entity)}`;
}

/** What the agents did: calls per day (succeeded/failed) and the latest audit events. */
export function AgentBoard({
  agents,
  charts,
  feed,
}: {
  agents: Overview["agents"];
  charts: Charts | null;
  feed: ActivityItem[] | null;
}) {
  const rate = agents.calls ? Math.round((100 * agents.succeeded) / agents.calls) : null;
  return (
    <Panel
      title="Agent activity"
      icon={<BoltIcon size={17} />}
      to="/activity"
      linkText="Command Center"
    >
      <p className="mb-2 text-xs text-slate-400">
        Last 24 h: <span className="text-slate-100">{agents.calls}</span> agent and tool calls
        {rate !== null && (
          <>
            , <span className="text-emerald-300">{rate}% succeeded</span>
          </>
        )}
        {agents.failed > 0 && <span className="text-red-300"> · {agents.failed} failed</span>}
      </p>
      {charts ? (
        <ResponsiveContainer width="100%" height={150}>
          <BarChart
            data={charts.agent_calls_by_day.map((d) => ({ ...d, day: d.day.slice(5) }))}
            margin={{ top: 4, right: 0, bottom: 0, left: -28 }}
          >
            <CartesianGrid stroke="rgb(255 255 255 / 0.05)" vertical={false} />
            <XAxis dataKey="day" {...AXIS} />
            <YAxis allowDecimals={false} {...AXIS} />
            <Tooltip {...TOOLTIP} cursor={{ fill: "rgb(255 255 255 / 0.03)" }} />
            <Bar dataKey="succeeded" stackId="a" fill="#22d3ee" />
            <Bar dataKey="failed" stackId="a" fill="#f87171" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <Skeleton className="h-[150px]" />
      )}
      <p className="mt-3 mb-1 text-[11px] tracking-wide text-slate-500 uppercase">
        Recent activity
      </p>
      <ul className="divide-y divide-white/5 text-sm">
        {(feed ?? []).slice(0, FEED_ROWS).map((item) => (
          <li key={item.id} className="flex items-baseline justify-between gap-3 py-1.5">
            <span className="min-w-0 truncate text-slate-300">
              <span className="text-slate-500">{item.actor_name ?? "System"}</span> ·{" "}
              {describe(item)}
            </span>
            <span className="shrink-0 text-xs text-slate-500">{ago(item.at)}</span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
