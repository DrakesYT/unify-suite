import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router";
import { label } from "../format";
import { isDemo, useAuth } from "../session";
import { demoEmail, TOUR_STEPS, TourContext, useTour } from "../tourSteps";
import { CloseIcon, PlayIcon } from "./icons";

const SEEN_KEY = "unify.tour-offered";
const CARD_W = 360;
const CARD_H = 250; // close enough to place the card; it never needs to be exact
const GAP = 16;
const PAD = 8;

function readSeen(): boolean {
  try {
    return localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return false;
  }
}

function markSeen(): void {
  try {
    localStorage.setItem(SEEN_KEY, "1");
  } catch {
    // Blocked storage: the invitation simply shows again next time.
  }
}

/** Runs the guided tour: each step signs in as the step's demo account, then opens its page. */
export function TourProvider({ children }: { children: ReactNode }) {
  const { user, switchTo } = useAuth();
  const navigate = useNavigate();
  const [index, setIndex] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const goTo = useCallback(
    async (next: number) => {
      const step = TOUR_STEPS[next];
      setBusy(true);
      setError(null);
      try {
        if (user?.email !== demoEmail(step.as)) await switchTo(demoEmail(step.as));
        navigate(step.path);
        setIndex(next);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not switch to the demo account");
      } finally {
        setBusy(false);
      }
    },
    [user, switchTo, navigate],
  );

  const start = useCallback(() => {
    markSeen();
    void goTo(0);
  }, [goTo]);
  const end = useCallback(() => {
    setIndex(null);
    setError(null);
  }, []);

  return (
    <TourContext.Provider value={{ index, busy, error, start, goTo: (i) => void goTo(i), end }}>
      {children}
      {index !== null && <TourOverlay />}
    </TourContext.Provider>
  );
}

function useTargetRect(selector: string) {
  const [rect, setRect] = useState<DOMRect | null>(null);
  const scrolled = useRef<string | null>(null);
  useEffect(() => {
    const read = () => {
      const el = document.querySelector(selector);
      if (!el) return setRect(null);
      if (scrolled.current !== selector) {
        scrolled.current = selector;
        const tall = el.getBoundingClientRect().height > window.innerHeight * 0.6;
        el.scrollIntoView({ behavior: "smooth", block: tall ? "start" : "center" });
      }
      setRect(el.getBoundingClientRect());
    };
    read();
    const timer = setInterval(read, 200); // pages load data and scroll; follow the element
    return () => clearInterval(timer);
  }, [selector]);
  return rect;
}

function cardPosition(rect: DOMRect | null): CSSProperties {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  if (vw < 640) return { left: 12, right: 12, bottom: 12 };
  const width = Math.min(CARD_W, vw - 2 * GAP);
  const clampX = (x: number) => Math.max(GAP, Math.min(x, vw - width - GAP));
  const clampY = (y: number) => Math.max(GAP + 64, Math.min(y, vh - CARD_H - GAP));
  if (!rect) return { width, left: (vw - width) / 2, top: vh / 2 - CARD_H / 2 };
  if (rect.bottom + PAD + GAP + CARD_H < vh)
    return { width, left: clampX(rect.left), top: rect.bottom + PAD + GAP };
  if (rect.top - PAD - GAP - CARD_H > 64)
    return { width, left: clampX(rect.left), top: rect.top - PAD - GAP - CARD_H };
  if (rect.left - PAD - GAP - width > 0)
    return { width, left: rect.left - PAD - GAP - width, top: clampY(rect.top) };
  return { width, left: clampX(rect.left + GAP), top: vh - CARD_H - GAP };
}

function TourOverlay() {
  const { user } = useAuth();
  const { index, busy, error, goTo, end } = useTour();
  const step = TOUR_STEPS[index ?? 0];
  const rect = useTargetRect(step.target);
  const last = index === TOUR_STEPS.length - 1;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") end();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [end]);

  if (index === null) return null;
  return (
    <>
      {rect ? (
        <div
          aria-hidden="true"
          className="pointer-events-none fixed z-[60] rounded-2xl ring-2 ring-accent-purple transition-all duration-300 ease-[var(--ease-out)] motion-reduce:transition-none"
          style={{
            top: rect.top - PAD,
            left: rect.left - PAD,
            width: rect.width + 2 * PAD,
            height: rect.height + 2 * PAD,
            boxShadow: "0 0 0 9999px rgb(4 7 18 / 0.68)",
          }}
        />
      ) : (
        <div
          aria-hidden="true"
          className="pointer-events-none fixed inset-0 z-[60] bg-[#040712]/70"
        />
      )}
      <div
        key={index}
        role="dialog"
        aria-label={`Tour step ${index + 1} of ${TOUR_STEPS.length}`}
        className="anim-pop fixed z-[61] rounded-2xl [--origin:center] border border-accent-soft/30 bg-navy-900 p-5 shadow-2xl shadow-black/60"
        style={cardPosition(rect)}
      >
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold text-accent-soft">
            Step {index + 1} of {TOUR_STEPS.length}
          </span>
          <span className="flex flex-1 gap-1">
            {TOUR_STEPS.map((s, i) => (
              <span
                key={s.title}
                className={`h-1 flex-1 rounded-full ${i <= index ? "bg-accent-soft" : "bg-white/10"}`}
              />
            ))}
          </span>
          <button
            onClick={end}
            aria-label="End the tour"
            className="text-slate-500 hover:text-white"
          >
            <CloseIcon size={16} />
          </button>
        </div>
        {user && (
          <p className="mt-3 inline-block rounded-full bg-accent-purple/15 px-2.5 py-0.5 text-xs text-violet-200">
            Signed in as {user.full_name} · <span className="capitalize">{label(user.role)}</span>,{" "}
            {user.department}
          </p>
        )}
        <h3 className="mt-2 text-base font-semibold text-white">{step.title}</h3>
        <p className="mt-1 text-sm leading-relaxed text-slate-300">{step.body}</p>
        {error && <p className="mt-2 text-sm text-red-300">{error}</p>}
        <div className="mt-4 flex items-center justify-between gap-2">
          <button
            onClick={() => goTo(index - 1)}
            disabled={busy || index === 0}
            className="rounded-lg px-3 py-1.5 text-sm text-slate-400 hover:text-white disabled:invisible"
          >
            Back
          </button>
          <button
            onClick={() => (last ? end() : goTo(index + 1))}
            disabled={busy}
            className="rounded-lg bg-accent-purple px-4 py-1.5 text-sm font-medium text-white hover:bg-accent-purple/85 disabled:opacity-50"
          >
            {busy ? "Switching…" : last ? "Finish" : "Next"}
          </button>
        </div>
      </div>
    </>
  );
}

/** Top-bar button for demo accounts. */
export function TourButton() {
  const { user } = useAuth();
  const { index, start, busy } = useTour();
  if (!isDemo(user) || index !== null) return null;
  return (
    <button
      onClick={start}
      disabled={busy}
      className="flex h-9 items-center gap-1.5 rounded-full border border-white/10 px-3 text-sm text-slate-200 hover:bg-white/5"
    >
      <PlayIcon size={14} />
      <span className="hidden sm:inline">Tour</span>
    </button>
  );
}

/** Offered once per browser to anyone who signs in with a demo account. */
export function TourInvite() {
  const { user } = useAuth();
  const { index, start } = useTour();
  const [seen, setSeen] = useState(readSeen);
  if (!isDemo(user) || index !== null || seen) return null;
  const dismiss = () => {
    markSeen();
    setSeen(true);
  };
  return (
    <div className="anim-toast-in fixed right-4 bottom-4 left-4 z-50 rounded-2xl border border-white/10 bg-navy-900/95 p-4 shadow-2xl shadow-black/50 backdrop-blur sm:left-auto sm:w-80">
      <p className="flex items-center gap-2 text-sm font-semibold text-white">First time here?</p>
      <p className="mt-1 text-sm text-slate-300">
        Take the 2-minute guided tour. It switches between real demo roles so you can see the
        approval flow from both sides.
      </p>
      <div className="mt-3 flex gap-2">
        <button
          onClick={() => {
            dismiss();
            start();
          }}
          className="rounded-lg bg-accent-purple px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-purple/85"
        >
          Start the tour
        </button>
        <button onClick={dismiss} className="px-3 py-1.5 text-sm text-slate-400 hover:text-white">
          Not now
        </button>
      </div>
    </div>
  );
}
