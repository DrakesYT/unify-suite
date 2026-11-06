import { useState, type FormEvent } from "react";
import { api } from "../api";
import { when } from "../format";
import type { CallRecord } from "../types";
import { usePoll } from "../usePoll";
import { Badge, ErrorNote, ghostButton, inputClass, primaryButton } from "./ui";
import { WhyButton } from "./WhyDrawer";
import { toast } from "../toast";

const SPEAKER_COLORS = ["bg-accent-purple", "bg-accent-soft", "bg-amber-400", "bg-emerald-400"];

function AddCall({
  target,
  onAdded,
}: {
  target: { lead_id?: string; ticket_id?: string };
  onAdded: () => void;
}) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const form = new FormData();
    if (file) form.append("file", file);
    else form.append("text", text);
    if (title.trim()) form.append("title", title.trim());
    for (const [key, value] of Object.entries(target)) if (value) form.append(key, value);
    setBusy(true);
    setError(null);
    try {
      const call = await api<CallRecord>("/calls", { method: "POST", body: form });
      toast(
        call.analysis
          ? `Call analysed: ${call.analysis.sentiment}, ${call.analysis.action_items.length} action items`
          : "Transcript saved, but the analysis failed. You can analyse it again.",
        call.analysis ? "success" : "error",
      );
      setText("");
      setFile(null);
      setTitle("");
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add the call");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-2 rounded-lg border border-navy-800 p-3">
      <p className="text-xs text-slate-400">
        Paste the transcript or upload it (TXT or PDF). Lines like{" "}
        <code className="text-slate-300">Agent: …</code> /{" "}
        <code className="text-slate-300">Customer: …</code> let code count who talked how much.
      </p>
      <input
        className={inputClass}
        placeholder="Title (optional; taken from a 'Call:' line if there is one)"
        value={title}
        maxLength={200}
        onChange={(e) => setTitle(e.target.value)}
      />
      {!file && (
        <textarea
          className={`${inputClass} min-h-28 font-mono text-xs`}
          placeholder={"Agent: Hi Bilal, following up on your pricing question…\nCustomer: …"}
          value={text}
          maxLength={20000}
          onChange={(e) => setText(e.target.value)}
        />
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <input
          type="file"
          accept=".txt,.pdf"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="text-xs text-slate-400 file:mr-2 file:rounded-md file:border-0 file:bg-navy-800 file:px-2 file:py-1 file:text-slate-200"
        />
        <button type="submit" disabled={busy || (!file && !text.trim())} className={primaryButton}>
          {busy ? "Analysing…" : "Add and analyse"}
        </button>
      </div>
      <ErrorNote message={error} />
    </form>
  );
}

function CallCard({
  call,
  editable,
  onChange,
}: {
  call: CallRecord;
  editable: boolean;
  onChange: () => void;
}) {
  const [showText, setShowText] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const a = call.analysis;

  const retry = async () => {
    setBusy(true);
    setError(null);
    try {
      const again = await api<CallRecord>(`/calls/${call.id}/analyze`, { method: "POST" });
      toast(
        again.analysis ? "Call analysed" : "The analysis failed again",
        again.analysis ? "success" : "error",
      );
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not analyse");
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className="rounded-lg border border-navy-800 bg-navy-950/60 p-3 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium text-slate-100">{call.title}</p>
          <p className="text-xs text-slate-500">
            {call.file_name} · added {when(call.created_at)}
          </p>
        </div>
        <span className="flex items-center gap-1.5">
          {a && <Badge value={a.sentiment} />}
          {a && <WhyButton path={`call/${call.id}`} />}
        </span>
      </div>

      {call.speakers.length > 0 && (
        <div className="mt-3">
          <div className="flex h-1.5 overflow-hidden rounded-full bg-navy-800">
            {call.speakers.map((s, i) => (
              <span
                key={s.speaker}
                className={SPEAKER_COLORS[i % SPEAKER_COLORS.length]}
                style={{ width: `${s.share_pct}%` }}
              />
            ))}
          </div>
          <p className="mt-1 flex flex-wrap gap-x-3 text-[11px] text-slate-400">
            {call.speakers.map((s, i) => (
              <span key={s.speaker} className="flex items-center gap-1">
                <span
                  className={`h-2 w-2 rounded-full ${SPEAKER_COLORS[i % SPEAKER_COLORS.length]}`}
                />
                {s.speaker} {s.share_pct}% · {s.turns} turns
              </span>
            ))}
            <span className="text-slate-600">counted by code</span>
          </p>
        </div>
      )}

      {a && (
        <div className="mt-3 space-y-3">
          <p className="text-slate-200">{a.summary}</p>
          <p className="text-xs text-slate-400">
            Customer sentiment: <span className="text-slate-200">{a.sentiment}</span>, e.g.{" "}
            <q className="text-slate-300 italic">{a.sentiment_quote}</q>
          </p>
          {a.concerns.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {a.concerns.map((c) => (
                <span
                  key={c}
                  className="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs text-amber-200"
                >
                  {c}
                </span>
              ))}
            </div>
          )}
          <div>
            <p className="mb-1 text-xs font-semibold text-slate-400">Action items</p>
            {a.action_items.length === 0 && (
              <p className="text-xs text-slate-500">No one committed to a follow-up.</p>
            )}
            <ul className="space-y-1.5">
              {a.action_items.map((item) => (
                <li key={item.quote + item.task} className="flex gap-2">
                  <span
                    className={`mt-0.5 h-fit shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                      item.owner === "us"
                        ? "bg-accent-purple/20 text-violet-200"
                        : "bg-accent-soft/15 text-accent-soft"
                    }`}
                  >
                    {item.owner === "us" ? "We" : "Customer"}
                  </span>
                  <span className="min-w-0">
                    <span className="text-slate-100">{item.task}</span>
                    {item.due && <span className="text-amber-200"> · {item.due}</span>}
                    <span className="block text-xs text-slate-500 italic">“{item.quote}”</span>
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-[11px] text-slate-600">
              Suggestions only: nothing is sent or changed until someone acts on them.
            </p>
          </div>
        </div>
      )}

      {!a && call.analysis_error && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-red-500/10 px-3 py-2">
          <p className="text-xs text-red-200">Not analysed: {call.analysis_error}</p>
          {editable && (
            <button onClick={() => void retry()} disabled={busy} className={ghostButton}>
              {busy ? "Analysing…" : "Analyse again"}
            </button>
          )}
        </div>
      )}
      <ErrorNote message={error} />

      <button
        onClick={() => setShowText(!showText)}
        className="mt-3 text-xs text-slate-400 hover:text-white"
      >
        {showText ? "Hide transcript" : "Show transcript"}
      </button>
      {showText && (
        <pre className="mt-2 max-h-72 overflow-auto rounded-lg bg-navy-950 p-3 text-xs whitespace-pre-wrap text-slate-300">
          {call.transcript}
        </pre>
      )}
    </li>
  );
}

/** Calls about one lead or one ticket: add a transcript, read the Call Analyzer's findings. */
export function CallsPanel({
  leadId,
  ticketId,
  editable,
}: {
  leadId?: string;
  ticketId?: string;
  editable: boolean;
}) {
  const query = leadId ? `lead_id=${leadId}` : `ticket_id=${ticketId}`;
  const { data, error, reload } = usePoll<CallRecord[]>(`/calls?${query}`);
  const [adding, setAdding] = useState(false);

  return (
    <div className="anim-rise mt-4 rounded-lg border border-navy-800 bg-navy-950/40 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-semibold text-slate-300">
          Calls {data && data.length > 0 && <span className="text-slate-500">({data.length})</span>}
        </p>
        {editable && (
          <button onClick={() => setAdding(!adding)} className={ghostButton}>
            {adding ? "Cancel" : "Add call transcript"}
          </button>
        )}
      </div>
      <p className="mb-3 text-xs text-slate-500">
        The Call Analyzer summarises the call, reads the customer&apos;s sentiment and lists who
        promised what, quoting the transcript for each.
      </p>
      {adding && (
        <div className="mb-3">
          <AddCall
            target={leadId ? { lead_id: leadId } : { ticket_id: ticketId }}
            onAdded={() => {
              setAdding(false);
              void reload();
            }}
          />
        </div>
      )}
      <ErrorNote message={error} />
      {data && data.length === 0 && !adding && (
        <p className="text-xs text-slate-500">No calls yet.</p>
      )}
      <ul className="space-y-3">
        {data?.map((c) => (
          <CallCard key={c.id} call={c} editable={editable} onChange={() => void reload()} />
        ))}
      </ul>
    </div>
  );
}
