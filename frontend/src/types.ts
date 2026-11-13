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
    suspicious_text?: string[];
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
    order_number?: string | null;
    refund_amount_minor?: number | null;
    company?: string | null;
    to?: string;
    subject?: string;
    body?: string;
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

export interface OutboundEmail {
  id: string;
  kind: string;
  lead_id: string | null;
  po_id: string | null;
  to_address: string;
  subject: string;
  body: string;
  status: "draft" | "pending_approval" | "sent" | "failed" | "rejected";
  approval_id: string | null;
  drafted_by_model: string | null;
  delivered_to: string | null;
  sent_at: string | null;
  error: string | null;
  created_at: string;
  style_notes: { rule: string; severity: "hard" | "soft"; text: string; advice: string }[];
}

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
  /** Candidates with a resume who applied for this job, and how many are not screened yet. */
  applicants: number;
  unscreened: number;
}

export interface Candidate {
  id: string;
  name: string;
  email: string | null;
  skills: string[];
  years_experience: number | null;
  education: string[];
  file_id: string | null;
  job_id: string | null;
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
  ordered_on: string | null;
  expected_delivery: string | null;
  delivered_on: string | null;
  delivery_status: "not_ordered" | "no_date" | "on_track" | "late" | "delivered";
  days_late: number;
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

export interface Receivable {
  order_id: string;
  order_number: string;
  customer_name: string;
  customer_company: string | null;
  customer_email: string | null;
  amount_minor: number;
  currency: string;
  ordered_on: string;
  due_on: string;
  days_overdue: number;
  status: "not_due" | "overdue" | "on_hold";
  hold_reason: string | null;
}

export interface Invoice {
  id: string;
  number: string;
  vendor_id: string;
  po_number: string | null;
  invoice_date: string;
  amount_minor: number;
  currency: string;
  status: "received" | "needs_review" | "approved" | "rejected" | "payment_submitted";
  match_status: "matched" | "mismatch" | "no_po" | null;
  created_at: string;
}

export interface Anomaly {
  id: string;
  kind: string;
  invoice_id: string | null;
  created_at: string;
}

export interface Count {
  label: string;
  value: number;
}

export type HiringStageKey = "applied" | "screened" | "invite_pending" | "invite_sent";

export interface Overview {
  insights: { tone: "alert" | "warn" | "good" | "info"; text: string; link: string }[];
  hiring: {
    open_jobs: number;
    stages: {
      stage: HiringStageKey;
      count: number;
      cards: {
        candidate_id: string;
        name: string;
        job_title: string | null;
        score: number | null;
      }[];
    }[];
    applications_by_day: Count[];
  };
  crm: {
    stages: { stage: LeadStatus; count: number; value: Money[] }[];
    pipeline: Money[];
    win_rate: number | null;
    won: number;
    lost: number;
    target: QuarterTarget;
    top_deals: {
      lead_id: string;
      company: string;
      contact: string;
      status: LeadStatus;
      rating: "hot" | "warm" | "cold" | null;
      amount_minor: number;
      currency: string;
    }[];
  };
  support: {
    open: number;
    by_urgency: Count[];
    by_category: Count[];
    tickets: {
      ticket_id: string;
      title: string;
      customer_name: string | null;
      category: string | null;
      urgency: string | null;
      status: string;
      created_at: string;
    }[];
  };
  money: {
    unpaid_invoices: Money[];
    invoices_to_review: number;
    invoices_to_pay: number;
    recent_invoices: {
      invoice_id: string;
      number: string;
      vendor_name: string;
      amount_minor: number;
      currency: string;
      status: string;
      match_status: string | null;
    }[];
    receivables_open: number;
    receivables_overdue: number;
    overdue_amount: Money[];
    receivables_on_hold: number;
    overdue: {
      order_number: string;
      customer_name: string;
      amount_minor: number;
      currency: string;
      days_overdue: number;
      status: string;
    }[];
    deliveries_open: number;
    late_deliveries: { po_number: string; vendor_name: string; days_late: number }[];
  };
  agents: { calls: number; succeeded: number; failed: number };
}

export interface SearchHit {
  kind: string;
  title: string;
  subtitle: string;
  link: string;
}

export interface BriefItem {
  id: number;
  text: string;
  link: string;
  tone: "alert" | "warn" | "good" | "info";
}

export interface Brief {
  headline: string;
  summary: string;
  items: BriefItem[];
  written_by: "model" | "code";
  model: string | null;
}

export interface QuickAction {
  kind: "ask" | "open";
  icon: "approvals" | "lead" | "hiring" | "ticket" | "supplier";
  label: string;
  detail: string;
  prompt: string | null;
  link: string | null;
}

export interface Explanation {
  title: string;
  agent: string;
  model: string | null;
  ai_read: { label: string; value: string }[];
  ai_read_note: string | null;
  input_verified: boolean;
  ai_said: { label: string; value: string }[];
  calls: {
    task_id: string;
    agent: string;
    at: string;
    attempt: number;
    status: string;
    duration_ms: number | null;
    error: string | null;
  }[];
  code_decided: string[];
  people: { at: string; who: string; did: string }[];
}

export interface CallAnalysis {
  summary: string;
  sentiment: "positive" | "neutral" | "negative" | "mixed";
  sentiment_quote: string;
  concerns: string[];
  action_items: { owner: "us" | "customer"; task: string; due: string | null; quote: string }[];
}

export interface CallRecord {
  id: string;
  title: string;
  department: Department;
  lead_id: string | null;
  ticket_id: string | null;
  file_name: string;
  transcript: string;
  speakers: { speaker: string; turns: number; words: number; share_pct: number }[];
  analysis: CallAnalysis | null;
  analyzed_by_model: string | null;
  analyzed_at: string | null;
  analysis_error: string | null;
  suspicious_text: string[];
  created_at: string;
}

export interface HandoffNode {
  key: string;
  label: string;
  kind: "agent" | "rules" | "human" | "tool";
  status: StepStatus;
  attempts: number;
  duration_ms: number | null;
}

/** The newest supplier-payment run, one node per hand-off stop (null: no run yet). */
export interface Handoff {
  execution_id: string;
  status: ExecutionStatus;
  file_name: string | null;
  updated_at: string;
  nodes: HandoffNode[];
}

export interface LatestHandoff {
  run: Handoff | null;
}

/** Won this quarter against the quarterly sales target (a company setting). */
export interface QuarterTarget {
  quarter: string;
  target_minor: number;
  won_minor: number;
  currency: string;
  /** Who set the target in the app; null while the deployment default applies. */
  set_by: string | null;
  set_at: string | null;
}

export interface SalesSummary {
  target: QuarterTarget;
  currency: string;
  stages: { stage: LeadStatus; count: number; value_minor: number }[];
  weeks: {
    week_start: string;
    new_leads: number;
    new_value_minor: number;
    won: number;
    won_minor: number;
  }[];
}

/** A customer's order, as Support sees it. */
export interface Order {
  id: string;
  order_number: string;
  amount_minor: number;
  currency: string;
  status: "placed" | "shipped" | "delivered" | "cancelled" | "refunded";
  ordered_at: string;
}
