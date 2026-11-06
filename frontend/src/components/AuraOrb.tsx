import { SparkleIcon } from "./icons";

/** Aura's mark: a flat purple disc with the sparkle (the one place the sparkle means "AI"). */
export function Orb({ size = 40 }: { size?: number }) {
  return (
    <span
      className="grid shrink-0 place-items-center rounded-full bg-accent-purple"
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <SparkleIcon size={size * 0.5} className="text-white" />
    </span>
  );
}
