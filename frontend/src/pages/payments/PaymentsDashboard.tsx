import { AgingBars } from "../../components/charts/AgingBars";
import { CheckIcon, ClockIcon, InfoIcon, WalletIcon } from "../../components/icons";
import { Donut } from "../../components/charts/Donut";
import { otherCurrencies, showLargest } from "../../components/charts/currency";
import { MiniBars } from "../../components/charts/MiniTrend";
import { HeroStat, StatCard } from "../../components/charts/StatCard";
import type { Anomaly, Invoice, Receivable } from "../../types";
import { usePoll, usePollAll } from "../../usePoll";
import {
  agingBuckets,
  anomalyCount,
  matchSlices,
  matchedPercent,
  monthlyInvoiced,
  outstanding,
  overdueTotals,
} from "./stats";

export function PaymentsDashboard() {
  const receivables = usePoll<Receivable[]>("/finance/receivables").data ?? [];
  const invoices = usePollAll<Invoice>("/finance/invoices").data?.items ?? [];
  const anomalies = usePollAll<Anomaly>("/finance/anomalies").data?.items ?? [];
  const owed = outstanding(receivables);
  const matched = matchedPercent(invoices);
  const monthly = monthlyInvoiced(invoices);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,2fr)]">
        <HeroStat
          label="Outstanding receivables"
          icon={<WalletIcon size={16} />}
          value={showLargest(owed)}
          caption={otherCurrencies(owed) ?? `${receivables.length} unpaid customer orders`}
        />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <StatCard
            label="Overdue"
            value={showLargest(overdueTotals(receivables))}
            icon={<ClockIcon size={16} />}
            tone="red"
            danger
          />
          <StatCard
            label="Invoices matched"
            icon={<CheckIcon size={16} />}
            tone="emerald"
            value={matched === null ? "—" : `${Math.round(matched)}%`}
            accent
          />
          <StatCard
            label="Anomalies"
            value={anomalyCount(anomalies)}
            icon={<InfoIcon size={16} />}
            tone="amber"
          />
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <Donut
          title="Invoices by match status"
          slices={matchSlices(invoices)}
          accentKey="mismatch"
        />
        <AgingBars
          title="Overdue by age"
          buckets={agingBuckets(receivables)}
          emptyText="No overdue receivables."
        />
        <MiniBars
          title={`Invoiced per month${monthly.currency ? ` (${monthly.currency})` : ""}`}
          points={monthly.points}
          emptyText="No invoices yet."
        />
      </div>
    </div>
  );
}
