import { Link } from "react-router";
import { Badge, Card, Empty, ErrorNote, PageHeader } from "../components/ui";
import { when } from "../format";
import type { AgentTask, Page } from "../types";
import { usePoll } from "../usePoll";

export function Activity() {
  const { data, error } = usePoll<Page<AgentTask>>("/agents/activity?limit=100");

  return (
    <>
      <PageHeader
        title="Agent activity"
        subtitle="Every agent call and tool call, with its input hash, outcome and duration. Refreshes every 5 s."
      />
      <Card>
        <ErrorNote message={error} />
        {data?.items.length === 0 && <Empty>No agent activity yet.</Empty>}
        {data && data.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-slate-500 uppercase">
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
                {data.items.map((t) => (
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
                    <td className="py-2 text-xs">
                      {t.execution_id ? (
                        <Link
                          to={`/payments/${t.execution_id}`}
                          className="text-accent-cyan hover:underline"
                        >
                          open
                        </Link>
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
