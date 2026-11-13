import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { CheckIcon, CodeIcon, FileIcon, SparkleIcon, UsersIcon } from "./icons";

/** One department's task as it moves through UNIFY (fictional sample data, for the sign-in page). */
interface Story {
  department: string;
  kind: string;
  title: string;
  meta: string;
  aiRead: string;
  codeCheck: string;
  approver: string;
  result: string;
}

const STORIES: Story[] = [
  {
    department: "Finance",
    kind: "Supplier invoice",
    title: "ACME Industrial Supplies",
    meta: "INV-2026-0042 · $4,250.00",
    aiRead: "Vendor, total and PO number found",
    codeCheck: "Matches PO-1007, not a duplicate",
    approver: "finance manager",
    result: "Payment recorded",
  },
  {
    department: "Hiring",
    kind: "Resume",
    title: "Sara Malik",
    meta: "Applied for Data Analyst",
    aiRead: "Skills quoted from the resume",
    codeCheck: "Meets every must-have skill",
    approver: "hiring manager",
    result: "Interview invite sent",
  },
  {
    department: "Sales",
    kind: "New lead",
    title: "Karachi Logistics",
    meta: "Inbound · fleet of 120 trucks",
    aiRead: "Hot lead, outreach email drafted",
    codeCheck: "Email passes the quality check",
    approver: "sales manager",
    result: "Outreach email sent",
  },
  {
    department: "Support",
    kind: "Support ticket",
    title: "Refund request",
    meta: "Order SO-1101 · billing",
    aiRead: "Billing issue, high priority",
    codeCheck: "Refunds need a manager: escalate",
    approver: "support manager",
    result: "Escalation approved",
  },
  {
    department: "Procurement",
    kind: "Purchase request",
    title: "40 ergonomic chairs",
    meta: "Budget $12,000",
    aiRead: "Explains the ranking of three quotes",
    codeCheck: "Indus Furniture ranks best",
    approver: "procurement manager",
    result: "Purchase order created",
  },
];

/* Stages of one story: 0 card arrives · 1 AI reading · 2 code checking · 3 waiting for a person ·
   4 approved · 5 result shown · 6 card leaves. How long each stage holds before the next (ms). */
const HOLD = [450, 900, 900, 1500, 450, 2600, 200];
const LAST_STAGE = HOLD.length - 1;

function useReducedMotion(): boolean {
  const query = "(prefers-reduced-motion: reduce)";
  const [reduced, setReduced] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

function usePageVisible(): boolean {
  const [visible, setVisible] = useState(() => !document.hidden);
  useEffect(() => {
    const onChange = () => setVisible(!document.hidden);
    document.addEventListener("visibilitychange", onChange);
    return () => document.removeEventListener("visibilitychange", onChange);
  }, []);
  return visible;
}

type StepState = "pending" | "active" | "waiting" | "done";

function Step({
  icon,
  label,
  state,
  detail,
  last = false,
}: {
  icon: ReactNode;
  label: string;
  state: StepState;
  detail: string;
  last?: boolean;
}) {
  const tile = {
    pending: "bg-white/[0.04] text-slate-500",
    active: "bg-accent-purple/20 text-accent-soft",
    waiting: "bg-amber-400/15 text-amber-300",
    done: "bg-emerald-400/15 text-emerald-300",
  }[state];
  return (
    <li className="relative flex gap-3 pb-4 last:pb-0">
      {!last && (
        <span
          className="absolute top-9 bottom-1 left-[15px] w-px bg-white/[0.06]"
          aria-hidden="true"
        >
          {state === "done" && (
            <span className="anim-grow-down block h-full w-full bg-emerald-400/40" />
          )}
        </span>
      )}
      <span
        className={`relative grid h-8 w-8 shrink-0 place-items-center rounded-lg transition-colors duration-200 ${tile}`}
      >
        {state === "done" ? (
          <CheckIcon size={16} className="anim-draw" />
        ) : (
          <span className={state === "active" || state === "waiting" ? "anim-working" : ""}>
            {icon}
          </span>
        )}
      </span>
      <div className="min-w-0 flex-1 pt-0.5">
        <p
          className={`text-[13px] font-medium transition-colors duration-200 ${
            state === "pending" ? "text-slate-500" : "text-slate-100"
          }`}
        >
          {label}
        </p>
        <div className="mt-1 h-4 text-xs">
          {state === "pending" && <span className="block h-2 w-40 rounded bg-white/[0.05]" />}
          {state === "active" && <span className="anim-fade text-accent-soft">Working…</span>}
          {(state === "waiting" || state === "done") && (
            <span
              key={state}
              className={`anim-rise block truncate ${state === "waiting" ? "text-amber-200" : "text-slate-400"}`}
              style={{ "--rise": "4px" } as CSSProperties}
            >
              {detail}
            </span>
          )}
        </div>
      </div>
    </li>
  );
}

/** The sign-in page's moving picture: one task per department, read by AI, checked by code,
 *  approved by a person. It loops, pauses in a hidden tab and stands still for reduced motion. */
export function LoginShowcase() {
  const reduced = useReducedMotion();
  const visible = usePageVisible();
  const [story, setStory] = useState(0);
  const [stage, setStage] = useState(0);
  const shownStage = reduced ? 5 : stage;

  useEffect(() => {
    if (reduced || !visible) return;
    const id = window.setTimeout(() => {
      if (stage < LAST_STAGE) {
        setStage(stage + 1);
      } else {
        setStory((s) => (s + 1) % STORIES.length);
        setStage(0);
      }
    }, HOLD[stage]);
    return () => window.clearTimeout(id);
  }, [stage, reduced, visible]);

  const pick = (i: number) => {
    setStory(i);
    setStage(0);
  };

  const s = STORIES[story];
  const stepState = (doneAt: number, activeAt: number, waiting = false): StepState => {
    if (shownStage >= doneAt) return "done";
    if (shownStage >= activeAt) return waiting ? "waiting" : "active";
    return "pending";
  };
  const human = stepState(4, 3, true);

  return (
    <div className="flex flex-col gap-4">
      <div className="relative h-[332px]">
        <article
          key={story}
          aria-hidden="true"
          className={`absolute inset-0 rounded-2xl border border-white/10 bg-navy-950 p-5 shadow-2xl shadow-black/40 ${
            shownStage === LAST_STAGE ? "anim-fade-out" : "anim-rise"
          }`}
          style={{ "--rise": "10px" } as CSSProperties}
        >
          <header className="flex items-start gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white/[0.06] text-slate-300">
              <FileIcon size={18} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-medium tracking-wide text-accent-soft uppercase">
                {s.department} · {s.kind}
              </p>
              <p className="truncate text-[15px] font-semibold text-white">{s.title}</p>
              <p className="truncate text-xs text-slate-500">{s.meta}</p>
            </div>
          </header>
          <ol className="mt-5">
            <Step
              icon={<SparkleIcon size={16} />}
              label="AI reads it"
              state={stepState(2, 1)}
              detail={s.aiRead}
            />
            <Step
              icon={<CodeIcon size={16} />}
              label="Code checks it"
              state={stepState(3, 2)}
              detail={s.codeCheck}
            />
            <Step
              icon={<UsersIcon size={16} />}
              label="A person decides"
              state={human}
              detail={
                human === "waiting"
                  ? `Waiting for the ${s.approver}`
                  : `Approved by the ${s.approver}`
              }
              last
            />
          </ol>
          <div className="mt-4 h-9">
            {shownStage >= 5 && (
              <p className="anim-rise flex h-9 items-center gap-2 rounded-lg bg-emerald-400/10 px-3 text-[13px] font-medium text-emerald-200">
                <CheckIcon size={15} className="anim-draw" />
                {s.result}
              </p>
            )}
          </div>
        </article>
      </div>

      <div
        className="flex flex-wrap gap-1.5"
        role="group"
        aria-label="Show an example from a department"
      >
        {STORIES.map((x, i) => (
          <button
            key={x.department}
            type="button"
            onClick={() => pick(i)}
            aria-pressed={i === story}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-[background-color,color,transform] duration-200 active:scale-[0.96] motion-reduce:active:scale-100 ${
              i === story
                ? "bg-white text-violet-800"
                : "bg-white/10 text-violet-100 hover:bg-white/20"
            }`}
          >
            {x.department}
          </button>
        ))}
      </div>
    </div>
  );
}
