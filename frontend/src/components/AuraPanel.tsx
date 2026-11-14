import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
} from "react";
import { Link } from "react-router";
import { api } from "../api";
import { label } from "../format";
import { useAuth } from "../session";
import type { AuraReply, Overview } from "../types";
import { AuraBrief } from "./AuraBrief";
import { Orb } from "./AuraOrb";
import { ArrowRight, MicIcon, SendIcon } from "./icons";
import { QuickActions } from "./QuickActions";
import { useVoice } from "./useVoice";

interface Turn {
  question: string;
  answer: AuraReply | null;
  error: string | null;
}

const OUTCOME_TONE: Record<AuraReply["outcome"], string> = {
  done: "text-emerald-300",
  needs_input: "text-amber-200",
  not_found: "text-amber-200",
  not_allowed: "text-red-300",
  failed: "text-red-300",
  no_route: "text-slate-400",
};

function SystemStatus({ agents }: { agents?: Overview["agents"] }) {
  const healthy = !agents || agents.failed === 0 || agents.succeeded >= agents.failed;
  const rate = agents?.calls ? Math.round((100 * agents.succeeded) / agents.calls) : null;
  return (
    <div className="flex items-center gap-3 border-t border-white/5 px-4 py-3">
      <span
        className={`h-2 w-2 shrink-0 rounded-full ${healthy ? "bg-emerald-400" : "bg-amber-400"}`}
      />
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
export function AuraPanel({
  agents,
  chatOnly = false,
}: {
  agents?: Overview["agents"];
  /** Only the chat: no brief, shortcuts or status (those are the dashboard's, for leaders). */
  chatOnly?: boolean;
}) {
  const { user } = useAuth();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const onVoice = useCallback((text: string) => setMessage(text.slice(0, 1000)), []);
  const voice = useVoice(onVoice);

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
      className="flex flex-col self-start overflow-hidden rounded-2xl border border-white/[0.07] bg-navy-900/80 card-shadow xl:sticky xl:top-20 xl:max-h-[calc(100vh-6rem)]"
    >
      <div className="border-b border-white/5 px-5 py-4">
        <div className="flex items-center gap-3">
          <Orb size={34} />
          <div>
            <h2 className="text-base font-semibold text-white">Aura</h2>
            <p className="text-xs text-slate-400">
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
        {user && !chatOnly && <AuraBrief userId={user.id} />}
        {chatOnly && turns.length === 0 && (
          <p className="text-slate-400">
            Ask in plain words, for example “investigate the ticket about the late order” or “is the
            Sultan Tiles lead worth chasing?”. Aura runs the right agent with your permissions.
          </p>
        )}
        {turns.map((turn, i) => (
          <div key={i} className="space-y-2">
            <p className="anim-pop ml-8 rounded-2xl rounded-tr-sm bg-accent-purple/25 px-3 py-2 text-slate-100">
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
                        className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent-soft"
                        style={{ animationDelay: `${d}ms` }}
                      />
                    ))}
                  </span>
                )}
                {turn.error && <p className="text-red-300">{turn.error}</p>}
                {turn.answer && (
                  <div
                    className="anim-rise space-y-1.5"
                    style={{ "--rise": "4px" } as CSSProperties}
                  >
                    <p className="text-slate-200">{turn.answer.reply}</p>
                    <p className={OUTCOME_TONE[turn.answer.outcome]}>{turn.answer.summary}</p>
                    <p className="flex flex-wrap items-center gap-2 pt-0.5 text-[11px]">
                      <span className="rounded-full bg-accent-soft/10 px-2 py-0.5 text-accent-soft">
                        {turn.answer.agent ? label(turn.answer.agent) : "no agent"}
                      </span>
                      {turn.answer.link && (
                        <Link
                          to={turn.answer.link}
                          className="flex items-center gap-1 text-slate-400 hover:text-accent-soft"
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
          className="w-full rounded-full border border-white/10 bg-navy-950 px-4 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-accent-soft/60 focus:outline-none"
          placeholder={voice.listening ? "Listening…" : "Ask Aura…"}
          aria-label="Message to Aura"
          value={message}
          maxLength={1000}
          onChange={(e) => setMessage(e.target.value)}
        />
        {voice.supported && (
          <button
            type="button"
            onClick={voice.toggle}
            aria-label={voice.listening ? "Stop listening" : "Speak to Aura"}
            aria-pressed={voice.listening}
            title={voice.listening ? "Stop listening" : "Speak to Aura"}
            className={`grid h-9 w-9 shrink-0 place-items-center rounded-full border transition ${
              voice.listening
                ? "animate-pulse border-red-400/60 bg-red-500/20 text-red-200"
                : "border-white/10 text-slate-300 hover:border-accent-soft/50 hover:text-white"
            }`}
          >
            <MicIcon size={16} />
          </button>
        )}
        <button
          type="submit"
          disabled={busy || !message.trim()}
          aria-label="Send"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent-purple text-on-accent transition-colors hover:bg-accent-purple/85 disabled:opacity-40"
        >
          <SendIcon size={16} />
        </button>
      </form>
      {voice.error && <p className="-mt-1 px-5 pb-2 text-xs text-amber-200">{voice.error}</p>}
      {!chatOnly && <QuickActions onAsk={(prompt) => void ask(prompt)} busy={busy} />}
      {!chatOnly && <SystemStatus agents={agents} />}
    </aside>
  );
}
