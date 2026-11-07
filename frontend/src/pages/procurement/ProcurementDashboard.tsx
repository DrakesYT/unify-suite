import { AgingBars } from "../../components/charts/AgingBars";
import { otherCurrencies, showLargest } from "../../components/charts/currency";
import { Gauge } from "../../components/charts/Gauge";
import { MiniBars } from "../../components/charts/MiniTrend";
import { HeroStat, StatCard } from "../../components/charts/StatCard";
import type { PurchaseOrder, PurchaseRequest } from "../../types";
import {
  approvalPercent,
  monthlySpend,
  onTimePercent,
  pendingOrders,
  rankingSavings,
  spendTotals,
  topVendors,
} from "./stats";

export function ProcurementDashboard({
  orders,
  requests,
  vendorNames,
}: {
  orders: PurchaseOrder[];
  requests: PurchaseRequest[];
  vendorNames: Map<string, string>;
}) {
  const spend = spendTotals(orders);
  const savings = rankingSavings(requests);
  const monthly = monthlySpend(orders);

  return (
    <div className="mb-6 space-y-6">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,2fr)]">
        <HeroStat
          label="Total PO spend"
          value={showLargest(spend)}
          caption={otherCurrencies(spend) ?? "Approved purchase orders"}
        />
        <div className="grid grid-cols-2 gap-4">
          <StatCard label="POs waiting for approval" value={pendingOrders(orders)} />
          <StatCard
            label="Saved by vendor ranking"
            value={showLargest(savings)}
            delta="vs. average quote"
            accent
          />
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-4">
        <Gauge
          title="On-time delivery"
          percent={onTimePercent(orders)}
          caption="No delivered orders yet."
        />
        <Gauge
          title="PO approval rate"
          percent={approvalPercent(orders)}
          caption="No decided orders yet."
        />
        <MiniBars
          title={`Spend per month${monthly.currency ? ` (${monthly.currency})` : ""}`}
          points={monthly.points}
          emptyText="No approved orders yet."
        />
        <AgingBars
          title="Top vendors by spend"
          buckets={vendorNames.size === 0 ? [] : topVendors(orders, vendorNames)}
          emptyText="No approved orders yet."
        />
      </div>
    </div>
  );
}
