import type { CSSProperties } from "react";

/* The mark is drawn several times, each copy a step further back in 3D space and a shade darker,
   so together they read as one solid, extruded logo. */
const DEPTH = 10; // copies, 1.6 px apart

const ACCENT = [139, 92, 246]; // #8b5cf6
const NAVY = [12, 18, 41]; // #0c1229

/** The accent, `t` of the way toward navy (0 = accent, 1 = navy). */
function darken(t: number): string {
  const [r, g, b] = ACCENT.map((c, i) => Math.round(c + (NAVY[i] - c) * t));
  return `rgb(${r} ${g} ${b})`;
}

function Mark({ layer }: { layer: number }) {
  const back = layer > 0;
  // Back copies darken from the accent toward navy; the front copy keeps the real logo colours.
  const shade = back ? darken(0.25 + layer * 0.05) : "#8b5cf6";
  return (
    <svg
      viewBox="0 0 32 32"
      className="logo-loader-layer"
      style={{ "--z": `${-layer * 1.6}px` } as CSSProperties}
      aria-hidden="true"
    >
      <path
        className="logo-loader-u"
        d="M9 8v8.5a7 7 0 0 0 14 0V8"
        fill="none"
        stroke={shade}
        strokeWidth="3.2"
        strokeLinecap="round"
      />
      <path
        className="logo-loader-bar"
        d="M16 8v8"
        stroke={back ? shade : "#c4b5fd"}
        strokeWidth="3.2"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Loading state built from the logo: the U draws itself, then the solid mark turns slowly.
 *  It only fades in after 300 ms, so a quick load never flashes it. */
export function LogoLoader({ label, fullScreen = false }: { label: string; fullScreen?: boolean }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={`logo-loader grid place-items-center ${fullScreen ? "min-h-screen" : "min-h-[60vh]"}`}
    >
      <div className="flex flex-col items-center gap-6">
        <div className="logo-loader-stage">
          <div className="logo-loader-mark">
            {Array.from({ length: DEPTH }, (_, i) => DEPTH - 1 - i).map((layer) => (
              <Mark key={layer} layer={layer} />
            ))}
          </div>
          <span className="logo-loader-shadow" aria-hidden="true" />
        </div>
        <p className="text-sm text-slate-400">{label}</p>
      </div>
    </div>
  );
}
