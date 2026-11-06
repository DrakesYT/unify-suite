/** Thin fetch wrapper. All calls go to same-origin `/api/...`; errors use the backend envelope.
 *
 *  The session token lives only in an HttpOnly cookie the browser attaches by itself: no script on
 *  the page (ours or an injected one) can read it. Every call carries the CSRF header the API
 *  requires on data-changing requests. */

const CSRF_HEADER = { "X-Requested-With": "unify" };

/** Not a secret: only remembers that this browser signed in, so a refresh knows to show the
 *  "Checking your sign-in" screen while the server confirms the cookie. */
const SIGNED_IN_HINT = "unify.signedIn";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export function hasSignedInHint(): boolean {
  try {
    return localStorage.getItem(SIGNED_IN_HINT) === "1";
  } catch {
    return false;
  }
}

export function setSignedInHint(signedIn: boolean): void {
  try {
    if (signedIn) localStorage.setItem(SIGNED_IN_HINT, "1");
    else localStorage.removeItem(SIGNED_IN_HINT);
    localStorage.removeItem("unify.token"); // left over from before cookie sessions
  } catch {
    // Private mode / blocked storage: the hint only changes which loading screen shows.
  }
}

/** Fired when the server says the session is no longer valid. */
export const SIGNED_OUT_EVENT = "unify:signed-out";

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isForm = init.body instanceof FormData;
  const res = await fetch(`/api${path}`, {
    ...init,
    credentials: "same-origin",
    headers: {
      ...(isForm ? {} : { "Content-Type": "application/json" }),
      ...CSRF_HEADER,
      ...init.headers,
    },
  });
  const body = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && hasSignedInHint()) {
      setSignedInHint(false);
      window.dispatchEvent(new Event(SIGNED_OUT_EVENT));
    }
    const err = body?.error;
    throw new ApiError(res.status, err?.code ?? "http_error", err?.message ?? res.statusText);
  }
  return body as T;
}
