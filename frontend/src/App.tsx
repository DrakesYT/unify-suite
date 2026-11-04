import { useEffect, useState } from "react";
import { api } from "./api";

const POLL_MS = 5000;

type Health = "checking" | "ok" | "down";

export default function App() {
  const [health, setHealth] = useState<Health>("checking");

  useEffect(() => {
    const check = () =>
      api<{ status: string }>("/health")
        .then(() => setHealth("ok"))
        .catch(() => setHealth("down"));
    check();
    const id = setInterval(check, POLL_MS);
    return () => clearInterval(id);
  }, []);

  const pill = {
    checking: "bg-slate-700 text-slate-200",
    ok: "bg-accent-cyan/15 text-accent-cyan",
    down: "bg-red-500/15 text-red-400",
  }[health];

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 px-4">
      <h1 className="bg-gradient-to-r from-accent-purple to-accent-cyan bg-clip-text text-4xl font-bold tracking-tight text-transparent">
        UNIFY SUITE
      </h1>
      <p className="text-slate-400">AI workforce platform — powered by Vultr</p>
      <span className={`rounded-full px-4 py-1 text-sm font-medium ${pill}`}>
        API + database: {health}
      </span>
    </main>
  );
}
