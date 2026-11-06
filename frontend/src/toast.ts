export type ToastTone = "success" | "error" | "info";

export interface ToastMessage {
  message: string;
  tone: ToastTone;
}

export const TOAST_EVENT = "unify:toast";

/** Show a short message in the corner: `toast("Lead rated hot")`, `toast("…", "error")`.
 * A plain function (a window event the Toaster listens for), so any code can call it. */
export function toast(message: string, tone: ToastTone = "success"): void {
  window.dispatchEvent(new CustomEvent<ToastMessage>(TOAST_EVENT, { detail: { message, tone } }));
}
