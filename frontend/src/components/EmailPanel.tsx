import { useState } from "react";
import { api } from "../api";
import { when } from "../format";
import type { OutboundEmail } from "../types";
import { usePoll } from "../usePoll";
import { Badge, ErrorNote, ghostButton, inputClass, primaryButton } from "./ui";
import { WhyButton } from "./WhyDrawer";
import { toast } from "../toast";

const ACT_DONE: Record<string, string> = {
  draft: "Draft written. Check it, then send it for approval.",
  save: "Draft saved",
  send: "Sent to a manager for approval. Nothing goes out before that.",
  retry: "Trying to send again",
};

/** An AI-drafted email: the agent drafts, a person edits, a manager approves, then it is sent. */
/** What code found in the saved text: bot-like phrasing a reviewer may want to change. */
function StyleCheck({ notes }: { notes: OutboundEmail["style_notes"] }) {
  if (notes.length === 0) {
    return (
      <p className="text-xs text-emerald-300/90">
        Style check by code: no bot-like phrasing. Amounts, references and dates were checked
        against the facts when the AI wrote it.
      </p>
    );
  }
  return (
    <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-2.5 text-xs">
      <p className="mb-1 font-semibold text-amber-200">Style suggestions (checked by code)</p>
      <ul className="space-y-1">
        {notes.map((n, i) => (
          <li key={`${n.rule}-${i}`} className="text-slate-300">
            <span className="font-medium text-amber-100">“{n.text}”</span>{" "}
            <span className="text-slate-500">({n.rule})</span>: {n.advice}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function EmailPanel({
  title,
  intro,
  listPath,
  emailsPath,
  managerLabel,
  editable,
  draftLabel = "Draft email with AI",
}: {
  title: string;
  intro: string;
  /** GET = this record's emails; POST = ask the agent for a new draft */
  listPath: string;
  /** base path for one email: PATCH, /request-approval, /retry */
  emailsPath: string;
  managerLabel: string;
  editable: boolean;
  /** The button that starts the first draft. */
  draftLabel?: string;
}) {
  const { data, reload } = usePoll<OutboundEmail[]>(listPath);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [loadedId, setLoadedId] = useState<string | null>(null);
  const email = data?.[0];

  // Load a new draft into the editor once (not on every poll, so typing is never overwritten).
  if (email?.status === "draft" && email.id !== loadedId) {
    setLoadedId(email.id);
    setSubject(email.subject);
    setBody(email.body);
  }

  const act = async (name: string, path: string, init: RequestInit) => {
    setBusy(name);
    setError(null);
    try {
      await api(path, init);
      if (ACT_DONE[name]) toast(ACT_DONE[name]);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(null);
    }
  };
  const save = () =>
    act("save", `${emailsPath}/${email!.id}`, {
      method: "PATCH",
      body: JSON.stringify({ subject, body }),
    });
  const send = async () => {
    if (subject !== email!.subject || body !== email!.body) await save();
    await act("send", `${emailsPath}/${email!.id}/request-approval`, { method: "POST" });
  };

  return (
    <div className="anim-rise mt-3 rounded-lg border border-navy-800 bg-navy-950/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold text-slate-300">
          {title} {email && <Badge value={email.status} />}{" "}
          {email && <WhyButton path={`email/${email.id}`} verifiable={false} />}
        </p>
        {editable && (
          <button
            disabled={!!busy}
            onClick={() => act("draft", listPath, { method: "POST" })}
            className={ghostButton}
          >
            {busy === "draft" ? "Writing…" : email ? "Draft a new email" : draftLabel}
          </button>
        )}
      </div>
      <ErrorNote message={error} />
      {!email && <p className="mt-2 text-sm text-slate-500">{intro}</p>}
      {email && (
        <div className="mt-3 space-y-2 text-sm">
          <p className="text-slate-400">
            To: <span className="text-slate-200">{email.to_address}</span>
          </p>
          {email.status === "draft" && editable ? (
            <>
              <input
                className={inputClass}
                value={subject}
                maxLength={120}
                onChange={(e) => setSubject(e.target.value)}
              />
              <textarea
                className={`${inputClass} min-h-56 font-sans`}
                value={body}
                maxLength={3000}
                onChange={(e) => setBody(e.target.value)}
              />
              <div className="flex flex-wrap gap-2">
                <button disabled={!!busy} onClick={() => void send()} className={primaryButton}>
                  {busy === "send" ? "Sending for approval…" : "Send for approval"}
                </button>
                <button disabled={!!busy} onClick={() => void save()} className={ghostButton}>
                  {busy === "save" ? "Saving…" : "Save changes"}
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="font-medium text-slate-100">{email.subject}</p>
              <p className="rounded-lg bg-navy-950/70 p-3 whitespace-pre-wrap text-slate-300">
                {email.body}
              </p>
            </>
          )}
          {(email.status === "draft" || email.status === "pending_approval") && (
            <StyleCheck notes={email.style_notes} />
          )}
          {email.status === "pending_approval" && (
            <p className="text-amber-200">Waiting for {managerLabel} in the Approval Center.</p>
          )}
          {email.status === "sent" && (
            <p className="text-emerald-300">
              Sent to {email.delivered_to} · {when(email.sent_at!)}
            </p>
          )}
          {email.status === "rejected" && (
            <p className="text-red-300">
              The {managerLabel.replace(/^an? /, "")} rejected this email. It was not sent.
            </p>
          )}
          {email.status === "failed" && (
            <div className="space-y-2">
              <p className="text-red-300">Approved, but sending failed: {email.error}</p>
              {editable && (
                <button
                  disabled={!!busy}
                  onClick={() =>
                    act("retry", `${emailsPath}/${email.id}/retry`, { method: "POST" })
                  }
                  className={ghostButton}
                >
                  {busy === "retry" ? "Retrying…" : "Retry sending"}
                </button>
              )}
            </div>
          )}
          <p className="text-xs text-slate-500">Drafted by {email.drafted_by_model ?? "AI"}</p>
        </div>
      )}
    </div>
  );
}
