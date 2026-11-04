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
    title?: string;
    category?: string;
    urgency?: string;
    customer_name?: string | null;
    note?: string;
    likely_cause?: string | null;
    item?: string | null;
    quantity?: number | null;
    budget_minor?: number | null;
    over_budget?: boolean;
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

export type LeadStatus = "new" | "contacted" | "qualified" | "won" | "lost";
export type Priority = "low" | "medium" | "high";

export interface Lead {
  id: string;
  name: string;
  company: string;
  email: string;
  status: LeadStatus;
  priority: Priority;
  value_minor: number;
  currency: string;
  notes: string;
  rating: "hot" | "warm" | "cold" | null;
  qualification: {
    rating: string;
    reason: string;
    cited_fields: string[];
    model: string;
    qualified_at: string;
  } | null;
  owner_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Job {
  id: string;
  title: string;
  required_skills: string[];
  min_years: number;
  status: "open" | "closed";
  created_at: string;
}

export interface Candidate {
  id: string;
  name: string;
  email: string | null;
  skills: string[];
  years_experience: number | null;
  education: string[];
  file_id: string | null;
  created_at: string;
}

export interface CandidateScore {
  candidate: Candidate;
  score: number;
  matched_skills: string[];
  missing_skills: string[];
  evidence: { requirement: string; quote: string }[];
  summary: string;
  updated_at: string;
}

export type TicketCategory =
  "billing" | "technical" | "shipping" | "refund" | "legal" | "account" | "other";

export interface Ticket {
  id: string;
  title: string;
  description: string;
  category: TicketCategory | null;
  urgency: "low" | "normal" | "high" | "critical" | null;
  status: "open" | "investigating" | "escalated" | "resolved" | "closed";
  customer_id: string | null;
  investigation: {
    likely_causes: { cause: string; order_numbers: string[] }[];
    order_numbers_used: string[];
    next_step: string;
    draft_reply: string;
    investigated_at: string;
  } | null;
  created_at: string;
  updated_at: string;
}

export interface Customer {
  id: string;
  name: string;
  company: string | null;
  email: string | null;
}

export interface Vendor {
  id: string;
  name: string;
  contact: string | null;
  lead_time_days: number;
  on_time_rate: string;
  created_at: string;
}

export interface RankedVendor {
  rank: number;
  vendor_id: string;
  vendor_name: string;
  total_minor: number;
  currency: string;
  lead_time_days: number;
  on_time_rate: string;
  price_score: string;
  lead_time_score: string;
  delivery_score: string;
  score: string;
  over_budget: boolean;
}

export interface VendorComparison {
  request_id: string;
  ranking: RankedVendor[];
  reason: string | null;
  reason_error: string | null;
  compared_at: string;
}

export interface PurchaseRequest {
  id: string;
  item: string;
  quantity: number;
  budget_minor: number;
  currency: string;
  status: "pending" | "approved" | "rejected" | "ordered";
  chosen_vendor_id: string | null;
  requested_by_id: string | null;
  comparison: VendorComparison | null;
  created_at: string;
}

export interface Quote {
  id: string;
  request_id: string;
  vendor_id: string;
  unit_price_minor: number;
  currency: string;
}

export interface PurchaseOrder {
  id: string;
  po_number: string;
  vendor_id: string;
  request_id: string | null;
  amount_minor: number;
  currency: string;
  status: "pending_approval" | "approved" | "rejected";
  created_at: string;
}

export interface Money {
  amount_minor: number;
  currency: string;
}

export interface Kpis {
  sales_pipeline: Money[];
  unpaid_invoices: Money[];
  open_vacancies: number;
  open_tickets: number;
  pending_purchase_requests: number;
  pending_approvals: number;
}

export interface Charts {
  leads_by_rating: { label: string; value: number }[];
  tickets_by_category: { label: string; value: number }[];
  invoices_by_match: { label: string; value: number }[];
  agent_calls_by_day: { day: string; succeeded: number; failed: number }[];
}

export interface ActivityItem {
  id: string;
  at: string;
  actor_name: string | null;
  action: string;
  entity: string;
  entity_id: string | null;
  detail: Record<string, unknown>;
}

export interface AuraReply {
  route: string;
  agent: string | null;
  reply: string;
  outcome: "done" | "needs_input" | "not_found" | "not_allowed" | "failed" | "no_route";
  summary: string;
  link: string | null;
}
