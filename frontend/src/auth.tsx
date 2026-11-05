import { useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken, SIGNED_OUT_EVENT } from "./api";
import { AuthContext } from "./session";
import type { User } from "./types";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(Boolean(getToken()));

  useEffect(() => {
    if (getToken()) {
      api<User>("/auth/me")
        .then(setUser)
        .catch(() => setUser(null))
        .finally(() => setLoading(false));
    }
    const onSignedOut = () => setUser(null);
    window.addEventListener(SIGNED_OUT_EVENT, onSignedOut);
    return () => window.removeEventListener(SIGNED_OUT_EVENT, onSignedOut);
  }, []);

  const signIn = async (email: string, password: string) => {
    const res = await api<{ access_token: string; user: User }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setToken(res.access_token);
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
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, signIn, signOut, switchTo }}>
      {children}
    </AuthContext.Provider>
  );
}
