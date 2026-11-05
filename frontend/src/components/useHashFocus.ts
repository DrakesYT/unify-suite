import { useEffect } from "react";
import { useLocation } from "react-router";

const WAIT_MS = 4000;
const STEP_MS = 150;
const FLASH_MS = 2200;

/** After navigating to `/page#some-id`, scroll that row into view and flash it once the page
 * has loaded its data (rows arrive with the first poll, so keep looking for a few seconds). */
export function useHashFocus() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (!hash) return;
    const id = decodeURIComponent(hash.slice(1));
    let waited = 0;
    let flash: ReturnType<typeof setTimeout> | undefined;
    const timer = setInterval(() => {
      const el = document.getElementById(id);
      waited += STEP_MS;
      if (!el && waited < WAIT_MS) return;
      clearInterval(timer);
      if (!el) return;
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("flash-focus");
      flash = setTimeout(() => el.classList.remove("flash-focus"), FLASH_MS);
    }, STEP_MS);
    return () => {
      clearInterval(timer);
      clearTimeout(flash);
    };
  }, [pathname, hash]);
}
