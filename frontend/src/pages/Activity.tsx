import { useState } from "react";
import { StatCard } from "../components/charts/StatCard";
import { BoltIcon, ClockIcon, FlowIcon, InfoIcon, ListIcon } from "../components/icons";
import { Link } from "react-router";
import { api } from "../api";
import { Badge, Card, Empty, ErrorNote, PageHeader, ghostButton, Loading } from "../components/ui";
import { HandoffGraph } from "../components/HandoffGraph";
import { ago, when } from "../format";
import type { AgentTask, LatestHandoff, Page } from "../types";
import { usePoll } from "../usePoll";
import { toast } from "../toast";

const FEED_DOT: Record<AgentTask["status"], string> = {
  succeeded: "bg-emerald-400",
  running: "bg-accent-purple anim-working",
  failed: "bg-red-400",
};

/** The newest calls, unfiltered, as a short live feed beside the hand-off graph. */
function LiveFeed({ items }: { items: AgentTask[] | undefined }) {
  if (!items) return <Loading rows={5} />;
  if (items.length === 0) return <p className="text-sm text-slate-500">Nothing yet.</p>;
  return (
    <ul className="divide-y divide-navy-800" aria-live="off">
      {items.map((t) => (
        <li key={t.id} className="flex items-start gap-2.5 py-2">
          <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${FEED_DOT[t.status]}`} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm text-slate-200">
              {t.agent}
              {t.tool && <span className="text-slate-500"> → {t.tool}</span>}
            </span>
            <span className="block truncate text-xs text-slate-500">
              {t.error ?? `${t.status}${t.duration_ms !== null ? ` · ${t.duration_ms} ms` : ""}`}
            </span>
          </span>
          <span className="shrink-0 text-xs whitespace-nowrap text-slate-500">
            {ago(t.created_at)}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Command Center: every agent and tool call, with Retry for failed workflow steps. */
export function Activity() {
  const [onlyFailed, setOnlyFailed] = useState(false);
  const { data, error, reload } = usePoll<Page<AgentTask>>(
    `/agents/activity?limit=200${onlyFailed ? "&status=failed" : ""}`,
  );
  const handoff = usePoll<LatestHandoff>("/agents/handoff");
  const feed = usePoll<Page<AgentTask>>("/agents/activity?limit=8");
  const [message, setMessage] = useState<string | null>(null);
  const rows = data?.items ?? [];
  const agentRows = rows.filter((t) => !t.tool);
  const failed = rows.filter((t) => t.status === "failed").length;
  const timed = agentRows.filter((t) => t.duration_ms !== null);
  const avg = timed.length
    ? Math.round(timed.reduce((sum, t) => sum + (t.duration_ms ?? 0), 0) / timed.length)
    : 0;

  const retry = async (executionId: string) => {
    setMessage(null);
    try {
      await api(`/workflows/${executionId}/retry`, { method: "POST" });
      setMessage("Retry started; the run continues in the background.");
      toast("Retry started", "info");
      await reload();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Retry failed");
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Agents at work"
        icon={<BoltIcon size={22} />}
        live
        title="Command Center"
        subtitle="Every agent call and tool call with its input hash, outcome and duration."
      />
      <div data-tour="command-center" className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Calls shown" value={rows.length} icon={<ListIcon size={16} />} />
        <StatCard
          label="Agent calls"
          value={agentRows.length}
          icon={<BoltIcon size={16} />}
          tone="sky"
        />
        <StatCard
          label="Failed"
          value={failed}
          icon={<InfoIcon size={16} />}
          tone="red"
          danger={failed > 0}
        />
        <StatCard
          label="Avg agent time"
          value={`${avg} ms`}
          icon={<ClockIcon size={16} />}
          tone="amber"
        />
      </div>
      <div className="mb-6 grid gap-4 items-start lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <Card title="Agent hand-off" icon={<FlowIcon size={16} />}>
          <ErrorNote message={handoff.error} />
          {handoff.data ? (
            <HandoffGraph run={handoff.data.run} />
          ) : (
            !handoff.error && <Loading rows={3} />
          )}
        </Card>
        <Card title="Live activity" icon={<ClockIcon size={16} />}>
          <LiveFeed items={feed.data?.items} />
        </Card>
      </div>
      <Card
        actions={
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={onlyFailed}
              onChange={(e) => setOnlyFailed(e.target.checked)}
            />
            Only failures
          </label>
        }
      >
        <ErrorNote message={error} />
        {message && <p className="mb-3 text-sm text-amber-200">{message}</p>}
        {!data && !error && <Loading rows={6} />}
        {data && rows.length === 0 && (
          <Empty hint="Every agent call and tool call is listed here as it happens.">
            No agent activity yet.
          </Empty>
        )}
        {rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-slate-500">
                <tr>
                  <th className="py-2 pr-4">When</th>
                  <th className="py-2 pr-4">Agent → tool</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Try</th>
                  <th className="py-2 pr-4">ms</th>
                  <th className="py-2 pr-4">Input hash</th>
                  <th className="py-2">Run</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-navy-800">
                {rows.map((t) => (
                  <tr key={t.id}>
                    <td className="py-2 pr-4 whitespace-nowrap text-slate-400">
                      {when(t.created_at)}
                    </td>
                    <td className="py-2 pr-4 whitespace-nowrap text-slate-200">
                      {t.agent}
                      {t.tool && <span className="text-slate-500"> → {t.tool}</span>}
                      {t.error && (
                        <div className="max-w-md truncate text-xs text-red-300">{t.error}</div>
                      )}
                    </td>
                    <td className="py-2 pr-4">
                      <Badge value={t.status} />
                    </td>
                    <td className="py-2 pr-4 text-slate-400">{t.attempt}</td>
                    <td className="py-2 pr-4 text-slate-400">{t.duration_ms ?? "—"}</td>
                    <td className="py-2 pr-4 font-mono text-xs text-slate-500">
                      {t.input_hash.slice(0, 12)}
                    </td>
                    <td className="py-2 text-xs whitespace-nowrap">
                      {t.execution_id ? (
                        <span className="flex items-center gap-2">
                          <Link
                            to={`/payments/${t.execution_id}`}
                            className="text-accent-soft hover:underline"
                          >
                            open
                          </Link>
                          {t.status === "failed" && (
                            <button
                              onClick={() => void retry(t.execution_id!)}
                              className={`${ghostButton} px-2 py-0.5 text-xs`}
                            >
                              Retry
                            </button>
                          )}
                        </span>
                      ) : (
                        <span className="text-slate-600">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
