import { label, money } from "./format";
import type { Approval } from "./types";

/** One line saying what an approval is about (bell menu, dashboard panel). */
export function approvalHeadline(a: Approval): { title: string; detail: string } {
  const p = a.payload;
  switch (a.action) {
    case "pay_invoice":
      return {
        title: `Pay ${money(p.amount_minor, p.currency)} to ${p.vendor_name ?? "a supplier"}`,
        detail: `Invoice ${p.invoice_number ?? "?"}${p.match_status ? ` · ${label(p.match_status)}` : ""}`,
      };
    case "approve_po":
      return {
        title: `Purchase order ${p.po_number ?? ""} · ${money(p.amount_minor, p.currency)}`,
        detail: [p.vendor_name, p.item && `${p.quantity} × ${p.item}`].filter(Boolean).join(" · "),
      };
    case "approve_request":
      return {
        title: `Purchase request: ${p.quantity} × ${p.item ?? "item"}`,
        detail: `Budget ${money(p.budget_minor ?? undefined, p.currency)}`,
      };
    case "send_email":
      return {
        title: p.subject ?? "Send an email",
        detail: `Email to ${p.company ?? p.to ?? "?"}`,
      };
    default:
      return {
        title: p.title ?? label(a.action),
        detail: [label(a.action), p.customer_name].filter(Boolean).join(" · "),
      };
  }
}
