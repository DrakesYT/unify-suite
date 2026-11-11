import { useState, type FormEvent } from "react";
import { BriefcaseIcon, ListIcon, PlusIcon, UsersIcon } from "../components/icons";
import { api } from "../api";
import {
  Card,
  Empty,
  ErrorNote,
  PageHeader,
  ghostButton,
  inputClass,
  primaryButton,
  Loading,
} from "../components/ui";
import { EmailPanel } from "../components/EmailPanel";
import { when } from "../format";
import { canWrite, useAuth } from "../session";
import type { Candidate, CandidateScore, Job, Page } from "../types";
import { usePoll } from "../usePoll";
import { WhyButton } from "../components/WhyDrawer";
import { toast } from "../toast";

const INTERVIEW_MIN_SCORE = 50; // mirrors the backend rule; the backend enforces it

function NewJob({ onCreated }: { onCreated: (job: Job) => void }) {
  const [title, setTitle] = useState("");
  const [skills, setSkills] = useState("");
  const [years, setYears] = useState("0");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const job = await api<Job>("/hr/jobs", {
        method: "POST",
        body: JSON.stringify({
          title,
          required_skills: skills
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          min_years: Number(years || 0),
        }),
      });
      setTitle("");
      setSkills("");
      setYears("0");
      toast(`Job added: ${job.title}`);
      onCreated(job);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the job");
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      <input
        className={inputClass}
        placeholder="Job title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        required
      />
      <input
        className={inputClass}
        placeholder="Required skills, comma separated (Python, PostgreSQL, Docker)"
        value={skills}
        onChange={(e) => setSkills(e.target.value)}
        required
      />
      <div className="flex gap-3">
        <input
          className={inputClass}
          type="number"
          min="0"
          max="40"
          value={years}
          onChange={(e) => setYears(e.target.value)}
          aria-label="Minimum years of experience"
        />
        <button type="submit" className={`${primaryButton} whitespace-nowrap`}>
          Add job
        </button>
      </div>
      <p className="text-xs text-slate-500">Last field: minimum years of experience.</p>
      <ErrorNote message={error} />
    </form>
  );
}

function ResumeUpload({ job, onUploaded }: { job: Job | null; onUploaded: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    const body = new FormData();
    body.append("file", file);
    if (job) body.append("job_id", job.id); // they apply for the job being looked at
    try {
      const c = await api<Candidate>("/hr/candidates/upload", { method: "POST", body });
      setMessage(`Added ${c.name}: ${c.skills.length} skills, ${c.years_experience ?? 0} years`);
      toast(`Resume read: ${c.name}`);
      onUploaded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      <input
        type="file"
        accept=".pdf,.txt"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        className={`${inputClass} file:mr-3 file:rounded-md file:border-0 file:bg-navy-800 file:px-3 file:py-1 file:text-slate-200`}
        required
      />
      <button type="submit" disabled={busy || !file} className={`${primaryButton} w-full`}>
        {busy ? "Reading resume…" : "Upload resume"}
      </button>
      {message && <p className="text-sm text-emerald-300">{message}</p>}
      <ErrorNote message={error} />
    </form>
  );
}

const STRONG_MIN_SCORE = 75; // same band as the green score bar

/** Stages come from the screening scores that already exist: nothing is invented. */
function JobFunnel({ job, scores }: { job: Job; scores: CandidateScore[] }) {
  const screened = scores.length;
  const qualified = scores.filter((s) => s.score >= INTERVIEW_MIN_SCORE).length;
  const strong = scores.filter((s) => s.score >= STRONG_MIN_SCORE).length;
  const stages = [
    { name: "Applied", n: job.applicants, of: job.applicants },
    { name: "Screened", n: screened, of: job.applicants },
    { name: `Score ${INTERVIEW_MIN_SCORE}+`, n: qualified, of: screened },
    { name: `Score ${STRONG_MIN_SCORE}+`, n: strong, of: qualified },
  ];
  const pct = (n: number, of: number) => (of > 0 ? Math.round((n / of) * 100) : 0);
  const done = pct(screened, job.applicants);
  const r = 44;
  const circ = 2 * Math.PI * r;
  return (
    <div className="mb-5 grid gap-4 md:grid-cols-[200px_1fr]">
      <div className="flex flex-col items-center justify-center rounded-lg border border-navy-800 bg-navy-950/60 p-4">
        <svg
          width="112"
          height="112"
          viewBox="0 0 112 112"
          role="img"
          aria-label={`${done}% of applicants screened`}
        >
          <circle cx="56" cy="56" r={r} fill="none" strokeWidth="9" className="stroke-navy-800" />
          <circle
            cx="56"
            cy="56"
            r={r}
            fill="none"
            strokeWidth="9"
            strokeLinecap="round"
            className="stroke-accent-purple"
            strokeDasharray={circ}
            strokeDashoffset={circ * (1 - done / 100)}
            transform="rotate(-90 56 56)"
          />
          <text x="56" y="56" textAnchor="middle" className="fill-white text-xl font-semibold">
            {done}%
          </text>
          <text x="56" y="73" textAnchor="middle" className="fill-slate-500 text-[10px]">
            screened
          </text>
        </svg>
        <p className="mt-2 text-xs text-slate-500">Pipeline progress</p>
      </div>
      <div className="rounded-lg border border-navy-800 bg-navy-950/60 p-4">
        <h3 className="mb-3 text-xs font-semibold text-slate-400">Conversion funnel</h3>
        <ul className="space-y-2.5">
          {stages.map((st, i) => (
            <li key={st.name}>
              <div className="flex justify-between text-xs">
                <span className="text-slate-300">{st.name}</span>
                <span className="text-slate-400">
                  {st.n}
                  {i > 0 && ` (${pct(st.n, st.of)}%)`}
                </span>
              </div>
              <div className="mt-1 h-2 rounded-full bg-navy-800">
                <div
                  className="h-2 rounded-full bg-accent-purple"
                  style={{ width: `${pct(st.n, job.applicants)}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function ScoreCard({
  s,
  jobId,
  editable,
}: {
  s: CandidateScore;
  jobId: string;
  editable: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [inviting, setInviting] = useState(false);
  const invitable = s.score >= INTERVIEW_MIN_SCORE && Boolean(s.candidate.email);
  const tone = s.score >= 75 ? "bg-emerald-400" : s.score >= 50 ? "bg-amber-400" : "bg-slate-500";
  return (
    <li className="rounded-lg border border-navy-800 bg-navy-950/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 font-medium text-slate-100">
            {s.candidate.name}
            <span className="rounded-full bg-accent-purple/20 px-2 py-0.5 text-xs font-medium text-accent-soft">
              {s.score}% match
            </span>
          </p>
          <p className="text-xs text-slate-500">
            {s.candidate.years_experience ?? 0} years · {s.candidate.email ?? "no email"}
          </p>
        </div>
        <div className="flex min-w-40 items-center gap-3">
          <div className="h-2 flex-1 rounded-full bg-navy-800">
            <div className={`h-2 rounded-full ${tone}`} style={{ width: `${s.score}%` }} />
          </div>
          <span className="w-8 text-right text-lg font-semibold text-white">{s.score}</span>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5 text-xs">
        {s.matched_skills.map((k) => (
          <span key={k} className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-emerald-300">
            ✓ {k}
          </span>
        ))}
        {s.missing_skills.map((k) => (
          <span key={k} className="rounded-full bg-slate-500/15 px-2 py-0.5 text-slate-400">
            ✗ {k}
          </span>
        ))}
      </div>
      <div className="mt-3 flex items-start justify-between gap-3">
        <p className="text-sm text-slate-300">{s.summary}</p>
        <WhyButton path={`candidate/${jobId}/${s.candidate.id}`} />
      </div>
      <button
        onClick={() => setOpen(!open)}
        className="mt-2 text-xs text-accent-soft hover:underline"
      >
        {open
          ? "Hide evidence"
          : `Show evidence (${s.evidence.length} ${s.evidence.length === 1 ? "quote" : "quotes"} from the resume)`}
      </button>
      {open && (
        <ul className="stagger mt-2 space-y-2">
          {s.evidence.map((e) => (
            <li
              key={e.requirement + e.quote}
              className="border-l-2 border-accent-purple pl-3 text-sm"
            >
              <span className="text-xs text-slate-500">{e.requirement}</span>
              <p className="text-slate-200 italic">“{e.quote}”</p>
            </li>
          ))}
        </ul>
      )}
      {editable && invitable && (
        <button onClick={() => setInviting(!inviting)} className={`${ghostButton} mt-3 block`}>
          {inviting ? "Hide interview invite" : "Invite to interview"}
        </button>
      )}
      {inviting && (
        <EmailPanel
          title="Interview invitation"
          intro="Code holds three free 45-minute times (office hours, never double-booked); the Interview Invite Writer drafts the invitation and must list every time exactly. Nothing is sent until an HR manager approves it."
          listPath={`/hr/jobs/${jobId}/candidates/${s.candidate.id}/emails`}
          emailsPath="/hr/emails"
          managerLabel="an HR manager"
          editable={editable}
        />
      )}
    </li>
  );
}

export function Hiring() {
  const { user } = useAuth();
  const editable = Boolean(user && canWrite(user, "hr"));
  const jobs = usePoll<Page<Job>>("/hr/jobs?status=open&limit=100");
  const [picked, setPicked] = useState<string | null>(null);
  const jobId = picked ?? jobs.data?.items[0]?.id ?? null;
  const job = jobs.data?.items.find((j) => j.id === jobId) ?? null;
  const scores = usePoll<CandidateScore[]>(jobId ? `/hr/jobs/${jobId}/scores` : null);
  const ranked = jobId ? (scores.data ?? []) : [];
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const screen = async () => {
    if (!jobId) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/hr/jobs/${jobId}/screen`, { method: "POST", body: JSON.stringify({}) });
      await Promise.all([scores.reload(), jobs.reload()]);
      toast("Screening done: the ranking is updated");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Screening failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="HR · Resume Screener agent"
        icon={<UsersIcon size={22} />}
        live
        title="Hiring"
        subtitle="The Resume Screener quotes the resume for every skill it credits; code checks each quote and computes the score."
      />
      <div className="grid gap-6 xl:grid-cols-[320px_1fr]">
        <div className="space-y-6">
          <Card title="Open jobs" icon={<BriefcaseIcon size={16} />}>
            <ErrorNote message={jobs.error} />
            {!jobs.data && !jobs.error && <Loading rows={2} />}
            {jobs.data?.items.length === 0 && <Empty>No open jobs.</Empty>}
            <ul className="space-y-1">
              {jobs.data?.items.map((j) => (
                <li key={j.id}>
                  <button
                    onClick={() => setPicked(j.id)}
                    className={`w-full rounded-lg px-3 py-2 text-left text-sm ${
                      j.id === jobId
                        ? "bg-accent-purple/20 text-white"
                        : "text-slate-300 hover:bg-navy-800"
                    }`}
                  >
                    {j.title}
                    <span className="block text-xs text-slate-500">
                      {j.required_skills.join(", ")} · {j.min_years}+ years
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
          {editable && (
            <>
              <Card title="New job" icon={<PlusIcon size={16} />}>
                <NewJob onCreated={(j) => (setPicked(j.id), void jobs.reload())} />
              </Card>
              <Card title="Add a candidate" icon={<PlusIcon size={16} />}>
                <ResumeUpload job={job} onUploaded={() => void jobs.reload()} />
                <p className="mt-3 text-xs text-slate-500">
                  {job
                    ? `Adds an applicant for ${job.title}. ${job.applicants} applicants, ${job.unscreened} not screened yet.`
                    : "Pick a job first: the candidate applies for it."}
                </p>
              </Card>
            </>
          )}
        </div>
        <Card
          title={job ? `Ranking: ${job.title}` : "Ranking"}
          icon={<ListIcon size={16} />}
          actions={
            editable && job ? (
              <button
                onClick={screen}
                disabled={busy || job.unscreened === 0}
                className={ghostButton}
                title={job.unscreened === 0 ? "Everyone who applied is screened" : undefined}
              >
                {busy ? "Screening…" : `Screen new applicants (${job.unscreened})`}
              </button>
            ) : undefined
          }
        >
          <ErrorNote message={error} />
          {!jobs.data && <Loading rows={3} />}
          {jobs.data && !job && <Empty>Add a job to start screening.</Empty>}
          {job && scores.data && ranked.length === 0 && (
            <Empty hint="Add a candidate for this job, then press “Screen new applicants”.">
              No one screened for this job yet.
            </Empty>
          )}
          {job && scores.data && <JobFunnel job={job} scores={ranked} />}
          <ol className="space-y-3">
            {ranked.map((s) => (
              <ScoreCard key={s.candidate.id} s={s} jobId={job!.id} editable={editable} />
            ))}
          </ol>
          {ranked[0] && (
            <p className="mt-4 text-xs text-slate-500">
              Last screened {when(ranked[0].updated_at)}
            </p>
          )}
        </Card>
      </div>
    </>
  );
}
