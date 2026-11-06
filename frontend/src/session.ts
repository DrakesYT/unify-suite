import { createContext, useContext } from "react";
import type { Department, User } from "./types";

export interface AuthState {
  user: User | null;
  loading: boolean;
  /** This browser was signed in before: the load check is shown with the logo, on purpose. */
  restoring: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
  /** Demo accounts only: become another seeded demo user (no password typed). */
  switchTo: (email: string) => Promise<User>;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

export const DEMO_DOMAIN = "@demo.example.com";

/** Seeded demo account (the role switcher and the guided tour are only for these). */
export function isDemo(user: User | null): boolean {
  return Boolean(user && user.email.endsWith(DEMO_DOMAIN) && user.role !== "admin");
}

/** Mirrors the backend rule: who may read a department's data. */
export function canRead(user: User, department: Department): boolean {
  return user.role !== "employee" || user.department === department;
}

/** Mirrors the backend rule: who may change a department's data. */
export function canWrite(user: User, department: Department): boolean {
  if (user.role === "admin") return true;
  if (user.role === "executive") return false;
  return user.department === department;
}
