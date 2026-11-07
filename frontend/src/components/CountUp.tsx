import { useEffect, useRef, useState } from "react";

const NUMBER = /\d[\d,]*(\.\d+)?/;
const DURATION_MS = 250;

/** Counts the first number in `value` up from zero once, the first time real data arrives.
 *  Pages render 0 (or "$0") while their data loads, so a zero never uses up the animation. */
export function CountUp({ value }: { value: string | number }) {
  const text = String(value);
  const match = NUMBER.exec(text);
  const target = match ? Number(match[0].replaceAll(",", "")) : NaN;
  const done = useRef(false);
  const [shown, setShown] = useState<number | null>(null);

  useEffect(() => {
    if (done.current || Number.isNaN(target) || target === 0) return;
    done.current = true;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) return;
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / DURATION_MS);
      setShown(target * (1 - (1 - t) ** 3));
      if (t < 1) frame = requestAnimationFrame(tick);
      else setShown(null);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      // The value changed (or the card left) mid-count: show the real number, never a frozen one.
      cancelAnimationFrame(frame);
      setShown(null);
    };
  }, [target]);

  if (!match || shown === null) return <>{text}</>;
  const decimals = match[1] ? match[1].length - 1 : 0;
  const grouped = match[0].includes(",");
  const part = shown.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
    useGrouping: grouped,
  });
  return (
    <>
      {text.slice(0, match.index)}
      {part}
      {text.slice(match.index + match[0].length)}
    </>
  );
}
