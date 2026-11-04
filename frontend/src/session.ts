import { createContext, useContext } from "react";
import type { Department, User } from "./types";

export interface AuthState {
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
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
