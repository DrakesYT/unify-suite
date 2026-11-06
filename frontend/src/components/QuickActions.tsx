import type { ReactNode } from "react";
import { useNavigate } from "react-router";
import type { QuickAction } from "../types";
import { usePoll } from "../usePoll";
import { CartIcon, ChartIcon, ShieldIcon, TicketIcon, UsersIcon } from "./icons";

const ICONS: Record<QuickAction["icon"], ReactNode> = {
  approvals: <ShieldIcon size={17} />,
  lead: <ChartIcon size={17} />,
  hiring: <UsersIcon size={17} />,
  supplier: <CartIcon size={17} />,
  ticket: <TicketIcon size={17} />,
};

/** Shortcuts built by code from real records: ask Aura about one, or open a page. */
export function QuickActions({ onAsk, busy }: { onAsk: (prompt: string) => void; busy: boolean }) {
  const navigate = useNavigate();
  const { data } = usePoll<QuickAction[]>("/ai/quick-actions");
  if (!data?.length) return null;

  return (
    <div className="border-t border-white/5 px-4 py-3">
      <p className="mb-2 text-[11px] font-semibold text-slate-500">Quick actions</p>
      <div className="grid grid-cols-2 gap-2">
        {data.map((a) => (
          <button
            key={`${a.icon}-${a.detail}`}
            onClick={() =>
              a.kind === "ask" && a.prompt ? onAsk(a.prompt) : a.link && navigate(a.link)
            }
            disabled={busy && a.kind === "ask"}
            title={a.prompt ?? a.label}
            className="group flex min-w-0 flex-col items-start gap-1.5 rounded-xl bg-navy-950/70 p-2.5 text-left ring-1 ring-white/[0.07] transition-colors hover:bg-white/[0.04] hover:ring-white/15 disabled:opacity-50"
          >
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-white/5 text-slate-300">
              {ICONS[a.icon]}
            </span>
            <span className="w-full min-w-0">
              <span className="block text-xs font-medium text-slate-100">{a.label}</span>
              <span className="block truncate text-[11px] text-slate-500">{a.detail}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
