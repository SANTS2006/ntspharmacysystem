/** Floating 3D pharmacy objects (capsules, tablets, a medical cross and a molecule) modelled in code with three.js.
 *  Loaded on demand; pauses when off screen or in a hidden tab, draws a single still frame for reduced-motion users,
 *  and simply renders nothing when WebGL is unavailable. */
import { useEffect, useRef } from "react";
import * as THREE from "three";

export default function PharmacyScene({ color = "#10b981", color2 = "#38bdf8", className = "" }: { color?: string; color2?: string; className?: string }) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" }); } catch { return; }
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.set(0, 0, 13);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x1b3042, 1.5));
    const key = new THREE.DirectionalLight(0xffffff, 2.2); key.position.set(4, 6, 8); scene.add(key);
    const rim = new THREE.PointLight(new THREE.Color(color2), 40, 30); rim.position.set(-6, -3, 4); scene.add(rim);

    const owned: { dispose: () => void }[] = [];
    const keep = <T extends { dispose: () => void }>(x: T) => { owned.push(x); return x; };
    const material = (c: string, rough = 0.28) => keep(new THREE.MeshPhysicalMaterial({ color: new THREE.Color(c), roughness: rough, metalness: 0.08, clearcoat: 0.85, clearcoatRoughness: 0.2 }));
    const white = material("#f8fafc"), a = material(color), b = material(color2);
    const mesh = (g: THREE.BufferGeometry, m: THREE.Material) => new THREE.Mesh(keep(g), m);

    const capsule = (top: THREE.Material, bottom: THREE.Material) => {
      const g = new THREE.Group();
      const r = 0.52, len = 0.85;
      for (const [sign, mat] of [[1, top], [-1, bottom]] as const) {
        const tube = mesh(new THREE.CylinderGeometry(r, r, len, 40, 1, true), mat); tube.position.y = (sign * len) / 2; g.add(tube);
        const cap = mesh(new THREE.SphereGeometry(r, 40, 20, 0, Math.PI * 2, 0, Math.PI / 2), mat); cap.position.y = sign * len; if (sign < 0) cap.rotation.x = Math.PI; g.add(cap);
      }
      const band = mesh(new THREE.TorusGeometry(r, 0.028, 10, 48), white); band.rotation.x = Math.PI / 2; g.add(band);
      return g;
    };
    const tablet = (m: THREE.Material) => {
      const g = new THREE.Group();
      g.add(mesh(new THREE.CylinderGeometry(0.78, 0.78, 0.3, 48), m));
      const edge = mesh(new THREE.TorusGeometry(0.78, 0.15, 16, 48), m); edge.rotation.x = Math.PI / 2; g.add(edge);
      const score = mesh(new THREE.BoxGeometry(1.45, 0.06, 0.07), white); score.position.y = 0.17; g.add(score);
      return g;
    };
    const cross = () => {
      const s = new THREE.Shape();
      const w = 0.45, h = 1.3;
      [[-w, h], [w, h], [w, w], [h, w], [h, -w], [w, -w], [w, -h], [-w, -h], [-w, -w], [-h, -w], [-h, w], [-w, w]].forEach(([x, y], i) => (i ? s.lineTo(x, y) : s.moveTo(x, y)));
      const m = mesh(new THREE.ExtrudeGeometry(s, { depth: 0.55, bevelEnabled: true, bevelSize: 0.12, bevelThickness: 0.12, bevelSegments: 5 }), a);
      m.geometry.center();
      return m;
    };
    const molecule = () => {
      const g = new THREE.Group();
      const atoms: [number, number, number, number][] = [[0, 0, 0, 0.42], [1.25, 0.65, 0.2, 0.27], [-1.15, 0.75, -0.3, 0.3], [0.2, -1.35, 0.25, 0.25], [2.2, 0.05, -0.2, 0.2]];
      const bonds: [number, number][] = [[0, 1], [0, 2], [0, 3], [1, 4]];
      atoms.forEach(([x, y, z, r], i) => { const m = mesh(new THREE.SphereGeometry(r, 28, 20), i % 2 ? white : b); m.position.set(x, y, z); g.add(m); });
      bonds.forEach(([i, j]) => {
        const from = new THREE.Vector3(...(atoms[i].slice(0, 3) as [number, number, number])), to = new THREE.Vector3(...(atoms[j].slice(0, 3) as [number, number, number]));
        const dir = to.clone().sub(from);
        const rod = mesh(new THREE.CylinderGeometry(0.07, 0.07, dir.length(), 12), white);
        rod.position.copy(from).add(dir.clone().multiplyScalar(0.5));
        rod.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.normalize());
        g.add(rod);
      });
      return g;
    };

    const world = new THREE.Group();
    scene.add(world);
    const items: { o: THREE.Object3D; y: number; speed: number; phase: number }[] = [];
    const place = (o: THREE.Object3D, x: number, y: number, z: number, scale: number, speed: number) => {
      o.position.set(x, y, z); o.scale.setScalar(scale); o.rotation.set(x * 0.4, y * 0.5, z * 0.3 + x * 0.2);
      world.add(o); items.push({ o, y, speed, phase: items.length * 1.7 });
    };
    place(cross(), 0.2, 0.2, 0, 1.15, 0.22);
    place(capsule(a, white), -3.4, 1.7, -0.5, 1.05, 0.5);
    place(capsule(b, white), 3.5, -1.5, 0.6, 0.95, -0.42);
    place(capsule(white, a), 2.7, 2.5, -2, 0.75, 0.62);
    place(tablet(white), -2.8, -2.2, 0.4, 0.95, 0.38);
    place(tablet(b), 3.9, 0.9, -1.6, 0.7, -0.55);
    place(molecule(), -0.9, 2.9, -2.4, 0.8, 0.3);
    place(molecule(), 0.9, -3.0, -1.2, 0.62, -0.34);
    const dotsGeo = keep(new THREE.BufferGeometry());
    dotsGeo.setAttribute("position", new THREE.Float32BufferAttribute(Array.from({ length: 360 }, (_, i) => (Math.sin(i * 12.9898) * 43758.5453 % 1) * (i % 3 === 2 ? 5 : 9)), 3));
    world.add(new THREE.Points(dotsGeo, keep(new THREE.PointsMaterial({ color: new THREE.Color(color2), size: 0.05, transparent: true, opacity: 0.7 }))));

    let px = 0, py = 0;
    const pointer = (e: PointerEvent) => { px = e.clientX / window.innerWidth - 0.5; py = e.clientY / window.innerHeight - 0.5; };
    window.addEventListener("pointermove", pointer, { passive: true });
    const resize = () => {
      const w = el.clientWidth || 1, h = el.clientHeight || 1;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.position.z = camera.aspect < 1 ? 13 / Math.max(camera.aspect, 0.55) : 13;
      camera.updateProjectionMatrix();
      renderer.render(scene, camera);
    };
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(resize) : null;
    ro?.observe(el);
    resize();

    let frame = 0, visible = true, start = performance.now();
    const tick = (now: number) => {
      frame = requestAnimationFrame(tick);
      if (!visible || document.hidden) return;
      const t = (now - start) / 1000;
      for (const it of items) {
        it.o.position.y = it.y + Math.sin(t * 0.9 + it.phase) * 0.22;
        it.o.rotation.y += it.speed * 0.012;
        it.o.rotation.x += it.speed * 0.004;
      }
      world.rotation.y += (px * 0.5 - world.rotation.y) * 0.04;
      world.rotation.x += (py * 0.3 - world.rotation.x) * 0.04;
      world.position.y = Math.min(window.scrollY, 900) * 0.0016; // gentle parallax while scrolling
      renderer.render(scene, camera);
    };
    const io = typeof IntersectionObserver !== "undefined" ? new IntersectionObserver(([e]) => { visible = e.isIntersecting; }) : null;
    io?.observe(el);
    if (!still) { start = performance.now(); frame = requestAnimationFrame(tick); }
    return () => {
      cancelAnimationFrame(frame);
      ro?.disconnect(); io?.disconnect();
      window.removeEventListener("pointermove", pointer);
      owned.forEach((o) => o.dispose());
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    };
  }, [color, color2]);
  return <div ref={host} aria-hidden className={`pointer-events-none [&>canvas]:!h-full [&>canvas]:!w-full ${className}`} />;
}
