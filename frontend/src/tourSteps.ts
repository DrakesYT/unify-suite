import { createContext, useContext } from "react";
import { DEMO_DOMAIN } from "./session";

/** One stop of the guided tour: who you are, which page, what to look at. */
export interface TourStep {
  as: string; // demo account handle, e.g. "finance.clerk"
  path: string;
  target: string; // CSS selector of the element to spotlight
  title: string;
  body: string;
}

export const TOUR_STEPS: TourStep[] = [
  {
    as: "ceo",
    path: "/dashboard",
    target: '[data-tour="insights"]',
    title: "Five departments, one screen",
    body: 'You are Zara, the CEO. Every number on this dashboard is live from the database. The "Needs a look" line is written by code from those numbers, not by the AI, so it cannot invent anything.',
  },
  {
    as: "finance.clerk",
    path: "/payments",
    target: '[data-tour="upload-invoice"]',
    title: "An agent reads the invoice",
    body: "Now you are Faisal, a finance clerk. Upload a supplier invoice PDF here. The Invoice Processor agent reads it; plain code then matches it to the purchase order and checks for duplicates.",
  },
  {
    as: "finance.manager",
    path: "/approvals",
    target: '[data-tour="approvals"] > :first-child',
    title: "Nothing is paid without a human",
    body: "Now you are Maryam, the finance manager. Payments, purchase orders and emails stop here until a manager approves or rejects them; if you uploaded an invoice in step 2, it is waiting at the top. A price mismatch or a prompt-injection attempt in the document is shown before you decide.",
  },
  {
    as: "ceo",
    path: "/dashboard",
    target: '[data-tour="aura"]',
    title: "Ask Aura in plain words",
    body: "Back as the CEO. Try “Is the Karachi Logistics lead worth chasing?”. Aura hands the request to the right department agent, and can never do more than your role allows.",
  },
  {
    as: "ceo",
    path: "/activity",
    target: '[data-tour="command-center"]',
    title: "Every agent call is on record",
    body: "The Command Center (the table below) logs every agent and tool call: what went in, what came out, how long it took and whether it failed. A failed workflow step can be retried from here.",
  },
];

export const demoEmail = (handle: string) => `${handle}${DEMO_DOMAIN}`;

export interface TourState {
  index: number | null; // null = tour not running
  busy: boolean;
  error: string | null;
  start: () => void;
  goTo: (index: number) => void;
  end: () => void;
}

export const TourContext = createContext<TourState | null>(null);

export function useTour(): TourState {
  const ctx = useContext(TourContext);
  if (!ctx) throw new Error("useTour must be used inside TourProvider");
  return ctx;
}
