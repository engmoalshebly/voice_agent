import { Component, type ReactNode } from 'react';

/** A rendering bug must end the call cleanly, never leave a blank page. */
export class CallErrorBoundary extends Component<{ onCrash: () => void; children: ReactNode }, { crashed: boolean }> {
  state = { crashed: false };

  static getDerivedStateFromError() {
    return { crashed: true };
  }

  componentDidCatch(error: unknown) {
    console.error('call screen crashed', error);
    this.props.onCrash();
  }

  render() {
    return this.state.crashed ? null : this.props.children;
  }
}
