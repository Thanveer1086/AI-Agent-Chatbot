/**
 * Fetch wrapper for the backend API.
 *
 * Adds `Authorization: Bearer <token>` when a token is available, so the UI keeps
 * working once DEV_AUTH_BYPASS is switched off. The token comes from (first match):
 *   1. localStorage key "auth_token" (set by a login flow)
 *   2. the build-time VITE_API_TOKEN environment variable
 */
const TOKEN_KEY = 'auth_token';

export function getAuthToken(): string | null {
  try {
    const stored = window.localStorage.getItem(TOKEN_KEY);
    if (stored) return stored;
  } catch {
    // Storage can be unavailable (private mode, blocked cookies)
  }
  return import.meta.env.VITE_API_TOKEN || null;
}

export function setAuthToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore
  }
}

export function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getAuthToken();
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  return fetch(path, { ...init, headers });
}

/** Extract a readable error message from a failed API response. */
export async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === 'string') return body.detail;
    if (typeof body?.message === 'string') return body.message;
  } catch {
    // not JSON
  }
  return `Request failed (HTTP ${res.status})`;
}
