import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { TOAST_EVENT, type ToastMessage, type ToastTone } from "../toast";
import { CheckIcon, CloseIcon, InfoIcon } from "./icons";

const SHOW_MS = 4500;
const MAX_SHOWN = 3;

interface Item {
  id: number;
  message: string;
  tone: ToastTone;
}

const TONE: Record<ToastTone, { box: string; icon: ReactNode }> = {
  success: {
    box: "border-emerald-400/30 text-emerald-50",
    icon: <CheckIcon size={16} className="text-emerald-300" />,
  },
  error: {
    box: "border-red-400/40 text-red-50",
    icon: <CloseIcon size={16} className="text-red-300" />,
  },
  info: {
    box: "border-white/10 text-slate-100",
    icon: <InfoIcon size={16} className="text-accent-soft" />,
  },
};

/** Holds the toast queue and draws it bottom-right (bottom, full width, on phones). */
export function Toaster({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Item[]>([]);
  const next = useRef(1);

  const dismiss = useCallback(
    (id: number) => setItems((all) => all.filter((t) => t.id !== id)),
    [],
  );
  useEffect(() => {
    const onToast = (e: Event) => {
      const { message, tone } = (e as CustomEvent<ToastMessage>).detail;
      const id = next.current++;
      setItems((all) => [...all.slice(-(MAX_SHOWN - 1)), { id, message, tone }]);
      setTimeout(() => dismiss(id), SHOW_MS);
    };
    window.addEventListener(TOAST_EVENT, onToast);
    return () => window.removeEventListener(TOAST_EVENT, onToast);
  }, [dismiss]);

  return (
    <>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed right-3 bottom-3 left-3 z-[80] flex flex-col items-end gap-2 sm:left-auto"
      >
        {items.map((t) => (
          <div
            key={t.id}
            role={t.tone === "error" ? "alert" : "status"}
            className={`pointer-events-auto flex w-full items-start gap-2.5 rounded-xl border bg-navy-900/95 px-3.5 py-2.5 text-sm shadow-2xl shadow-black/50 backdrop-blur sm:w-96 ${TONE[t.tone].box}`}
          >
            <span className="mt-0.5 shrink-0">{TONE[t.tone].icon}</span>
            <span className="min-w-0 flex-1">{t.message}</span>
            <button
              onClick={() => dismiss(t.id)}
              aria-label="Dismiss"
              className="shrink-0 text-slate-500 hover:text-white"
            >
              <CloseIcon size={14} />
            </button>
          </div>
        ))}
      </div>
    </>
  );
}
