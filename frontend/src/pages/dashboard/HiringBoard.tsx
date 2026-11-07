import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { UsersIcon } from "../../components/icons";
import { initials } from "../../format";
import type { HiringStageKey, Overview } from "../../types";
import { QUIET, TOOLTIP } from "./chartStyle";
import { Panel, Quiet } from "./parts";

const CARDS_SHOWN = 3;
const STAGES: Record<HiringStageKey, { title: string; hint: string; bar: string }> = {
  applied: { title: "Applied", hint: "resume received", bar: "bg-slate-400" },
  screened: { title: "Screened", hint: "scored against a job", bar: "bg-accent-purple" },
  invite_pending: { title: "Invite pending", hint: "waiting for a manager", bar: "bg-amber-400" },
  invite_sent: { title: "Invited", hint: "interview invite sent", bar: "bg-accent-soft" },
};

function scoreTone(score: number): string {
  if (score >= 75) return "bg-emerald-400";
  if (score >= 50) return "bg-amber-400";
  return "bg-rose-400";
}

export function HiringBoard({ hiring }: { hiring: Overview["hiring"] }) {
  const total = hiring.stages.reduce((n, s) => n + s.count, 0);
  const trend = hiring.applications_by_day.map((d) => ({ day: d.label.slice(5), value: d.value }));

  return (
    <Panel
      title="Hiring pipeline"
      icon={<UsersIcon size={17} />}
      to="/hr"
      aside={
        <span className="mr-2 text-xs text-slate-500">
          {total} candidates · {hiring.open_jobs} open {hiring.open_jobs === 1 ? "job" : "jobs"}
        </span>
      }
    >
      {total === 0 ? (
        <Quiet>No candidates yet. Upload a resume on the Hiring page.</Quiet>
      ) : (
        <div className="-mx-1 overflow-x-auto px-1 pb-1">
          <div className="grid min-w-[520px] grid-cols-4 gap-2">
            {hiring.stages.map((stage) => {
              const meta = STAGES[stage.stage];
              return (
                <div
                  key={stage.stage}
                  className="rounded-xl bg-navy-950/60 p-2 ring-1 ring-white/5"
                >
                  <div className={`mb-2 h-0.5 rounded-full ${meta.bar}`} />
                  <p className="flex items-baseline justify-between px-1 text-xs font-medium text-slate-200">
                    {meta.title}
                    <span className="text-slate-500">{stage.count}</span>
                  </p>
                  <p className="mb-2 truncate px-1 text-[10px] text-slate-500">{meta.hint}</p>
                  <ul className="space-y-1.5">
                    {stage.cards.slice(0, CARDS_SHOWN).map((c) => (
                      <li
                        key={c.candidate_id}
                        className="rounded-lg bg-navy-900 p-2 ring-1 ring-white/[0.06]"
                      >
                        <div className="flex items-start gap-1.5">
                          <span className="grid h-5 w-5 mt-0.5 shrink-0 place-items-center rounded-full bg-white/10 text-[9px] font-semibold text-slate-200">
                            {initials(c.name)}
                          </span>
                          <span className="min-w-0">
                            <span className="block text-xs leading-tight break-words text-slate-100">
                              {c.name}
                            </span>
                            <span className="block truncate text-[10px] text-slate-500">
                              {c.job_title ?? "not screened yet"}
                            </span>
                          </span>
                        </div>
                        {c.score !== null && (
                          <div className="mt-1.5 flex items-center gap-1.5">
                            <span className="h-1 flex-1 overflow-hidden rounded-full bg-white/5">
                              <span
                                className={`block h-full rounded-full ${scoreTone(c.score)}`}
                                style={{ width: `${c.score}%` }}
                              />
                            </span>
                            <span className="text-[10px] text-slate-400">{c.score}% match</span>
                          </div>
                        )}
                      </li>
                    ))}
                    {stage.count > CARDS_SHOWN && (
                      <li className="px-1 text-[11px] text-slate-500">
                        +{stage.count - CARDS_SHOWN} more
                      </li>
                    )}
                    {stage.count === 0 && <li className="px-1 text-[11px] text-slate-600">—</li>}
                  </ul>
                </div>
              );
            })}
          </div>
        </div>
      )}
      <div className="mt-4">
        <p className="text-[11px] text-slate-500">Applications, last 14 days</p>
        <ResponsiveContainer width="100%" height={64}>
          <AreaChart data={trend} margin={{ top: 6, right: 0, bottom: 0, left: 0 }}>
            <XAxis dataKey="day" hide />
            <Tooltip {...TOOLTIP} cursor={{ fill: "rgb(255 255 255 / 0.03)" }} formatter={(v: number) => [v, "applications"]} />
            <Area
              type="monotone"
              dataKey="value"
              stroke={QUIET}
              strokeWidth={1.5}
              fill="rgb(100 116 139 / 0.12)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}
