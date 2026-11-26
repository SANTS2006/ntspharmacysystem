// Thin API client. The tenant is only a *hint* (X-Tenant-Slug); the backend binds authenticated users to their own tenant.
export interface User {
  id: number; email: string; full_name: string; role: string | null; permissions: string[];
  tenant_slug: string | null; branch: number | null; is_platform_admin: boolean; must_change_password: boolean; email_verified: boolean;
  phone?: string; avatar?: string | null; role_name?: string | null; branch_name?: string | null; pharmacy_name?: string | null; has_password?: boolean; date_joined?: string;
}
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) { super(message); }
}
let access: string | null = null; // memory only (not persisted) to limit XSS exposure
export const getAccessToken = () => access;
const REFRESH_KEY = "refresh_token";
export const setTokens = (t: { access: string; refresh: string } | null) => {
  access = t?.access ?? null;
  try { t ? sessionStorage.setItem(REFRESH_KEY, t.refresh) : sessionStorage.removeItem(REFRESH_KEY); } catch { /* storage blocked */ }
};
const getRefresh = () => { try { return sessionStorage.getItem(REFRESH_KEY); } catch { return null; } };

export async function api<T>(path: string, opts: { method?: string; body?: unknown; tenant?: string | null; retry?: boolean; headers?: Record<string, string> } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const isForm = opts.body instanceof FormData; // multipart (logo upload): let the browser set the boundary
  if (!isForm) headers["Content-Type"] = "application/json";
  if (access) headers.Authorization = `Bearer ${access}`;
  if (opts.tenant) headers["X-Tenant-Slug"] = opts.tenant;
  Object.assign(headers, opts.headers);
  const res = await fetch(`/api/v1${path}`, { method: opts.method ?? "GET", headers, body: opts.body ? (isForm ? (opts.body as FormData) : JSON.stringify(opts.body)) : undefined });
  if (res.status === 401 && access && opts.retry !== false && (await refresh(opts.tenant))) return api<T>(path, { ...opts, retry: false });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, data?.error?.code ?? "error", data?.error?.message ?? "Request failed.", data?.error?.details);
  return data as T;
}
async function refresh(tenant?: string | null): Promise<boolean> {
  const token = getRefresh();
  if (!token) return false;
  const res = await fetch("/api/v1/auth/refresh/", { method: "POST", headers: { "Content-Type": "application/json", ...(tenant ? { "X-Tenant-Slug": tenant } : {}) }, body: JSON.stringify({ refresh: token }) });
  if (!res.ok) { setTokens(null); return false; }
  setTokens((await res.json()).tokens); return true;
}
/** After a page reload the access token (memory only) is gone: renew it from this tab's refresh token. One shared request, because
 *  refresh tokens are single use. */
let restoring: Promise<boolean> | null = null;
export const restoreSession = () => (access ? Promise.resolve(true) : (restoring ??= refresh().catch(() => false).finally(() => { restoring = null; })));

export interface LoginResult { tokens: { access: string; refresh: string }; user: User }
export async function login(email: string, password: string, tenant?: string | null) {
  const r = await api<LoginResult>("/auth/login/", { method: "POST", body: { email, password }, tenant, retry: false });
  setTokens(r.tokens); return r.user;
}
export async function changePassword(old_password: string, new_password: string, tenant?: string | null) {
  const r = await api<{ tokens: { access: string; refresh: string } }>("/auth/change-password/", { method: "POST", body: { old_password, new_password }, tenant });
  setTokens(r.tokens);
}
export const fetchMe = (tenant?: string | null) => api<User>("/auth/me/", { tenant });
export async function logout() {
  const refresh = getRefresh();
  try { await api("/auth/logout/", { method: "POST", body: { refresh }, retry: false }); } finally { setTokens(null); }
}

/** Authenticated download that saves the file (exports are never served from a public URL). */
export async function downloadFile(path: string, filename: string) {
  const res = await fetch(`/api/v1${path}`, { headers: access ? { Authorization: `Bearer ${access}` } : {} });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new ApiError(res.status, d?.error?.code ?? "download_failed", d?.error?.message ?? "The file could not be created.");
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** Authenticated file download (protected documents are never served from a public URL). */
export async function openProtectedFile(path: string) {
  const res = await fetch(`/api/v1${path}`, { headers: access ? { Authorization: `Bearer ${access}` } : {} });
  if (!res.ok) throw new ApiError(res.status, "download_failed", "The document could not be opened.");
  const url = URL.createObjectURL(await res.blob());
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
