import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api } from "../api";
import { label } from "../format";
import { useAuth } from "../session";
import type { AuraReply, Overview } from "../types";
import { ArrowRight, SendIcon, SparkleIcon } from "./icons";

interface Turn {
  question: string;
  answer: AuraReply | null;
  error: string | null;
}

const EXAMPLES = [
  "Is the Karachi Logistics lead worth chasing?",
  "Rank the applicants for Senior Backend Engineer",
  "Which supplier should we buy the laptops from?",
];

const OUTCOME_TONE: Record<AuraReply["outcome"], string> = {
  done: "text-emerald-300",
  needs_input: "text-amber-200",
  not_found: "text-amber-200",
  not_allowed: "text-red-300",
  failed: "text-red-300",
  no_route: "text-slate-400",
};

function Orb({ size = 40 }: { size?: number }) {
  return (
    <span
      className="aura-orb relative grid shrink-0 place-items-center rounded-full"
      style={{
        width: size,
        height: size,
        background:
          "radial-gradient(circle at 35% 30%, #e0f2fe 0%, #22d3ee 28%, #8b5cf6 70%, #4c1d95 100%)",
        boxShadow: "0 0 24px rgb(34 211 238 / 0.45), 0 0 48px rgb(139 92 246 / 0.35)",
      }}
      aria-hidden="true"
    >
      <SparkleIcon size={size * 0.45} className="text-white/90" />
    </span>
  );
}

function SystemStatus({ agents }: { agents?: Overview["agents"] }) {
  const healthy = !agents || agents.failed === 0 || agents.succeeded >= agents.failed;
  const rate = agents?.calls ? Math.round((100 * agents.succeeded) / agents.calls) : null;
  return (
    <div className="flex items-center gap-3 border-t border-white/5 px-4 py-3">
      <span className="relative flex h-2.5 w-2.5">
        <span
          className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-50 ${
            healthy ? "bg-emerald-400" : "bg-amber-400"
          }`}
        />
        <span
          className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
            healthy ? "bg-emerald-400" : "bg-amber-400"
          }`}
        />
      </span>
      <div className="min-w-0 text-xs leading-snug">
        <p className="text-slate-200">AI system status: {healthy ? "active" : "degraded"}</p>
        <p className="truncate text-slate-500">
          {agents
            ? `${agents.calls} calls in 24 h${rate !== null ? ` · ${rate}% ok` : ""}`
            : "checking…"}{" "}
          · Vultr Serverless Inference
        </p>
      </div>
    </div>
  );
}

/** Aura: one chat box that hands each request to the right department agent. */
export function AuraPanel({ agents }: { agents?: Overview["agents"] }) {
  const { user } = useAuth();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const ask = async (text: string) => {
    if (!text.trim()) return;
    setBusy(true);
    setMessage("");
    const index = turns.length;
    setTurns((t) => [...t, { question: text, answer: null, error: null }]);
    try {
      const answer = await api<AuraReply>("/ai/chat", {
        method: "POST",
        body: JSON.stringify({ message: text }),
      });
      setTurns((t) => t.map((turn, i) => (i === index ? { ...turn, answer } : turn)));
    } catch (err) {
      const error = err instanceof Error ? err.message : "Aura is unavailable";
      setTurns((t) => t.map((turn, i) => (i === index ? { ...turn, error } : turn)));
    } finally {
      setBusy(false);
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void ask(message);
  };

  return (
    <aside
      data-tour="aura"
      className="flex flex-col self-start overflow-hidden rounded-2xl border border-accent-purple/30 bg-navy-900/90 shadow-[0_0_40px] shadow-accent-purple/10 xl:sticky xl:top-20 xl:max-h-[calc(100vh-6rem)]"
    >
      <div className="relative overflow-hidden bg-gradient-to-br from-accent-purple via-fuchsia-600/80 to-accent-cyan px-5 py-4">
        <div className="absolute -top-10 -right-8 h-32 w-32 rounded-full bg-white/10 blur-2xl" />
        <div className="relative flex items-center gap-3">
          <Orb />
          <div>
            <h2 className="text-base font-semibold text-white">Aura</h2>
            <p className="text-xs text-white/80">
              AI assistant · hands your request to the right agent
            </p>
          </div>
        </div>
      </div>

      <div
        ref={scroller}
        className="min-h-48 flex-1 space-y-4 overflow-y-auto px-4 py-4 text-sm"
        style={{ maxHeight: 460 }}
        aria-live="polite"
      >
        {turns.length === 0 && (
          <div className="space-y-3">
            <div className="flex gap-2.5">
              <Orb size={26} />
              <p className="rounded-2xl rounded-tl-sm bg-navy-800/80 px-3 py-2 text-slate-200">
                Hi {user?.full_name.split(" ")[0] ?? "there"}. Ask me about a lead, an applicant, a
                supplier or a ticket and I&apos;ll run the right agent for you.
              </p>
            </div>
            <div className="space-y-1.5 pl-9">
              {EXAMPLES.map((e) => (
                <button
                  key={e}
                  onClick={() => void ask(e)}
                  disabled={busy}
                  className="block w-full rounded-xl border border-white/10 px-3 py-2 text-left text-xs text-slate-300 transition hover:border-accent-cyan/50 hover:bg-white/[0.03] hover:text-white"
                >
                  {e}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((turn, i) => (
          <div key={i} className="space-y-2">
            <p className="ml-8 rounded-2xl rounded-tr-sm bg-gradient-to-r from-accent-purple/40 to-accent-purple/25 px-3 py-2 text-slate-100">
              {turn.question}
            </p>
            <div className="flex gap-2.5">
              <Orb size={26} />
              <div className="min-w-0 flex-1 rounded-2xl rounded-tl-sm bg-navy-800/80 px-3 py-2">
                {!turn.answer && !turn.error && (
                  <span className="flex gap-1 py-1" aria-label="Aura is thinking">
                    {[0, 150, 300].map((d) => (
                      <span
                        key={d}
                        className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent-cyan"
                        style={{ animationDelay: `${d}ms` }}
                      />
                    ))}
                  </span>
                )}
                {turn.error && <p className="text-red-300">{turn.error}</p>}
                {turn.answer && (
                  <div className="space-y-1.5">
                    <p className="text-slate-200">{turn.answer.reply}</p>
                    <p className={OUTCOME_TONE[turn.answer.outcome]}>{turn.answer.summary}</p>
                    <p className="flex flex-wrap items-center gap-2 pt-0.5 text-[11px]">
                      <span className="rounded-full bg-accent-cyan/10 px-2 py-0.5 text-accent-cyan">
                        {turn.answer.agent ? label(turn.answer.agent) : "no agent"}
                      </span>
                      {turn.answer.link && (
                        <Link
                          to={turn.answer.link}
                          className="flex items-center gap-1 text-slate-400 hover:text-accent-cyan"
                        >
                          Open <ArrowRight size={12} />
                        </Link>
                      )}
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      <form onSubmit={submit} className="flex gap-2 border-t border-white/5 px-4 py-3">
        <input
          className="w-full rounded-full border border-white/10 bg-navy-950 px-4 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-accent-cyan/60 focus:outline-none"
          placeholder="Ask Aura…"
          aria-label="Message to Aura"
          value={message}
          maxLength={1000}
          onChange={(e) => setMessage(e.target.value)}
        />
        <button
          type="submit"
          disabled={busy || !message.trim()}
          aria-label="Send"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-accent-purple to-accent-cyan text-white transition hover:opacity-90 disabled:opacity-40"
        >
          <SendIcon size={16} />
        </button>
      </form>
      <SystemStatus agents={agents} />
    </aside>
  );
}
