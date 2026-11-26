import { useQueryClient } from "@tanstack/react-query";
import { Check, LogOut } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { OrbitLogo, PLATFORM_BRAND, Spinner, type Brand } from "../components/brand/Brand";
import { fetchMe, logout as apiLogout, restoreSession, type User } from "./api";

interface SignOutOptions { brand?: Brand; to?: string }
interface Ctx { user: User | null; loading: boolean; setUser: (u: User | null) => void; signOut: (o?: SignOutOptions) => Promise<void>; can: (...perms: string[]) => boolean }
const AuthCtx = createContext<Ctx>({ user: null, loading: true, setUser: () => {}, signOut: async () => {}, can: () => false });
export const useAuth = () => useContext(AuthCtx);

const STEPS = ["Ending your session on the server", "Clearing your data from this screen", "Taking you to the sign-in page"];
const pause = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Full-screen sign-out progress. It stays until the server call, the cache clear and the redirect have all happened. */
function SignOutScreen({ brand, step, failed }: { brand: Brand; step: number; failed: boolean }) {
  return (
    <div role="alertdialog" aria-modal="true" aria-label="Signing out" className="animate-fade fixed inset-0 z-[120] grid place-items-center p-6" style={{ background: "var(--color-canvas)", "--brand": brand.color, "--brand-2": brand.color2 } as CSSProperties}>
      <div className="card animate-pop w-full max-w-sm p-8 text-center">
        <div className="flex justify-center"><OrbitLogo size={104} brand={brand} /></div>
        <p className="mt-5 flex items-center justify-center gap-2 text-lg font-bold"><LogOut size={18} aria-hidden />Signing out</p>
        <p className="mt-1 text-sm text-muted">{brand.name}</p>
        <ol aria-live="polite" className="mt-6 space-y-2.5 text-left text-sm">
          {STEPS.map((s, i) => (
            <li key={s} className={`flex items-center gap-3 transition-opacity ${i > step ? "opacity-40" : ""}`}>
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-line">
                {i < step ? <Check size={14} className="text-success" aria-hidden /> : i === step ? <Spinner size={12} /> : <span className="h-1.5 w-1.5 rounded-full bg-slate-300" />}
              </span>{s}
            </li>))}
        </ol>
        <div className="mt-6 h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${((step + 1) / STEPS.length) * 100}%`, background: "var(--brand)" }} /></div>
        {failed && <p className="mt-3 text-xs text-muted">The server could not be reached. You are still signed out on this device.</p>}
      </div>
    </div>
  );
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [leaving, setLeaving] = useState<{ brand: Brand; step: number; failed: boolean } | null>(null);
  const busy = useRef(false);
  const navigate = useNavigate();
  const queries = useQueryClient();
  useEffect(() => { restoreSession().then((ok) => (ok ? fetchMe().then(setUser) : undefined)).catch(() => setUser(null)).finally(() => setLoading(false)); }, []);

  const signOut = useCallback(async ({ brand = PLATFORM_BRAND, to }: SignOutOptions = {}) => {
    if (busy.current) return;
    busy.current = true;
    const target = to ?? (user?.tenant_slug ? `/${user.tenant_slug}/login` : "/platform/login");
    let failed = false;
    setLeaving({ brand, step: 0, failed });
    await Promise.all([apiLogout().catch(() => { failed = true; }), pause(650)]);
    setLeaving({ brand, step: 1, failed });
    await queries.cancelQueries();
    await pause(500);
    setLeaving({ brand, step: 2, failed });
    navigate(target, { replace: true });
    setUser(null);
    queries.clear();
    await pause(700);
    setLeaving(null);
    busy.current = false;
  }, [navigate, queries, user]);

  const can = useCallback((...perms: string[]) => !!user && perms.some((p) => user.permissions.includes(p)), [user]);
  return (
    <AuthCtx.Provider value={{ user, loading, setUser, signOut, can }}>
      {children}
      {leaving && <SignOutScreen {...leaving} />}
    </AuthCtx.Provider>
  );
}
