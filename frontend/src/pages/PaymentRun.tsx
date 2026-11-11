import { useState } from "react";
import { BoltIcon, FileIcon, FlowIcon, ShieldIcon } from "../components/icons";
import { Link, useParams } from "react-router";
import { api } from "../api";
import { canWrite, useAuth } from "../session";
import {
  Badge,
  Card,
  ErrorNote,
  InjectionWarning,
  PageHeader,
  ghostButton,
  Loading,
} from "../components/ui";
import { label, money, when } from "../format";
import type { AgentTask, Execution, Page, Step } from "../types";
import { usePoll } from "../usePoll";
import { WhyButton } from "../components/WhyDrawer";
import { toast } from "../toast";

function StepDetail({ step }: { step: Step }) {
  const out = step.output ?? {};
  if (step.error) return <p className="text-sm text-red-300">{step.error}</p>;
  if (step.key === "F1" && step.status === "succeeded")
    return (
      <>
        <p className="text-sm text-slate-400">
          {String(out.vendor_name)} · invoice {String(out.number)} · {String(out.total_amount)}{" "}
          {String(out.currency)}
        </p>
        <InjectionWarning lines={out.suspicious_text as string[] | undefined} />
      </>
    );
  if (step.key === "F2" && step.status === "succeeded")
    return (
      <p className="text-sm text-slate-400">
        <Badge value={String(out.match_status)} />{" "}
        {money(out.amount_minor as number, out.currency as string)}
      </p>
    );
  if (step.key === "F3" && step.status === "succeeded")
    return (
      <ul className="list-disc pl-5 text-sm text-amber-200">
        {(out.lines as string[]).map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    );
  if (step.key === "A1" && out.decision)
    return (
      <p className="text-sm text-slate-400">
        {label(String(out.decision))}
        {out.comment ? ` — “${String(out.comment)}”` : ""}
      </p>
    );
  return null;
}

export function PaymentRun() {
  const { id } = useParams();
  const { user } = useAuth();
  const [retryError, setRetryError] = useState<string | null>(null);
  const run = usePoll<Execution>(`/workflows/${id}`);
  const tasks = usePoll<Page<AgentTask>>(`/agents/activity?execution_id=${id}&limit=100`);

  const data = run.data;
  const retry = async () => {
    setRetryError(null);
    try {
      await api(`/workflows/${id}/retry`, { method: "POST" });
      toast("Retry started", "info");
      await run.reload();
    } catch (e) {
      setRetryError(e instanceof Error ? e.message : "Retry failed");
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Finance · supplier payment run"
        icon={<FileIcon size={22} />}
        live
        title={data?.input.file_name ?? "Payment run"}
        subtitle={
          data ? `PO ${data.input.po_number} · started ${when(data.created_at)}` : undefined
        }
      />
      {data && (
        <div className="-mt-3 mb-5">
          <WhyButton path={`run/${data.id}`} />
        </div>
      )}
      <ErrorNote message={run.error} />
      {!data && !run.error && <Loading rows={6} />}
      {data && (
        <div className="grid gap-6 xl:grid-cols-[2fr_1fr]">
          <Card
            title="Steps"
            icon={<FlowIcon size={16} />}
            actions={
              <div className="flex items-center gap-3">
                <Badge value={data.status} />
                {data.status === "failed" && user && canWrite(user, "finance") && (
                  <button onClick={retry} className={ghostButton}>
                    Retry failed step
                  </button>
                )}
              </div>
            }
          >
            <ErrorNote message={retryError} />
            <ol className="stagger space-y-3">
              {data.steps.map((step) => (
                <li key={step.key} className="rounded-lg border border-navy-800 bg-navy-950/60 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-sm">
                      <span className="mr-2 font-mono text-xs text-slate-500">{step.key}</span>
                      <span className="text-slate-100">{step.title}</span>
                      {step.department && (
                        <span className="ml-2 text-xs text-slate-500">{step.department}</span>
                      )}
                    </div>
                    <Badge value={step.status} />
                  </div>
                  <div className="mt-1.5">
                    <StepDetail step={step} />
                  </div>
                </li>
              ))}
            </ol>
            {data.status === "waiting_approval" && data.approval && (
              <p className="mt-4 text-sm text-amber-200">
                Waiting for a finance manager in the{" "}
                <Link to="/approvals" className="underline">
                  Approval Center
                </Link>
                .
              </p>
            )}
          </Card>
          <div className="space-y-6">
            {data.result && (
              <Card title="Verification" icon={<ShieldIcon size={16} />}>
                <p
                  className={`mb-3 text-sm font-medium ${data.result.passed ? "text-emerald-300" : "text-red-300"}`}
                >
                  {data.result.passed
                    ? "All records are linked correctly"
                    : "Verification found a problem"}
                </p>
                <ul className="space-y-1 text-sm">
                  {data.result.checks.map((c) => (
                    <li key={c.name} className={c.ok ? "text-slate-300" : "text-red-300"}>
                      {c.ok ? "✓" : "✗"} {c.name}
                    </li>
                  ))}
                </ul>
              </Card>
            )}
            <Card title="Agent calls" icon={<BoltIcon size={16} />}>
              <ul className="space-y-2 text-sm">
                {(tasks.data?.items ?? []).map((t) => (
                  <li key={t.id} className="flex items-center justify-between gap-2">
                    <span className="truncate text-slate-300">
                      {t.agent}
                      {t.tool && <span className="text-slate-500"> → {t.tool}</span>}
                    </span>
                    <span className="flex items-center gap-2 text-xs text-slate-500">
                      {t.duration_ms ?? "—"} ms <Badge value={t.status} />
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
