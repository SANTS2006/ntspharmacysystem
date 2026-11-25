import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { fetchMe, logout as apiLogout, type User } from "./api";

interface Ctx { user: User | null; loading: boolean; setUser: (u: User | null) => void; signOut: () => Promise<void> }
const AuthCtx = createContext<Ctx>({ user: null, loading: true, setUser: () => {}, signOut: async () => {} });
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { fetchMe().then(setUser).catch(() => setUser(null)).finally(() => setLoading(false)); }, []);
  const signOut = async () => { await apiLogout().catch(() => {}); setUser(null); };
  return <AuthCtx.Provider value={{ user, loading, setUser, signOut }}>{children}</AuthCtx.Provider>;
}
