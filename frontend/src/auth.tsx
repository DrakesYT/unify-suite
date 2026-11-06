import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api, hasSignedInHint, setSignedInHint, SIGNED_OUT_EVENT } from "./api";
import { LogoLoader } from "./components/LogoLoader";
import { AuthContext } from "./session";
import type { User } from "./types";

/** How long the logo stays up when the app shows it on purpose: long enough for the mark to draw
 *  itself and start turning (the session check itself answers in about a quarter of a second). */
const HOLD_MS = 1600;
const FADE_MS = 220; // matches .anim-fade-out

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

interface Cover {
  label: string;
  leaving: boolean;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  // The session cookie is invisible to scripts, so every load asks the server who is signed in.
  // `restoring`: this browser signed in before, so show the logo while the server confirms it.
  const [restoring] = useState(hasSignedInHint);
  const [loading, setLoading] = useState(true);
  // Full-screen logo over the switch between the sign-in page and the app (both directions).
  const [cover, setCover] = useState<Cover | null>(null);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    const me = api<User>("/auth/me").catch(() => null);
    Promise.all([me, restoring ? wait(HOLD_MS) : null]).then(([found]) => {
      setSignedInHint(Boolean(found));
      setUser(found);
      setLoading(false);
    });
    const onSignedOut = () => setUser(null);
    window.addEventListener(SIGNED_OUT_EVENT, onSignedOut);
    const pending = timers.current;
    return () => {
      window.removeEventListener(SIGNED_OUT_EVENT, onSignedOut);
      pending.forEach(clearTimeout);
    };
  }, [restoring]);

  /** Show the logo, run `atEnd` when it has had its moment, then fade the cover away. */
  const showCover = useCallback((label: string, atEnd?: () => void) => {
    timers.current.forEach(clearTimeout);
    setCover({ label, leaving: false });
    timers.current = [
      window.setTimeout(() => {
        atEnd?.();
        setCover({ label, leaving: true });
      }, HOLD_MS),
      window.setTimeout(() => setCover(null), HOLD_MS + FADE_MS),
    ];
  }, []);

  const signIn = async (email: string, password: string) => {
    const res = await api<{ user: User }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setSignedInHint(true);
    // The app opens behind the logo, so its first data is usually in by the time it fades.
    showCover("Opening your workspace…");
    setUser(res.user);
  };

  const switchTo = async (email: string) => {
    const res = await api<{ user: User }>("/auth/demo-switch", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    setUser(res.user);
    return res.user;
  };

  const signOut = () => {
    // End the session on the server straight away; the cover only paces what the user sees.
    api("/auth/logout", { method: "POST" }).catch(() => undefined);
    showCover("Signing you out…", () => {
      setSignedInHint(false);
      setUser(null);
    });
  };

  return (
    <AuthContext.Provider value={{ user, loading, restoring, signIn, signOut, switchTo }}>
      {children}
      {cover && (
        <div
          className={`fixed inset-0 z-[100] bg-navy-950 ${cover.leaving ? "anim-fade-out" : "anim-fade"}`}
        >
          <LogoLoader label={cover.label} fullScreen immediate />
        </div>
      )}
    </AuthContext.Provider>
  );
}
