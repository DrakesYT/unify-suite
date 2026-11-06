import { useState, type CSSProperties, type FormEvent } from "react";
import { Navigate } from "react-router";
import { useAuth } from "../session";
import { ErrorNote, inputClass, primaryButton } from "../components/ui";
import { EyeIcon, EyeOffIcon, LockIcon, LogoMark, MailIcon } from "../components/icons";
import { LoginShowcase } from "../components/LoginShowcase";

/** Stagger for the sign-in page's one-time entrance (ms after the card starts arriving). */
const at = (ms: number) => ({ "--delay": `${ms}ms` }) as CSSProperties;

export function Login() {
  const { user, signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [failures, setFailures] = useState(0);
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
      setFailures((n) => n + 1);
    } finally {
      setBusy(false);
    }
  };

  const field = `${inputClass} h-11 pl-10 transition-colors duration-150`;

  return (
    <main className="grid min-h-screen place-items-center px-3 py-6 md:px-6">
      <div className="anim-rise-slow grid w-full max-w-[1120px] gap-2 rounded-3xl border border-white/5 bg-navy-900 p-2 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        {/* Left: the form */}
        <section className="flex flex-col px-5 py-8 sm:px-10 lg:px-14 lg:py-12">
          <div className="anim-rise flex items-center gap-3" style={at(80)}>
            <LogoMark size={44} />
            <span className="text-2xl font-bold tracking-tight text-white sm:text-[28px]">
              UNIFY <span className="font-medium text-accent-soft">SUITE</span>
            </span>
          </div>

          <form onSubmit={submit} className="my-auto w-full max-w-sm space-y-5 py-10 lg:py-14">
            <div className="anim-rise" style={at(120)}>
              <h1 className="text-xl font-semibold text-white">Sign in to UNIFY</h1>
              <p className="mt-2 text-sm text-slate-400">
                Your AI workforce for sales, finance, hiring, support and procurement.
              </p>
            </div>

            <label className="anim-rise block space-y-1.5 text-sm" style={at(170)}>
              <span className="text-slate-300">Email</span>
              <span className="relative block">
                <MailIcon
                  size={17}
                  className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-slate-500"
                />
                <input
                  className={field}
                  type="email"
                  autoComplete="username"
                  placeholder="you@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </span>
            </label>

            <label className="anim-rise block space-y-1.5 text-sm" style={at(210)}>
              <span className="text-slate-300">Password</span>
              <span className="relative block">
                <LockIcon
                  size={17}
                  className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-slate-500"
                />
                <input
                  className={`${field} pr-11`}
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                  className="absolute top-1/2 right-1.5 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-md text-slate-500 transition-colors hover:bg-white/5 hover:text-slate-200"
                >
                  {showPassword ? <EyeOffIcon size={17} /> : <EyeIcon size={17} />}
                </button>
              </span>
            </label>

            {error && (
              <div key={failures} className="anim-shake">
                <ErrorNote message={error} />
              </div>
            )}

            <div className="anim-rise" style={at(250)}>
              <button
                type="submit"
                disabled={busy}
                className={`${primaryButton} flex h-11 w-full items-center justify-center gap-2`}
              >
                {busy && (
                  <span
                    className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"
                    aria-hidden="true"
                  />
                )}
                {busy ? "Signing in…" : "Sign in"}
              </button>
            </div>
          </form>

          <p className="anim-rise text-xs text-slate-500" style={at(290)}>
            Runs on Vultr: one cloud VM, Coolify, and Vultr Serverless Inference.
          </p>
        </section>

        {/* Right: what the product does, as a short moving story */}
        <section className="dot-grid relative overflow-hidden rounded-2xl bg-violet-700 px-5 py-8 sm:px-10 lg:px-12 lg:py-12">
          <p
            className="anim-rise text-xs font-semibold tracking-wider text-violet-200 uppercase"
            style={at(160)}
          >
            How UNIFY works
          </p>
          <h2
            className="anim-rise mt-3 max-w-md text-2xl leading-tight font-semibold text-white sm:text-[28px]"
            style={at(200)}
          >
            AI does the reading. Your managers make the call.
          </h2>
          <p className="anim-rise mt-3 max-w-md text-sm text-violet-100/85" style={at(240)}>
            Five departments, one agent each. Code checks the numbers, and nothing important happens
            until a person approves it.
          </p>
          <div className="anim-rise mt-8" style={at(320)}>
            <LoginShowcase />
          </div>
        </section>
      </div>
    </main>
  );
}
