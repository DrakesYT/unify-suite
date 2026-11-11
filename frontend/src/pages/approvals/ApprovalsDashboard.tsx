import { Donut } from "../../components/charts/Donut";
import { CheckIcon, ClockIcon, CloseIcon, ShieldIcon } from "../../components/icons";
import { MiniBars } from "../../components/charts/MiniTrend";
import { HeroStat, StatCard } from "../../components/charts/StatCard";
import { Badge, Card, Empty } from "../../components/ui";
import { approvalHeadline } from "../../approvalText";
import { ago } from "../../format";
import type { Approval, Page } from "../../types";
import { usePoll } from "../../usePoll";
import {
  decidedInWeek,
  formatMinutes,
  medianMinutes,
  pendingByDepartment,
  recentDecisions,
} from "./stats";

/** Charts over every approval the user can see (pending, approved and rejected). */
export function ApprovalsDashboard() {
  const pending = usePoll<Page<Approval>>("/approvals?status=pending&limit=200").data?.items ?? [];
  const approved =
    usePoll<Page<Approval>>("/approvals?status=approved&limit=200").data?.items ?? [];
  const rejected =
    usePoll<Page<Approval>>("/approvals?status=rejected&limit=200").data?.items ?? [];
  const decided = [...approved, ...rejected];
  const recent = recentDecisions(decided);

  return (
    <div className="mb-6 space-y-6">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,2fr)]">
        <HeroStat
          label="Waiting for a decision"
          icon={<ShieldIcon size={16} />}
          value={String(pending.length)}
          caption={pending.length === 0 ? "Nothing is waiting." : "Pending approvals"}
        />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <StatCard
            label="Approved, last 7 days"
            icon={<CheckIcon size={16} />}
            tone="emerald"
            value={decidedInWeek(decided, "approved")}
            accent
          />
          <StatCard
            label="Rejected, last 7 days"
            value={decidedInWeek(decided, "rejected")}
            icon={<CloseIcon size={16} />}
            tone="red"
          />
          <StatCard
            label="Median time to decide"
            value={formatMinutes(medianMinutes(decided))}
            icon={<ClockIcon size={16} />}
            tone="amber"
          />
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <MiniBars
          title="Pending by department"
          points={pendingByDepartment(pending)}
          emptyText="No pending approvals."
        />
        <Donut
          title="Approved vs rejected"
          slices={[
            { key: "approved", value: approved.length },
            { key: "rejected", value: rejected.length },
          ]}
          accentKey="approved"
          emptyText="No decisions yet."
        />
        <Card title="Recent decisions" icon={<ClockIcon size={16} />}>
          {recent.length === 0 ? (
            <Empty>No decisions yet.</Empty>
          ) : (
            <ul className="space-y-2.5">
              {recent.map((a) => (
                <li key={a.id} className="flex items-center gap-2 text-sm">
                  <Badge value={a.status} />
                  <span className="min-w-0 flex-1 truncate text-slate-300">
                    {approvalHeadline(a).title}
                  </span>
                  <span className="shrink-0 text-xs text-slate-500">
                    {a.decided_at ? ago(a.decided_at) : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
