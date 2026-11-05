import { Link } from "react-router";
import { approvalHeadline } from "../../approvalText";
import { Badge } from "../../components/ui";
import { ShieldIcon } from "../../components/icons";
import { ago } from "../../format";
import type { Approval, Page } from "../../types";
import { Panel, Quiet, Skeleton } from "./parts";

/** Agent actions paused for a human. Nothing here happens until a manager decides. */
export function ApprovalsBoard({ page }: { page: Page<Approval> | null }) {
  const items = page?.items ?? [];
  return (
    <Panel
      title="Approvals"
      icon={<ShieldIcon size={17} />}
      to="/approvals"
      linkText="Approval Center"
      aside={
        items.length > 0 && (
          <span className="mr-2 rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-300">
            {items.length}
            {page?.next_cursor ? "+" : ""} waiting
          </span>
        )
      }
    >
      {!page && <Skeleton className="h-32" />}
      {page && items.length === 0 && (
        <Quiet>Nothing waiting. Every agent action that needs a human has been decided.</Quiet>
      )}
      <ul className="space-y-2">
        {items.map((a) => {
          const { title, detail } = approvalHeadline(a);
          const flagged = (a.payload.suspicious_text?.length ?? 0) > 0;
          return (
            <li key={a.id}>
              <Link
                to="/approvals"
                className={`flex items-center gap-3 rounded-xl px-3 py-2.5 ring-1 transition hover:bg-white/[0.03] ${
                  flagged ? "bg-red-500/[0.06] ring-red-500/30" : "bg-navy-950/60 ring-white/5"
                }`}
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-slate-100">{title}</span>
                  <span className="block truncate text-xs text-slate-500">
                    <span className="capitalize">{a.department}</span> · {detail} ·{" "}
                    {ago(a.created_at)}
                  </span>
                  {flagged && (
                    <span className="mt-1 block text-[11px] font-medium text-red-300">
                      Possible prompt injection in the document. Check before approving.
                    </span>
                  )}
                </span>
                {a.payload.match_status && <Badge value={a.payload.match_status} />}
                {a.payload.urgency && <Badge value={a.payload.urgency} />}
                <span className="hidden rounded-lg bg-accent-purple/20 px-2.5 py-1 text-xs font-medium text-violet-200 sm:inline">
                  Review
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
