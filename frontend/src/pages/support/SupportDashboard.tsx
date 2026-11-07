import { Donut } from "../../components/charts/Donut";
import { MiniTrend } from "../../components/charts/MiniTrend";
import { StatCard } from "../../components/charts/StatCard";
import type { Ticket } from "../../types";
import { STATUSES, categorySlices, createdVsResolved, statusCounts } from "./stats";

export function SupportDashboard({ tickets }: { tickets: Ticket[] }) {
  const counts = statusCounts(tickets);
  return (
    <div className="mb-6 space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {STATUSES.map((s) => (
          <StatCard
            key={s}
            label={s[0].toUpperCase() + s.slice(1)}
            value={counts[s]}
            accent={s === "open"}
          />
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Donut
          title="Tickets by category"
          slices={categorySlices(tickets)}
          accentKey={categorySlices(tickets)[0]?.key}
          emptyText="No tickets yet."
        />
        <MiniTrend
          title="Created vs resolved, last 14 days"
          points={createdVsResolved(tickets)}
          accent="created"
          muted="resolved"
          names={{ created: "Created", resolved: "Resolved" }}
          emptyText="No tickets in the last 14 days."
        />
      </div>
    </div>
  );
}
