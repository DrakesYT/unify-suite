import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router";
import { api } from "../api";
import type { SearchHit } from "../types";
import { SearchIcon } from "./icons";
import { useDismiss } from "./useDismiss";

const MIN_CHARS = 2;
const DEBOUNCE_MS = 250;
const KIND_LABEL: Record<string, string> = {
  lead: "Lead",
  job: "Job",
  candidate: "Candidate",
  ticket: "Ticket",
  vendor: "Vendor",
  purchase_order: "PO",
  invoice: "Invoice",
  order: "Order",
};

/** Top-bar search across every department the user may read. Press "/" to jump here. */
export function SearchBox({ onNavigate }: { onNavigate?: () => void }) {
  const navigate = useNavigate();
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [term, setTerm] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(box, open, close);

  const query = term.trim();
  useEffect(() => {
    if (query.length < MIN_CHARS) return;
    let live = true;
    const timer = setTimeout(async () => {
      try {
        const found = await api<SearchHit[]>(`/search?q=${encodeURIComponent(query)}`);
        if (!live) return;
        setHits(found);
        setError(null);
        setActive(0);
      } catch (e) {
        if (live) setError(e instanceof Error ? e.message : "Search failed");
      }
    }, DEBOUNCE_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [query]);

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const typing = target.closest("input, textarea, select, [contenteditable=true]");
      if (e.key === "/" && !typing && input.current?.offsetParent) {
        e.preventDefault();
        input.current.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const shown = query.length >= MIN_CHARS ? hits : null;
  const go = (hit: SearchHit) => {
    setOpen(false);
    setTerm("");
    setHits(null);
    input.current?.blur();
    onNavigate?.();
    navigate(hit.link);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!shown?.length) return;
    const step = { ArrowDown: 1, ArrowUp: -1 }[e.key];
    if (step) {
      e.preventDefault();
      setActive((i) => (i + step + shown.length) % shown.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      go(shown[Math.min(active, shown.length - 1)]);
    }
  };

  return (
    <div ref={box} className="relative w-full">
      <label className="flex items-center gap-2 rounded-full border border-white/10 bg-navy-900/80 px-3 py-1.5 text-slate-400 focus-within:border-accent-soft/60 focus-within:text-slate-200">
        <SearchIcon size={16} />
        <input
          ref={input}
          type="search"
          value={term}
          maxLength={80}
          placeholder="Search leads, tickets, POs…"
          aria-label="Search"
          onChange={(e) => {
            setTerm(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          className="w-full bg-transparent text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none [&::-webkit-search-cancel-button]:hidden"
        />
        <kbd className="hidden rounded border border-white/10 px-1.5 text-[10px] text-slate-500 lg:inline">
          /
        </kbd>
      </label>
      {open && query.length >= MIN_CHARS && (
        <div className="anim-pop absolute right-0 z-50 mt-2 w-full min-w-72 overflow-hidden rounded-xl border border-white/10 bg-navy-900 shadow-2xl shadow-black/50">
          {error && <p className="px-4 py-3 text-sm text-red-300">{error}</p>}
          {!error && shown === null && (
            <p className="px-4 py-3 text-sm text-slate-500">Searching…</p>
          )}
          {!error && shown?.length === 0 && (
            <p className="px-4 py-3 text-sm text-slate-500">Nothing matches “{query}”.</p>
          )}
          <ul role="listbox" className="max-h-96 overflow-y-auto py-1">
            {shown?.map((hit, i) => (
              <li
                key={`${hit.kind}-${hit.link}-${hit.title}`}
                role="option"
                aria-selected={i === active}
              >
                <button
                  onMouseEnter={() => setActive(i)}
                  onClick={() => go(hit)}
                  className={`flex w-full items-center gap-3 px-4 py-2 text-left ${
                    i === active ? "bg-accent-purple/15" : ""
                  }`}
                >
                  <span className="w-16 shrink-0 text-[10px] font-semibold text-accent-soft">
                    {KIND_LABEL[hit.kind] ?? hit.kind}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm text-slate-100">{hit.title}</span>
                    <span className="block truncate text-xs text-slate-500">{hit.subtitle}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
