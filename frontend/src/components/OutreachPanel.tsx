import { useState } from "react";
import { api } from "../api";
import { when } from "../format";
import type { OutboundEmail } from "../types";
import { usePoll } from "../usePoll";
import { Badge, ErrorNote, ghostButton, inputClass, primaryButton } from "./ui";

/** Outreach for one qualified lead: AI drafts, the rep edits, a sales manager approves, it is sent. */
export function OutreachPanel({ leadId, editable }: { leadId: string; editable: boolean }) {
  const { data, reload } = usePoll<OutboundEmail[]>(`/sales/leads/${leadId}/emails`);
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
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(null);
    }
  };
  const save = () =>
    act("save", `/sales/emails/${email!.id}`, {
      method: "PATCH",
      body: JSON.stringify({ subject, body }),
    });
  const send = async () => {
    if (subject !== email!.subject || body !== email!.body) await save();
    await act("send", `/sales/emails/${email!.id}/request-approval`, { method: "POST" });
  };

  return (
    <div className="mt-3 rounded-lg border border-navy-800 bg-navy-950/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold text-slate-300 uppercase">
          Outreach email {email && <Badge value={email.status} />}
        </p>
        {editable && (
          <button
            disabled={!!busy}
            onClick={() => act("draft", `/sales/leads/${leadId}/emails`, { method: "POST" })}
            className={ghostButton}
          >
            {busy === "draft" ? "Writing…" : email ? "Draft a new email" : "Draft email with AI"}
          </button>
        )}
      </div>
      <ErrorNote message={error} />
      {!email && (
        <p className="mt-2 text-sm text-slate-500">
          The Outreach Writer drafts a first email from the qualification. Nothing is sent until a
          sales manager approves it.
        </p>
      )}
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
          {email.status === "pending_approval" && (
            <p className="text-amber-200">Waiting for a sales manager in the Approval Center.</p>
          )}
          {email.status === "sent" && (
            <p className="text-emerald-300">
              Sent to {email.delivered_to} · {when(email.sent_at!)}
            </p>
          )}
          {email.status === "rejected" && (
            <p className="text-red-300">A sales manager rejected this email. It was not sent.</p>
          )}
          {email.status === "failed" && (
            <div className="space-y-2">
              <p className="text-red-300">Approved, but sending failed: {email.error}</p>
              {editable && (
                <button
                  disabled={!!busy}
                  onClick={() =>
                    act("retry", `/sales/emails/${email.id}/retry`, { method: "POST" })
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
