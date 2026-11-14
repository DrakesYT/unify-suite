import { useState } from "react";
import { api } from "../api";
import { toast } from "../toast";
import type { InterviewSlot, OutboundEmail } from "../types";
import { usePoll } from "../usePoll";
import { ErrorNote, ghostButton } from "./ui";

/** Under a sent interview invitation: record the time the candidate picked. The other offered
 *  times are then free for other candidates again. */
export function InterviewSlots({ listPath, editable }: { listPath: string; editable: boolean }) {
  const emails = usePoll<OutboundEmail[]>(listPath);
  const invite = emails.data?.[0];
  const sent = invite?.status === "sent";
  const slots = usePoll<InterviewSlot[]>(sent ? `/hr/emails/${invite.id}/slots` : null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!sent || !slots.data || slots.data.length === 0) return null;
  const booked = slots.data.find((s) => s.booked);

  const book = async (slot: InterviewSlot) => {
    if (!window.confirm(`Book the interview for ${slot.label}? The other times are released.`))
      return;
    setBusy(true);
    setError(null);
    try {
      await api(`/hr/emails/${invite.id}/slots/${slot.id}/book`, { method: "POST" });
      toast(`Interview booked: ${slot.label}`);
      await slots.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not book the interview");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 rounded-lg border border-navy-800 bg-navy-950/40 p-3 text-sm">
      {booked ? (
        <p className="text-emerald-300">Interview booked: {booked.label}</p>
      ) : (
        <>
          <p className="text-xs font-semibold text-slate-300">Which time did the candidate pick?</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {slots.data.map((slot) => (
              <button
                key={slot.id}
                disabled={busy || !editable}
                onClick={() => void book(slot)}
                className={ghostButton}
              >
                {slot.label}
              </button>
            ))}
          </div>
        </>
      )}
      <ErrorNote message={error} />
    </div>
  );
}
