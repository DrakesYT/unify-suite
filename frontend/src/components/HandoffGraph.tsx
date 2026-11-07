import { Link } from "react-router";
import { ago, label } from "../format";
import type { Handoff, HandoffNode, StepStatus } from "../types";

// Stroke colour per real step status. Flat colours only; purple is reserved for "working now".
const TONE: Record<StepStatus, string> = {
  succeeded: "#34d399",
  running: "#8b5cf6",
  waiting_approval: "#fbbf24",
  failed: "#f87171",
  rejected: "#f87171",
  pending: "#475569",
  skipped: "#334155",
};
const KIND: Record<HandoffNode["kind"], string> = {
  agent: "AI agent",
  rules: "Plain code",
  human: "Human",
  tool: "Tool",
};
const ACTIVE: StepStatus[] = ["running", "waiting_approval"];

const W = 150; // node width
const H = 72;
const GAP = 40;
const PAD = 14;

/** Workflow B as a hand-off: each stop is coloured by the latest real status of its step. */
export function HandoffGraph({ run }: { run: Handoff | null }) {
  if (!run) {
    return (
      <p className="py-10 text-center text-sm text-slate-500">
        No supplier-payment run yet. Start one from Payments and it appears here.
      </p>
    );
  }
  const nodes = run.nodes;
  const width = PAD * 2 + nodes.length * W + (nodes.length - 1) * GAP;
  const height = H + PAD * 2;
  const x = (i: number) => PAD + i * (W + GAP);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400">
        <span>
          Latest run{run.file_name ? `: ${run.file_name}` : ""} · {label(run.status)} ·{" "}
          {ago(run.updated_at)}
        </span>
        <Link to={`/payments/${run.execution_id}`} className="text-accent-soft hover:underline">
          open run
        </Link>
      </div>
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="mx-auto block min-w-[700px]"
          role="img"
          aria-label={`Hand-off: ${nodes.map((n) => `${n.label} ${label(n.status)}`).join(", then ")}`}
        >
          <defs>
            <marker
              id="handoff-arrow"
              viewBox="0 0 8 8"
              refX="7"
              refY="4"
              markerWidth="7"
              markerHeight="7"
              orient="auto"
            >
              <path d="M0 0 L8 4 L0 8 z" fill="context-stroke" />
            </marker>
          </defs>
          {nodes.slice(1).map((node, i) => {
            const from = nodes[i];
            const done = from.status === "succeeded";
            const live = done && ACTIVE.includes(node.status);
            const colour = done ? TONE.succeeded : TONE.pending;
            return (
              <line
                key={`${from.key}-${node.key}`}
                x1={x(i) + W}
                y1={PAD + H / 2}
                x2={x(i + 1) - 2}
                y2={PAD + H / 2}
                stroke={live ? TONE[node.status] : colour}
                strokeWidth={2}
                markerEnd="url(#handoff-arrow)"
                className={live ? "flow-dash" : undefined}
              />
            );
          })}
          {nodes.map((n, i) => {
            const colour = TONE[n.status];
            const active = ACTIVE.includes(n.status);
            return (
              <g key={n.key} transform={`translate(${x(i)} ${PAD})`}>
                <title>{`${n.label}: ${label(n.status)}${n.attempts > 1 ? `, attempt ${n.attempts}` : ""}`}</title>
                <rect
                  width={W}
                  height={H}
                  rx={12}
                  fill="#070b1a"
                  stroke={colour}
                  strokeWidth={active ? 2 : 1.5}
                  strokeDasharray={n.status === "skipped" ? "4 4" : undefined}
                  className={active ? "anim-working" : undefined}
                />
                <circle cx={16} cy={18} r={4} fill={colour} />
                <text x={28} y={22} fontSize={13} fontWeight={600} fill="#f1f5f9">
                  {n.label}
                </text>
                <text x={16} y={44} fontSize={11} fill="#94a3b8">
                  {KIND[n.kind]} · {label(n.status)}
                </text>
                <text x={16} y={60} fontSize={11} fill="#64748b">
                  {n.duration_ms !== null ? `${n.duration_ms} ms` : "—"}
                  {n.attempts > 1 ? ` · try ${n.attempts}` : ""}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
