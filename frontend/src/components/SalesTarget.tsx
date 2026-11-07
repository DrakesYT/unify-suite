import { useState, type FormEvent } from "react";
import { api } from "../api";
import { compactMoney, money } from "../format";
import { useAuth } from "../session";
import { toast } from "../toast";
import type { QuarterTarget } from "../types";
import { ErrorNote, ghostButton, inputClass, primaryButton } from "./ui";

/** Decimal places the currency uses (2 for USD, 0 for JPY). */
function decimals(currency: string): number {
  try {
    return new Intl.NumberFormat("en", { style: "currency", currency }).resolvedOptions()
      .maximumFractionDigits!;
  } catch {
    return 2;
  }
}

// inputClass sets w-full; these fields set their own width.
const field = inputClass.replace("w-full ", "");

/** The CEO or an admin sets the quarterly target here; the backend checks the role again. */
function TargetForm({
  target,
  onDone,
  className = "",
}: {
  target: QuarterTarget;
  onDone: (changed: boolean) => void;
  className?: string;
}) {
  const [amount, setAmount] = useState(
    String(target.target_minor / 10 ** decimals(target.currency)),
  );
  const [currency, setCurrency] = useState(target.currency);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // What will be saved, written the way the bar shows it, so a stray digit is seen first.
  const code = currency.trim().toUpperCase();
  const value = Number(amount);
  const minor = Math.round(value * 10 ** decimals(code));
  const preview =
    /^[A-Z]{3}$/.test(code) && Number.isFinite(value) && value > 0
      ? `${money(minor, code)} (${compactMoney(minor, code)})`
      : null;

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/settings/sales-target", {
        method: "PUT",
        body: JSON.stringify({ amount, currency: code }),
      });
      toast("Quarterly sales target updated");
      onDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the target");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      onSubmit={save}
      className={`anim-pop rounded-xl bg-navy-950/60 px-4 py-3.5 ring-1 ring-accent-purple/40 [--origin:top] ${className}`}
    >
      <p className="text-xs text-slate-400">Quarterly sales target for {target.quarter}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <label className="flex max-w-sm min-w-0 flex-[1_1_12rem] items-center gap-2">
          <span className="sr-only">Target amount</span>
          <input
            className={`${field} w-full min-w-0 text-base tabular-nums`}
            type="number"
            min="1"
            step="any"
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            onFocus={(e) => e.target.select()} // typing replaces the old value, never mixes into it
            autoFocus
            required
          />
        </label>
        <label className="shrink-0">
          <span className="sr-only">Currency</span>
          <input
            className={`${field} w-20 text-center uppercase`}
            maxLength={3}
            pattern="[A-Za-z]{3}"
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
            required
          />
        </label>
        <div className="flex shrink-0 gap-2">
          <button type="submit" disabled={busy || !preview} className={primaryButton}>
            {busy ? "Saving…" : "Save"}
          </button>
          <button type="button" onClick={() => onDone(false)} className={ghostButton}>
            Cancel
          </button>
        </div>
      </div>
      <p className="mt-2 text-xs text-slate-400 tabular-nums" aria-live="polite">
        {preview ? `= ${preview} per quarter` : "Enter an amount above zero"}
      </p>
      <div className="mt-1">
        <ErrorNote message={error} />
      </div>
    </form>
  );
}

/** Won this quarter against the quarterly target: one progress bar, editable by the CEO or an
 *  admin. `editClassName` lets the form take more room than the bar (e.g. a whole grid row). */
export function TargetBar({
  target,
  onTargetChanged,
  editClassName = "",
  className = "",
}: {
  target: QuarterTarget;
  onTargetChanged: () => void;
  editClassName?: string;
  className?: string;
}) {
  const { user } = useAuth();
  const canEdit = user?.role === "admin" || user?.role === "executive";
  const [editing, setEditing] = useState(false);
  const share = target.target_minor ? target.won_minor / target.target_minor : 0;
  const pct = Math.round(share * 100);
  if (editing) {
    return (
      <TargetForm
        target={target}
        className={editClassName}
        onDone={(changed) => {
          setEditing(false);
          if (changed) onTargetChanged();
        }}
      />
    );
  }
  return (
    <div
      className={`flex min-w-0 flex-col justify-center rounded-xl bg-navy-950/60 px-3.5 py-3 ring-1 ring-white/5 ${className}`}
    >
      <p className="truncate text-xs text-slate-400">Won in {target.quarter}</p>
      <p className="mt-1 truncate text-xl font-semibold text-white tabular-nums">
        {compactMoney(target.won_minor, target.currency)}{" "}
        <span className="text-xs font-normal text-slate-500">
          of {compactMoney(target.target_minor, target.currency)}
        </span>
      </p>
      <div
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.07]"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${pct}% of target`}
      >
        <div
          className="h-full rounded-full bg-accent-purple"
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <p className="mt-1 flex items-center gap-2 text-xs text-slate-500">
        <span className="min-w-0 truncate">
          {pct}% of the quarterly target
          {target.set_by ? ` · set by ${target.set_by}` : " · default"}
        </span>
        {canEdit && (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="shrink-0 rounded px-1 text-accent-soft hover:bg-white/5 hover:text-white"
          >
            Edit target
          </button>
        )}
      </p>
    </div>
  );
}
