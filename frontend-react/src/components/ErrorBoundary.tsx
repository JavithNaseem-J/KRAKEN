import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  incidentId: string;
}

function generateIncidentId(): string {
  return Math.random().toString(36).substring(2, 10).toUpperCase();
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, incidentId: '' };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true, incidentId: generateIncidentId() };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('[KRAKEN ErrorBoundary]', error, info);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="flex h-screen w-full items-center justify-center bg-black/90">
          <div className="max-w-md rounded-2xl border border-red-500/30 bg-black/70 p-8 text-center shadow-2xl backdrop-blur-xl">
            <div className="mb-4 flex justify-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-red-500/20 text-red-400 text-2xl">⚠</span>
            </div>
            <h2 className="mb-2 text-lg font-bold text-white">Unexpected Error</h2>
            <p className="text-sm text-neutral-400 leading-relaxed">
              KRAKEN encountered an unexpected issue. Our team has been notified.
            </p>
            <p className="mt-3 font-mono text-xs text-neutral-500">
              Incident ID: #{this.state.incidentId}
            </p>
            <button
              onClick={() => this.setState({ hasError: false, incidentId: '' })}
              className="mt-6 rounded-lg bg-purple-600 px-5 py-2 text-sm font-medium text-white hover:bg-purple-500 transition-colors"
            >
              Try Again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
