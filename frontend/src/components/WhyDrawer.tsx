import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api, ApiError } from "../api";
import { when } from "../format";
import type { Explanation } from "../types";
import {
  CheckIcon,
  CloseIcon,
  CodeIcon,
  EyeIcon,
  QuestionIcon,
  SparkleIcon,
  UsersIcon,
} from "./icons";

function Section({
  icon,
  title,
  hint,
  children,
}: {
  icon: ReactNode;
  title: string;
  hint: string;
  children: ReactNode;
}) {
  return (
    <section className="border-t border-white/5 px-5 py-4">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
        <span className="grid h-6 w-6 place-items-center rounded-md bg-accent-purple/15 text-violet-300">
          {icon}
        </span>
        {title}
      </h3>
      <p className="mt-0.5 mb-3 pl-8 text-xs text-slate-500">{hint}</p>
      <div className="pl-8">{children}</div>
    </section>
  );
}

function Fields({ fields }: { fields: Explanation["ai_read"] }) {
  return (
    <dl className="space-y-2 text-sm">
      {fields.map((f, i) => (
        <div key={`${f.label}-${i}`}>
          <dt className="text-[11px] text-slate-500 first-letter:uppercase">{f.label}</dt>
          <dd className="mt-0.5 break-words whitespace-pre-wrap text-slate-200">
            {f.value || "—"}
          </dd>
        </div>
      ))}
    </dl>
  );
}

const EXIT_MS = 220; // matches .anim-drawer-out

/** Side panel: what the AI read, what it said, what code decided, who was involved. */
function WhyDrawer({
  path,
  verifiable,
  onClose,
}: {
  path: string;
  verifiable: boolean;
  onClose: () => void;
}) {
  const [data, setData] = useState<Explanation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null); // nothing AI-made to explain
  // Closing plays the slide-out first; the drawer unmounts once it is over (a timer, so a tab that
  // isn't painting still closes).
  const [leaving, setLeaving] = useState(false);
  const close = useCallback(() => {
    setLeaving(true);
    window.setTimeout(onClose, EXIT_MS);
  }, [onClose]);

  useEffect(() => {
    let live = true;
    api<Explanation>(`/explain/${path}`)
      .then((d) => live && setData(d))
      .catch((e) => {
        if (!live) return;
        if (e instanceof ApiError && e.code === "no_ai_result") setNotice(e.message);
        else setError(e instanceof Error ? e.message : "Could not load");
      });
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("keydown", onKey);
    return () => {
      live = false;
      document.removeEventListener("keydown", onKey);
    };
  }, [path, close]);

  return (
    <div className="fixed inset-0 z-[70] flex justify-end">
      <button
        aria-label="Close"
        onClick={close}
        className={`${leaving ? "anim-fade-out" : "anim-fade"} absolute inset-0 bg-[var(--overlay)] backdrop-blur-[2px]`}
      />
      <aside
        role="dialog"
        aria-label="Why the AI said this"
        className={`${leaving ? "anim-drawer-out" : "anim-drawer-in"} relative flex h-full w-full max-w-lg flex-col overflow-hidden border-l border-white/10 bg-navy-900 shadow-2xl shadow-black/60`}
      >
        <header className="flex items-start gap-3 border-b border-white/5 px-5 py-4">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-accent-purple/25 text-accent-soft">
            <QuestionIcon />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold text-accent-soft">Why?</p>
            <h2 className="text-base font-semibold text-white">
              {data?.title ?? (notice ? "Nothing from the AI here" : "Loading…")}
            </h2>
            {data && (
              <p className="mt-0.5 text-xs text-slate-400">
                {data.agent}
                {data.model ? ` · ${data.model} on Vultr Serverless Inference` : ""}
              </p>
            )}
          </div>
          <button onClick={close} aria-label="Close" className="text-slate-400 hover:text-white">
            <CloseIcon />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto pb-6">
          {error && <p className="px-5 py-4 text-sm text-red-300">{error}</p>}
          {notice && <p className="px-5 py-4 text-sm text-slate-300">{notice}.</p>}
          {!data && !error && !notice && (
            <div className="space-y-3 px-5 py-5">
              {[0, 1, 2].map((n) => (
                <div key={n} className="h-16 animate-pulse rounded-xl bg-white/[0.04]" />
              ))}
            </div>
          )}
          {data && (
            <div className="stagger">
              <Section
                icon={<EyeIcon size={14} />}
                title="What the AI read"
                hint="The exact input the agent was given, nothing more."
              >
                {verifiable &&
                  (data.input_verified ? (
                    <p className="mb-3 flex items-start gap-1.5 rounded-lg bg-emerald-500/10 px-2.5 py-1.5 text-xs text-emerald-200">
                      <CheckIcon size={14} className="mt-px shrink-0" />
                      Verified: this input has the same fingerprint (SHA-256) as the logged call.
                    </p>
                  ) : (
                    <p className="mb-3 rounded-lg bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-200">
                      The record was edited after the AI ran, so this is what it would read now, not
                      necessarily what it read then.
                    </p>
                  ))}
                <Fields fields={data.ai_read} />
                {data.ai_read_note && (
                  <p className="mt-3 text-xs text-slate-400">{data.ai_read_note}</p>
                )}
              </Section>
              <Section
                icon={<SparkleIcon size={14} />}
                title="What the AI said"
                hint="Its reply, after it passed validation."
              >
                <Fields fields={data.ai_said} />
              </Section>
              <Section
                icon={<CodeIcon size={14} />}
                title="What code decided"
                hint="Plain rules. The AI cannot change these."
              >
                <ul className="space-y-1.5 text-sm text-slate-200">
                  {data.code_decided.map((line) => (
                    <li key={line} className="flex gap-2">
                      <CheckIcon size={15} className="mt-0.5 shrink-0 text-accent-soft" />
                      {line}
                    </li>
                  ))}
                </ul>
              </Section>
              {data.calls.length > 0 && (
                <Section
                  icon={<SparkleIcon size={14} />}
                  title="Agent calls"
                  hint="From the activity log (Command Center)."
                >
                  <ul className="space-y-1 text-xs text-slate-300">
                    {data.calls.map((c) => (
                      <li key={c.task_id} className="flex flex-wrap gap-x-2">
                        <span
                          className={c.status === "failed" ? "text-red-300" : "text-emerald-300"}
                        >
                          {c.status}
                        </span>
                        <span>attempt {c.attempt}</span>
                        {c.duration_ms !== null && (
                          <span>{(c.duration_ms / 1000).toFixed(1)} s</span>
                        )}
                        <span className="text-slate-500">{when(c.at)}</span>
                        {c.error && <span className="w-full text-red-300/80">{c.error}</span>}
                      </li>
                    ))}
                  </ul>
                </Section>
              )}
              <Section
                icon={<UsersIcon size={14} />}
                title="Who was involved"
                hint="People's actions, from the audit log."
              >
                {data.people.length === 0 && <p className="text-sm text-slate-500">No one yet.</p>}
                <ol className="relative space-y-3 border-l border-white/10 pl-4">
                  {data.people.map((p, i) => (
                    <li key={i} className="text-sm">
                      <span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full bg-accent-purple" />
                      <span className="text-slate-100">{p.who}</span>{" "}
                      <span className="text-slate-300">{p.did}</span>
                      <span className="block text-xs text-slate-500">{when(p.at)}</span>
                    </li>
                  ))}
                </ol>
              </Section>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

/** Small "Why?" pill that opens the drawer for one AI result. */
export function WhyButton({ path, verifiable = true }: { path: string; verifiable?: boolean }) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []); // stable, so the drawer loads once
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1 rounded-full border border-accent-soft/30 px-2 py-0.5 text-xs text-accent-soft hover:bg-accent-soft/10"
      >
        <QuestionIcon size={13} /> Why?
      </button>
      {open && <WhyDrawer path={path} verifiable={verifiable} onClose={close} />}
    </>
  );
}
