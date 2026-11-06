import { Link } from "react-router";
import { Badge } from "../../components/ui";
import { TicketIcon } from "../../components/icons";
import { ago, label } from "../../format";
import type { Overview } from "../../types";
import { URGENCY_TONE } from "./chartStyle";
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
            <div>
              <p className="mb-2 text-xs text-slate-500">Open by category</p>
              <ul className="space-y-2">
                {support.by_category.map((d) => {
                  const top = support.by_category[0].value || 1;
                  return (
                    <li key={d.label} className="text-xs">
                      <span className="flex justify-between text-slate-300">
                        <span className="capitalize">{label(d.label)}</span>
                        <span className="tabular-nums">{d.value}</span>
                      </span>
                      <span className="mt-1 block h-1 overflow-hidden rounded-full bg-white/[0.06]">
                        <span
                          className="block h-full rounded-full bg-slate-400"
                          style={{ width: `${(100 * d.value) / top}%` }}
                        />
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}
