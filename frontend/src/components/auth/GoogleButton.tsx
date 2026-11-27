/** "Sign in with Google" using Google Identity Services. The server verifies the returned token. */
import { useEffect, useRef, useState } from "react";

interface Gsi { accounts: { id: { initialize: (o: { client_id: string; callback: (r: { credential: string }) => void }) => void; renderButton: (el: HTMLElement, o: Record<string, unknown>) => void } } }
const SRC = "https://accounts.google.com/gsi/client";

export function GoogleButton({ clientId, onToken }: { clientId: string; onToken: (idToken: string) => void }) {
  const box = useRef<HTMLDivElement>(null); const callback = useRef(onToken); const [failed, setFailed] = useState(false);
  callback.current = onToken;
  useEffect(() => {
    const draw = () => {
      const g = (window as unknown as { google?: Gsi }).google;
      if (!g || !box.current) return;
      g.accounts.id.initialize({ client_id: clientId, callback: (r) => callback.current(r.credential) });
      g.accounts.id.renderButton(box.current, { theme: "outline", size: "large", text: "signin_with", shape: "pill", width: Math.min(box.current.offsetWidth || 320, 400) });
    };
    let script = document.querySelector<HTMLScriptElement>(`script[src="${SRC}"]`);
    if (!script) { script = document.createElement("script"); script.src = SRC; script.async = true; document.head.appendChild(script); }
    const fail = () => setFailed(true);
    script.addEventListener("load", draw); script.addEventListener("error", fail); draw();
    return () => { script.removeEventListener("load", draw); script.removeEventListener("error", fail); };
  }, [clientId]);
  return failed ? <p className="text-center text-xs text-muted">Google sign-in could not be loaded. Use your email and password.</p> : <div ref={box} className="flex min-h-11 w-full justify-center" />;
}
