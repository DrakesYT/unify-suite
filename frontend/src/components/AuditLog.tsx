import { useEffect, useState } from "react";
import { api } from "../api";
import { label, when } from "../format";
import type { ActivityItem } from "../types";
import { ListIcon } from "./icons";
import { Card, Empty, ErrorNote, ghostButton, inputClass } from "./ui";

const PAGE = 50;

/** What one audit row is about, in a few words (the detail the service recorded with it). */
function summary(item: ActivityItem): string {
  const parts = Object.entries(item.detail ?? {})
    .filter(([, value]) => value !== null && typeof value !== "object")
    .map(([key, value]) => `${label(key)}: ${String(value)}`);
  return parts.join(" · ");
}

/** The audit log: who did what, newest first, with a filter and older pages on demand. */
export function AuditLog() {
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<ActivityItem[]>([]);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async (q: string, before: string | null, known: ActivityItem[]) => {
    try {
      const params = new URLSearchParams({ limit: String(PAGE) });
      if (q.trim()) params.set("q", q.trim());
      if (before) params.set("before", before);
      const page = await api<ActivityItem[]>(`/dashboard/audit?${params.toString()}`);
      setRows([...known, ...page]);
      setMore(page.length === PAGE);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the audit log");
    }
  };

  // Typing filters after a short pause, so each keystroke is not a request.
  useEffect(() => {
    const timer = setTimeout(() => void load(query, null, []), 300);
    return () => clearTimeout(timer);
  }, [query]);

  return (
    <Card
      title="Audit log"
      icon={<ListIcon size={16} />}
      actions={
        <input
          className={`${inputClass} w-56`}
          type="search"
          placeholder="Filter: approval, invoice, a name…"
          aria-label="Filter the audit log"
          value={query}
          maxLength={80}
          onChange={(e) => setQuery(e.target.value)}
        />
      }
    >
      <p className="mb-3 text-xs text-slate-500">
        Every change is recorded here and can never be edited or removed.
      </p>
      <ErrorNote message={error} />
      {rows.length === 0 && !error && <Empty>Nothing matches.</Empty>}
      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-slate-500">
              <tr>
                <th className="py-2 pr-4">When</th>
                <th className="py-2 pr-4">Who</th>
                <th className="py-2 pr-4">What</th>
                <th className="py-2">Detail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-navy-800">
              {rows.map((item) => (
                <tr key={item.id} className="align-top">
                  <td className="py-2 pr-4 text-xs whitespace-nowrap text-slate-400">
                    {when(item.at)}
                  </td>
                  <td className="py-2 pr-4 whitespace-nowrap text-slate-200">
                    {item.actor_name ?? "System"}
                  </td>
                  <td className="py-2 pr-4 whitespace-nowrap text-slate-300">
                    {label(item.action.replaceAll(".", " "))}
                  </td>
                  <td className="py-2 text-xs text-slate-500">{summary(item)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {more && (
        <button
          className={`${ghostButton} mt-3`}
          onClick={() => void load(query, rows[rows.length - 1].at, rows)}
        >
          Load older entries
        </button>
      )}
    </Card>
  );
}
