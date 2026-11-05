import { useCallback, useRef, useState } from "react";
import { Link } from "react-router";
import { approvalHeadline } from "../approvalText";
import { ago, initials, label } from "../format";
import { useAuth } from "../session";
import type { Approval, Page } from "../types";
import { usePoll } from "../usePoll";
import { BellIcon, ChevronDown, LogoutIcon } from "./icons";
import { useDismiss } from "./useDismiss";

const BELL_ITEMS = 6;

const popover =
  "absolute right-0 z-50 mt-2 overflow-hidden rounded-xl border border-white/10 bg-navy-900 shadow-2xl shadow-black/50";

/** Bell with the number of decisions waiting (what this user may see in the Approval Center). */
export function NotificationBell() {
  const { data } = usePoll<Page<Approval>>(`/approvals?status=pending&limit=${BELL_ITEMS}`);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(box, open, close);

  const items = data?.items ?? [];
  const count = items.length ? `${items.length}${data?.next_cursor ? "+" : ""}` : "";

  return (
    <div ref={box} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={count ? `${count} approvals waiting` : "No approvals waiting"}
        aria-expanded={open}
        className="relative grid h-9 w-9 place-items-center rounded-full text-slate-300 hover:bg-white/5 hover:text-white"
      >
        <BellIcon />
        {count && (
          <span className="absolute -top-0.5 -right-0.5 grid min-w-[18px] place-items-center rounded-full bg-gradient-to-r from-accent-purple to-fuchsia-500 px-1 text-[10px] leading-[18px] font-semibold text-white shadow-[0_0_10px] shadow-accent-purple/60">
            {count}
          </span>
        )}
      </button>
      {open && (
        <div className={`${popover} w-80 max-w-[calc(100vw-2rem)]`}>
          <p className="border-b border-white/5 px-4 py-3 text-xs font-semibold tracking-wide text-slate-400 uppercase">
            Waiting for a decision
          </p>
          {items.length === 0 && (
            <p className="px-4 py-6 text-center text-sm text-slate-500">Nothing is waiting.</p>
          )}
          <ul className="max-h-80 divide-y divide-white/5 overflow-y-auto">
            {items.map((a) => {
              const { title, detail } = approvalHeadline(a);
              return (
                <li key={a.id}>
                  <Link
                    to="/approvals"
                    onClick={close}
                    className="block px-4 py-3 hover:bg-white/5"
                  >
                    <span className="block truncate text-sm text-slate-100">{title}</span>
                    <span className="mt-0.5 flex justify-between gap-2 text-xs text-slate-500">
                      <span className="truncate">
                        {a.department} · {detail}
                      </span>
                      <span className="shrink-0">{ago(a.created_at)}</span>
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
          <Link
            to="/approvals"
            onClick={close}
            className="block border-t border-white/5 px-4 py-2.5 text-center text-sm text-accent-cyan hover:bg-white/5"
          >
            Open the Approval Center
          </Link>
        </div>
      )}
    </div>
  );
}

export function Avatar({ name, size = 32 }: { name: string; size?: number }) {
  return (
    <span
      style={{ width: size, height: size, fontSize: size * 0.38 }}
      className="grid shrink-0 place-items-center rounded-full bg-gradient-to-br from-accent-purple to-accent-cyan font-semibold text-white"
    >
      {initials(name)}
    </span>
  );
}

export function UserMenu() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(box, open, close);
  if (!user) return null;

  return (
    <div ref={box} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label="Account menu"
        className="flex items-center gap-2 rounded-full py-1 pr-2 pl-1 hover:bg-white/5"
      >
        <Avatar name={user.full_name} />
        <span className="hidden text-left leading-tight 2xl:block">
          <span className="block text-sm text-slate-100">{user.full_name}</span>
          <span className="block text-[11px] text-slate-500 capitalize">
            {label(user.role)} · {user.department}
          </span>
        </span>
        <ChevronDown size={14} className="text-slate-400" />
      </button>
      {open && (
        <div className={`${popover} w-64`}>
          <div className="flex items-center gap-3 border-b border-white/5 px-4 py-3">
            <Avatar name={user.full_name} size={38} />
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-white">{user.full_name}</p>
              <p className="truncate text-xs text-slate-500">{user.email}</p>
              <p className="mt-1 text-xs text-accent-cyan capitalize">
                {label(user.role)} · {user.department}
              </p>
            </div>
          </div>
          <button
            onClick={signOut}
            className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-slate-300 hover:bg-white/5 hover:text-white"
          >
            <LogoutIcon size={16} /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}
