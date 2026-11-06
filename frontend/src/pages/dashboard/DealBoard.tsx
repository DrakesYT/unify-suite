import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api } from "../../api";
import { Badge, ErrorNote, ghostButton, inputClass, primaryButton } from "../../components/ui";
import { ChartIcon } from "../../components/icons";
import { compactMoney, label, money } from "../../format";
import type { LeadStatus, Money, Overview } from "../../types";
import { useAuth } from "../../session";
import { toast } from "../../toast";
import { Panel, Stat } from "./parts";

const STAGE_BAR: Record<LeadStatus, string> = {
  new: "bg-slate-400",
  contacted: "bg-sky-400",
  qualified: "bg-accent-purple",
  won: "bg-emerald-400",
  lost: "bg-rose-400/70",
};

function sumText(values: Money[]): string {
  return values.length
    ? values.map((v) => compactMoney(v.amount_minor, v.currency)).join(" + ")
    : "—";
}

/** Decimal places the currency uses (2 for USD, 0 for JPY). */
function decimals(currency: string): number {
  try {
    return new Intl.NumberFormat("en", { style: "currency", currency }).resolvedOptions()
      .maximumFractionDigits!;
  } catch {
    return 2;
  }
}

/** The CEO or an admin sets the quarterly target here; the backend checks the role again. */
function TargetForm({
  target,
  onDone,
}: {
  target: Overview["crm"]["target"];
  onDone: (changed: boolean) => void;
}) {
  const [amount, setAmount] = useState(
    String(target.target_minor / 10 ** decimals(target.currency)),
  );
  const [currency, setCurrency] = useState(target.currency);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // What will be saved, written the way the gauge shows it, so a stray digit is seen first.
  const code = currency.trim().toUpperCase();
  const value = Number(amount);
  const preview =
    /^[A-Z]{3}$/.test(code) && Number.isFinite(value) && value > 0
      ? `${money(Math.round(value * 10 ** decimals(code)), code)} (${compactMoney(Math.round(value * 10 ** decimals(code)), code)})`
      : null;

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/settings/sales-target", {
        method: "PUT",
        body: JSON.stringify({ amount, currency: currency.trim().toUpperCase() }),
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
      className="anim-pop flex flex-col gap-2 rounded-xl bg-navy-950/60 px-3.5 py-3 ring-1 ring-accent-purple/40 [--origin:top]"
    >
      <p className="text-xs text-slate-400">Quarterly sales target</p>
      <div className="flex gap-2">
        <input
          className={`${inputClass} min-w-0 flex-1`}
          type="number"
          min="1"
          step="any"
          inputMode="decimal"
          aria-label="Target amount"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          onFocus={(e) => e.target.select()} // typing replaces the old value, never mixes into it
          autoFocus
          required
        />
        <input
          className={`${inputClass} w-16 uppercase`}
          aria-label="Currency"
          maxLength={3}
          pattern="[A-Za-z]{3}"
          value={currency}
          onChange={(e) => setCurrency(e.target.value)}
          required
        />
      </div>
      <p className="text-xs text-slate-400 tabular-nums" aria-live="polite">
        {preview ? `= ${preview} per quarter` : "Enter an amount above zero"}
      </p>
      <ErrorNote message={error} />
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy || !preview}
          className={`${primaryButton} flex-1 py-1.5`}
        >
          {busy ? "Saving…" : "Save"}
        </button>
        <button type="button" onClick={() => onDone(false)} className={`${ghostButton} py-1.5`}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/** Won this quarter against the quarterly target: one progress bar. */
function TargetBar({
  target,
  onTargetChanged,
}: {
  target: Overview["crm"]["target"];
  onTargetChanged: () => void;
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
        onDone={(changed) => {
          setEditing(false);
          if (changed) onTargetChanged();
        }}
      />
    );
  }
  return (
    <div className="flex min-w-0 flex-col justify-center rounded-xl bg-navy-950/60 px-3.5 py-3 ring-1 ring-white/5">
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

export function DealBoard({
  crm,
  onTargetChanged,
}: {
  crm: Overview["crm"];
  onTargetChanged: () => void;
}) {
  return (
    <Panel title="CRM deal board" icon={<ChartIcon size={17} />} to="/sales">
      <div className="grid grid-cols-5 gap-1.5">
        {crm.stages.map((s) => (
          <div
            key={s.stage}
            className="min-w-0 rounded-lg bg-navy-950/60 px-2 py-2 ring-1 ring-white/5"
          >
            <div className={`mb-1.5 h-0.5 rounded-full ${STAGE_BAR[s.stage]}`} />
            <p className="truncate text-[11px] text-slate-400 capitalize">{s.stage}</p>
            <p className="text-lg leading-tight font-semibold text-white">{s.count}</p>
            <p className="truncate text-[10px] text-slate-500">{sumText(s.value)}</p>
          </div>
        ))}
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_1fr_1.2fr]">
        <Stat
          label="Open pipeline"
          value={sumText(crm.pipeline)}
          hint="new + contacted + qualified"
        />
        <Stat
          label="Win rate"
          value={crm.win_rate === null ? "—" : `${crm.win_rate}%`}
          hint={crm.won + crm.lost ? `${crm.won} won · ${crm.lost} lost` : "no deals closed yet"}
          tone="text-accent-soft"
        />
        <TargetBar target={crm.target} onTargetChanged={onTargetChanged} />
      </div>
      <p className="mt-4 mb-1.5 text-[11px] text-slate-500">Biggest open deals</p>
      <ul className="divide-y divide-white/5">
        {crm.top_deals.slice(0, 4).map((d) => (
          <li key={d.lead_id}>
            <Link
              to={`/sales#lead-${d.lead_id}`}
              className="-mx-2 flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-white/[0.03]"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-slate-100">{d.company}</span>
                <span className="block truncate text-xs text-slate-500">
                  {d.contact} · {label(d.status)}
                </span>
              </span>
              {d.rating && <Badge value={d.rating} />}
              <span className="text-sm font-medium whitespace-nowrap text-slate-200">
                {money(d.amount_minor, d.currency)}
              </span>
            </Link>
          </li>
        ))}
        {crm.top_deals.length === 0 && (
          <li className="py-3 text-sm text-slate-500">No open deals.</li>
        )}
      </ul>
    </Panel>
  );
}
