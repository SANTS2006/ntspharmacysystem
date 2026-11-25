/** When the app is opened on https://<slug>.<base-domain>, map the clean URL onto the pharmacy's routes (/pharmacy/<slug>/...). */
const GLOBAL_PATHS = ["/reset-password", "/accept-invitation", "/change-password", "/dashboard", "/platform"];

export function hostSlug(host = window.location.hostname, base = document.querySelector<HTMLMetaElement>('meta[name="platform-base-domain"]')?.content ?? ""): string | null {
  if (!base || base.startsWith("__")) return null;
  const h = host.toLowerCase();
  if (!h.endsWith("." + base.toLowerCase())) return null;
  const sub = h.slice(0, -(base.length + 1));
  return /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(sub) && sub !== "www" ? sub : null;
}

export function rewriteForSubdomain(): void {
  const slug = hostSlug();
  if (!slug) return;
  const { pathname, search, hash } = window.location;
  const prefix = `/pharmacy/${slug}`;
  if (pathname === prefix || pathname.startsWith(prefix + "/") || GLOBAL_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"))) return;
  window.history.replaceState(null, "", prefix + (pathname === "/" ? "" : pathname) + search + hash);
}
