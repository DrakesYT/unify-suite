import { useState } from "react";
import { AuraPanel } from "./AuraPanel";
import { Orb } from "./AuraOrb";
import { CloseIcon } from "./icons";

/** Aura for people without the dashboard: a button that opens the chat. Bottom left, because
 *  toasts and the tour invitation use the bottom right. */
export function AuraDock() {
  const [open, setOpen] = useState(false);
  return (
    <div className="fixed bottom-4 left-4 z-40 flex flex-col items-start gap-3">
      {open && (
        <div className="anim-rise w-[min(92vw,380px)]">
          <AuraPanel chatOnly />
        </div>
      )}
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={open ? "Close Aura" : "Ask Aura"}
        className="flex items-center gap-2 rounded-full bg-accent-purple px-4 py-2.5 text-sm font-medium text-on-accent shadow-lg transition-colors hover:bg-accent-purple/85"
      >
        {open ? <CloseIcon /> : <Orb size={22} />}
        {open ? "Close" : "Ask Aura"}
      </button>
    </div>
  );
}
