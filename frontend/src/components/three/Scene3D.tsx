import { Component, lazy, Suspense, type ReactNode } from "react";

const PharmacyScene = lazy(() => import("./PharmacyScene"));

/** Decoration must never break a page: any failure to load or draw the 3D scene is swallowed. */
class Quiet extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? null : this.props.children; }
}

export function Scene3D(props: { color?: string; color2?: string; className?: string }) {
  return <Quiet><Suspense fallback={null}><PharmacyScene {...props} /></Suspense></Quiet>;
}
