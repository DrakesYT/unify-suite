import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api } from "../api";
import type { AuraReply } from "../types";
import { inputClass, primaryButton } from "./ui";

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

export function AuraPanel() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

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
    <aside className="flex flex-col self-start rounded-xl xl:sticky xl:top-6 border border-accent-purple/30 bg-gradient-to-b from-navy-900 to-navy-950 p-5">
      <div className="mb-3 flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full bg-accent-cyan shadow-[0_0_10px] shadow-accent-cyan" />
        <h2 className="font-semibold text-white">Aura</h2>
        <span className="text-xs text-slate-500">routes your request to the right agent</span>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto pr-1 text-sm" style={{ maxHeight: 420 }}>
        {turns.length === 0 && (
          <div className="space-y-2">
            <p className="text-slate-400">Try one of these:</p>
            {EXAMPLES.map((e) => (
              <button
                key={e}
                onClick={() => void ask(e)}
                disabled={busy}
                className="block w-full rounded-lg border border-navy-800 px-3 py-2 text-left text-slate-300 hover:border-accent-purple/50 hover:text-white"
              >
                {e}
              </button>
            ))}
          </div>
        )}
        {turns.map((turn, i) => (
          <div key={i} className="space-y-2">
            <p className="ml-6 rounded-lg bg-accent-purple/20 px-3 py-2 text-slate-100">
              {turn.question}
            </p>
            {!turn.answer && !turn.error && <p className="text-slate-500">Thinking…</p>}
            {turn.error && <p className="text-red-300">{turn.error}</p>}
            {turn.answer && (
              <div className="mr-6 space-y-1 rounded-lg bg-navy-800/60 px-3 py-2">
                <p className="text-slate-200">{turn.answer.reply}</p>
                <p className={OUTCOME_TONE[turn.answer.outcome]}>{turn.answer.summary}</p>
                <p className="text-xs text-slate-500">
                  {turn.answer.agent ?? "no agent"}
                  {turn.answer.link && (
                    <>
                      {" · "}
                      <Link to={turn.answer.link} className="text-accent-cyan hover:underline">
                        open
                      </Link>
                    </>
                  )}
                </p>
              </div>
            )}
          </div>
        ))}
      </div>
      <form onSubmit={submit} className="mt-4 flex gap-2">
        <input
          className={inputClass}
          placeholder="Ask Aura…"
          value={message}
          maxLength={1000}
          onChange={(e) => setMessage(e.target.value)}
        />
        <button type="submit" disabled={busy || !message.trim()} className={primaryButton}>
          Send
        </button>
      </form>
    </aside>
  );
}
