import { Component, type ReactNode } from "react";

/** Keeps the navigation usable if one page throws while rendering. */
export class PageBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div role="alert" className="card mx-auto max-w-md p-8 text-center">
        <h1 className="page-title">This page could not be displayed</h1>
        <p className="page-subtitle">Something went wrong while showing it. Your data has not been changed.</p>
        <button className="btn btn-primary mt-5" onClick={() => this.setState({ failed: false })}>Try again</button>
      </div>
    );
  }
}
