const ZERO_DECIMAL = new Set(["CLP", "ISK", "JPY", "KRW", "PYG", "UGX", "VND", "XAF", "XOF"]);

/** Minor units to whole major units (cents to dollars; yen stay yen), rounded. */
export function majorUnits(amountMinor: number, currency: string): number {
  return Math.round(amountMinor / (ZERO_DECIMAL.has(currency) ? 1 : 100));
}

export function money(amountMinor: number | undefined, currency: string | undefined): string {
  if (amountMinor === undefined || !currency) return "—";
  const digits = ZERO_DECIMAL.has(currency) ? 0 : 2;
  const value = amountMinor / 10 ** digits;
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(value);
  } catch {
    return `${value.toFixed(digits)} ${currency}`;
  }
}

export function when(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function label(value: string): string {
  return value.replaceAll("_", " ");
}

/** 4_800_000 cents → "$48K" (for tight dashboard tiles; exact values stay on the pages). */
export function compactMoney(amountMinor: number, currency: string): string {
  const digits = ZERO_DECIMAL.has(currency) ? 0 : 2;
  const value = amountMinor / 10 ** digits;
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(value);
  } catch {
    return `${value.toFixed(0)} ${currency}`;
  }
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return (
    (parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")
  ).toUpperCase();
}

/** "5 min ago", "3 h ago", "2 d ago". */
export function ago(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60_000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}
