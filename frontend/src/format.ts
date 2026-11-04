const ZERO_DECIMAL = new Set(["CLP", "ISK", "JPY", "KRW", "PYG", "UGX", "VND", "XAF", "XOF"]);

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
