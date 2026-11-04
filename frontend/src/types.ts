/** Shapes returned by the backend API. */

export type Role = "admin" | "manager" | "employee" | "executive";
export type Department = "sales" | "finance" | "hr" | "support" | "procurement";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  department: Department;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export type ExecutionStatus =
  "running" | "waiting_approval" | "approved" | "rejected" | "failed" | "completed";

export type StepStatus =
  "pending" | "running" | "succeeded" | "failed" | "waiting_approval" | "rejected" | "skipped";

export interface Step {
  key: string;
  title: string;
  department: Department | null;
  status: StepStatus;
  attempts: number;
  output: Record<string, unknown> | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface Approval {
  id: string;
  action: string;
  payload: {
    invoice_number?: string;
    vendor_name?: string;
    po_number?: string;
    amount_minor?: number;
    currency?: string;
    match_status?: string;
    discrepancies?: string[];
  };
  required_role: Role;
  department: Department;
  status: "pending" | "approved" | "rejected" | "cancelled";
  execution_id: string | null;
  requested_by_id: string | null;
  decided_by_id: string | null;
  decided_at: string | null;
  comment: string | null;
  created_at: string;
}

export interface ExecutionSummary {
  id: string;
  workflow: string;
  status: ExecutionStatus;
  input: { po_number?: string; file_name?: string };
  started_by_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Execution extends ExecutionSummary {
  steps: Step[];
  approval: Approval | null;
  result: { passed: boolean; checks: { name: string; ok: boolean }[] } | null;
}

export interface AgentTask {
  id: string;
  agent: string;
  tool: string | null;
  execution_id: string | null;
  input_hash: string;
  output: unknown;
  status: "running" | "succeeded" | "failed";
  attempt: number;
  duration_ms: number | null;
  error: string | null;
  created_at: string;
}
