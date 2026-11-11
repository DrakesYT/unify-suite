/** Light or dark theme: stored per browser, light by default, applied as <html data-theme>. */
import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

const KEY = "unify.theme";
const META_COLOR: Record<Theme, string> = { light: "#f3f2fa", dark: "#070b1a" };
const listeners = new Set<() => void>();

function stored(): Theme {
  try {
    return localStorage.getItem(KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

let current: Theme = stored();

function paint(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", META_COLOR[theme]);
}

/** Called once before the first render so the page never flashes the other theme. */
export function initTheme() {
  paint(current);
}

/** Switch theme; the new one grows as a circle out of `origin` (the switch that was pressed). */
export function setTheme(theme: Theme, origin?: HTMLElement | null) {
  if (theme === current) return;
  current = theme;
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // Private window or blocked storage: the choice simply lasts for this visit.
  }
  const apply = () => {
    paint(theme);
    listeners.forEach((l) => l());
  };
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!document.startViewTransition || reduced || !origin) {
    apply();
    return;
  }
  const box = origin.getBoundingClientRect();
  const x = box.left + box.width / 2;
  const y = box.top + box.height / 2;
  const radius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
  const root = document.documentElement.style;
  root.setProperty("--reveal-x", `${x}px`);
  root.setProperty("--reveal-y", `${y}px`);
  root.setProperty("--reveal-r", `${radius}px`);
  document.startViewTransition(apply);
}

export function useTheme(): Theme {
  return useSyncExternalStore(
    (onChange) => {
      listeners.add(onChange);
      return () => listeners.delete(onChange);
    },
    () => current,
  );
}
