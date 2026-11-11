/** Soft icon chip colours; the light theme deepens the text shade automatically. */
export const CHIP_TONE = {
  violet: "bg-violet-500/12 text-violet-300",
  amber: "bg-amber-500/15 text-amber-300",
  sky: "bg-sky-500/15 text-sky-300",
  rose: "bg-rose-500/15 text-rose-300",
  emerald: "bg-emerald-500/15 text-emerald-300",
  red: "bg-red-500/15 text-red-300",
} as const;
export type ChipTone = keyof typeof CHIP_TONE;
