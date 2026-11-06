import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api, getToken, setToken, SIGNED_OUT_EVENT } from "./api";
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
  const [loading, setLoading] = useState(Boolean(getToken()));
  // Full-screen logo over the switch between the sign-in page and the app (both directions).
  const [cover, setCover] = useState<Cover | null>(null);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    if (getToken()) {
      Promise.all([api<User>("/auth/me").catch(() => null), wait(HOLD_MS)]).then(([me]) => {
        setUser(me);
        setLoading(false);
      });
    }
    const onSignedOut = () => setUser(null);
    window.addEventListener(SIGNED_OUT_EVENT, onSignedOut);
    const pending = timers.current;
    return () => {
      window.removeEventListener(SIGNED_OUT_EVENT, onSignedOut);
      pending.forEach(clearTimeout);
    };
  }, []);

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
    const res = await api<{ access_token: string; user: User }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setToken(res.access_token);
    // The app opens behind the logo, so its first data is usually in by the time it fades.
    showCover("Opening your workspace…");
    setUser(res.user);
  };

  const switchTo = async (email: string) => {
    const res = await api<{ access_token: string; user: User }>("/auth/demo-switch", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    setToken(res.access_token);
    setUser(res.user);
    return res.user;
  };

  const signOut = () => {
    showCover("Signing you out…", () => {
      setToken(null);
      setUser(null);
    });
  };

  return (
    <AuthContext.Provider value={{ user, loading, signIn, signOut, switchTo }}>
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
