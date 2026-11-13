import { Component, type ErrorInfo, type ReactNode } from 'react';

interface ErrorBoundaryState {
  error: Error | null;
  errorInfo: ErrorInfo | null;
  copied: boolean;
}

interface ErrorBoundaryProps {
  children: ReactNode;
}

/**
 * Last-resort recovery surface. A bug in a canvas render or a third-party
 * browser API must not leave the whole application as a blank white page.
 */
export class AppErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    error: null,
    errorInfo: null,
    copied: false,
  };

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    this.setState({ error, errorInfo });
    console.error('SKEER MIDI VAULT interface error', error, errorInfo);
    try {
      window.localStorage.setItem(
        'skeer.midiVault.lastInterfaceError',
        JSON.stringify({
          at: new Date().toISOString(),
          message: error.message,
          stack: error.stack,
          componentStack: errorInfo.componentStack,
        }),
      );
    } catch {
      // Diagnostic storage is optional.
    }
  }

  private diagnostics = (): string => {
    const { error, errorInfo } = this.state;
    return [
      `SKEER MIDI VAULT ${new Date().toISOString()}`,
      `URL: ${window.location.href}`,
      `User agent: ${navigator.userAgent}`,
      '',
      error ? `${error.name}: ${error.message}` : 'Unknown interface error',
      error?.stack || '',
      errorInfo?.componentStack || '',
    ].join('\n');
  };

  private copyDiagnostics = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(this.diagnostics());
      this.setState({ copied: true });
    } catch {
      this.setState({ copied: false });
    }
  };

  private reset = (): void => {
    this.setState({ error: null, errorInfo: null, copied: false });
  };

  render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div className="fatal-screen" role="alert">
        <div className="fatal-card">
          <div className="fatal-brand">
            <img src="/brand/skeer-wordmark.png" alt="SKEER" />
            <span>MIDI VAULT</span>
          </div>
          <p className="fatal-kicker">Interface recovery</p>
          <h1>The interface hit an unexpected error.</h1>
          <p className="fatal-copy">
            Your source MIDI files, index and manual labels are safe. Nothing was
            deleted or rewritten. Reload the interface to continue; if the same
            action crashes it again, copy the diagnostics below.
          </p>
          <pre className="fatal-details">{this.diagnostics()}</pre>
          <div className="fatal-actions">
            <button type="button" className="fatal-primary" onClick={() => window.location.reload()}>
              Reload interface
            </button>
            <button type="button" onClick={() => void this.copyDiagnostics()}>
              {this.state.copied ? 'Diagnostics copied' : 'Copy diagnostics'}
            </button>
            <button type="button" onClick={this.reset}>
              Try again without reload
            </button>
          </div>
          <p className="fatal-footnote">
            SKEER MIDI VAULT · local-only · source files are never modified
          </p>
        </div>
      </div>
    );
  }
}
