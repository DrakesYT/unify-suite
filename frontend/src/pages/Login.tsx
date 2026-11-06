import { useState, type FormEvent } from "react";
import { Navigate } from "react-router";
import { useAuth } from "../session";
import { ErrorNote, inputClass, primaryButton } from "../components/ui";
import { LogoMark } from "../components/icons";

export function Login() {
  const { user, signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm space-y-4 rounded-2xl border border-navy-800 bg-navy-900 p-8"
      >
        <div className="text-center">
          <h1 className="flex items-center justify-center gap-2 text-2xl font-semibold tracking-tight text-white">
            <LogoMark size={30} />
            UNIFY <span className="font-medium text-slate-400">SUITE</span>
          </h1>
          <p className="mt-2 text-sm text-slate-400">AI workforce platform, powered by Vultr</p>
        </div>
        <label className="block space-y-1 text-sm">
          <span className="text-slate-300">Email</span>
          <input
            className={inputClass}
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label className="block space-y-1 text-sm">
          <span className="text-slate-300">Password</span>
          <input
            className={inputClass}
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        <ErrorNote message={error} />
        <button type="submit" disabled={busy} className={`${primaryButton} w-full`}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
