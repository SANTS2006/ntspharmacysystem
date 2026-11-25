import { useRef } from "react";
import { useNavigate } from "react-router-dom";

/** Empty navbar space: 5 clicks within 3s open the platform login. Decorative (aria-hidden, not focusable) so it
 *  never interferes with keyboard/screen-reader navigation; /platform/login stays reachable by URL. */
export function HiddenLoginTrigger({ to = "/platform/login", clicks = 5, windowMs = 3000 }: { to?: string; clicks?: number; windowMs?: number }) {
  const navigate = useNavigate();
  const stamps = useRef<number[]>([]);
  const onClick = () => {
    const now = Date.now();
    stamps.current = [...stamps.current.filter((t) => now - t < windowMs), now];
    if (stamps.current.length >= clicks) { stamps.current = []; navigate(to); }
  };
  return <div aria-hidden="true" data-testid="hidden-login-trigger" onClick={onClick} className="h-10 min-w-12 flex-1 select-none" />;
}
