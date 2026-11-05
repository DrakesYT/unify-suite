import { Link } from "react-router";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Badge } from "../../components/ui";
import { TicketIcon } from "../../components/icons";
import { ago, label } from "../../format";
import type { Overview } from "../../types";
import { PALETTE, TOOLTIP, URGENCY_TONE } from "./chartStyle";
import { Panel, Quiet } from "./parts";

export function SupportBoard({ support }: { support: Overview["support"] }) {
  return (
    <Panel
      title="Support tickets"
      icon={<TicketIcon size={17} />}
      to="/support"
      aside={<span className="mr-2 text-xs text-slate-500">{support.open} open</span>}
    >
      <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1">
        {support.by_urgency.map((u) => (
          <span
            key={u.label}
            className="flex items-center gap-1.5 text-xs text-slate-400 capitalize"
          >
            <span className={`h-2 w-2 rounded-full ${URGENCY_TONE[u.label] ?? "bg-slate-500"}`} />
            {u.label} <span className="text-slate-200">{u.value}</span>
          </span>
        ))}
      </div>
      {support.tickets.length === 0 ? (
        <Quiet>No open tickets.</Quiet>
      ) : (
        <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_150px]">
          <ul className="divide-y divide-white/5">
            {support.tickets.map((t) => (
              <li key={t.ticket_id}>
                <Link
                  to={`/support#ticket-${t.ticket_id}`}
                  className="-mx-2 flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-white/[0.03]"
                >
                  <span
                    className={`h-8 w-1 shrink-0 rounded-full ${URGENCY_TONE[t.urgency ?? "unrated"]}`}
                    title={t.urgency ?? "not rated"}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-slate-100">{t.title}</span>
                    <span className="block truncate text-xs text-slate-500">
                      {t.customer_name ?? "no customer"} ·{" "}
                      {t.category ? label(t.category) : "unclassified"} · {ago(t.created_at)}
                    </span>
                  </span>
                  <Badge value={t.status} />
                </Link>
              </li>
            ))}
          </ul>
          {support.by_category.length > 0 && (
            <div className="flex flex-col items-center">
              <p className="self-start text-[11px] tracking-wide text-slate-500 uppercase">
                By category
              </p>
              <ResponsiveContainer width="100%" height={120}>
                <PieChart>
                  <Pie
                    data={support.by_category}
                    dataKey="value"
                    nameKey="label"
                    innerRadius={34}
                    outerRadius={54}
                    paddingAngle={2}
                    stroke="none"
                  >
                    {support.by_category.map((d, i) => (
                      <Cell key={d.label} fill={PALETTE[i % PALETTE.length]} />
                    ))}
                  </Pie>
                  <Tooltip {...TOOLTIP} formatter={(v: number, n: string) => [v, label(n)]} />
                </PieChart>
              </ResponsiveContainer>
              <ul className="w-full space-y-0.5">
                {support.by_category.map((d, i) => (
                  <li
                    key={d.label}
                    className="flex items-center gap-1.5 text-[11px] text-slate-400"
                  >
                    <span
                      className="h-2 w-2 rounded-sm"
                      style={{ background: PALETTE[i % PALETTE.length] }}
                    />
                    <span className="flex-1 capitalize">{label(d.label)}</span>
                    <span className="text-slate-300">{d.value}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}
