import { useQuery } from "@tanstack/react-query";
import { HeartPulse, PackageCheck, ShieldCheck, Smartphone } from "lucide-react";
import { PLATFORM_BRAND, type Brand } from "../components/brand/Brand";
import { api, type User } from "./api";

export interface Site { name: string; slug: string; description: string; logo: string | null; primary_color: string; secondary_color: string; contact_email: string; contact_phone: string; address: string; city: string; country?: string; online_payments?: boolean }

/** A pharmacy's public identity (name, logo, colours). Shared by its website, its sign-in page and both of its portals. */
export const useSiteQuery = (slug?: string) => useQuery({ queryKey: ["site", slug], queryFn: () => api<Site>(`/public/pharmacies/${slug}/`), enabled: !!slug, retry: false, staleTime: 5 * 60_000 });

export const brandOf = (s?: Site | null): Brand => s ? { name: s.name, logo: s.logo, color: s.primary_color, color2: s.secondary_color } : PLATFORM_BRAND;

export const PHARMACY_POINTS: [typeof ShieldCheck, string][] = [[PackageCheck, "Order medicines and follow every step"], [ShieldCheck, "Prescriptions reviewed by a pharmacist"], [Smartphone, "Pay securely with mobile money"], [HeartPulse, "Book pharmacy services online"]];

/** The one place that decides where an account lands after signing in. */
export function homeFor(user: User): string {
  if (user.must_change_password) return "/change-password";
  if (user.is_platform_admin) return "/platform/dashboard";
  if (!user.tenant_slug) return "/";
  if (user.role === "customer") return user.email_verified ? `/${user.tenant_slug}/account/dashboard` : `/${user.tenant_slug}/verify`;
  return `/${user.tenant_slug}/admin/dashboard`;
}
