/** Thin fetch wrapper. All calls go to same-origin `/api/...`; errors use the backend envelope. */

const TOKEN_KEY = "unify.token";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Private mode / blocked storage: the session simply lasts until reload.
  }
}

/** Fired when the server says the session is no longer valid. */
export const SIGNED_OUT_EVENT = "unify:signed-out";

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const isForm = init.body instanceof FormData;
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: {
      ...(isForm ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && token) {
      setToken(null);
      window.dispatchEvent(new Event(SIGNED_OUT_EVENT));
    }
    const err = body?.error;
    throw new ApiError(res.status, err?.code ?? "http_error", err?.message ?? res.statusText);
  }
  return body as T;
}
