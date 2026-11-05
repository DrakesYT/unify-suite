import { SparkleIcon } from "./icons";

/** Aura's glowing avatar. */
export function Orb({ size = 40 }: { size?: number }) {
  return (
    <span
      className="aura-orb relative grid shrink-0 place-items-center rounded-full"
      style={{
        width: size,
        height: size,
        background:
          "radial-gradient(circle at 35% 30%, #e0f2fe 0%, #22d3ee 28%, #8b5cf6 70%, #4c1d95 100%)",
        boxShadow: "0 0 24px rgb(34 211 238 / 0.45), 0 0 48px rgb(139 92 246 / 0.35)",
      }}
      aria-hidden="true"
    >
      <SparkleIcon size={size * 0.45} className="text-white/90" />
    </span>
  );
}
