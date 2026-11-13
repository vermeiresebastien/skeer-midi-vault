import { IconButton, Spinner } from './Common';
import { ScanIcon, SettingsIcon } from './Icons';
import type { ScanStatus } from '../types';

export function TopBar({
  scan,
  onOpenScan,
  onOpenSettings,
  libraryCount,
}: {
  scan: ScanStatus;
  onOpenScan: () => void;
  onOpenSettings: () => void;
  libraryCount: number;
}) {
  const scanning = scan.active || scan.state === 'cancelling';
  return (
    <header className="topbar">
      <div className="brand-lockup">
        <img
          className="skeer-wordmark"
          src="/brand/skeer-wordmark.png"
          alt="SKEER"
          draggable={false}
        />
        <span className="brand-divider" aria-hidden="true" />
        <div className="product-name">
          <span className="product-title">MIDI VAULT</span>
          <span className="product-subtitle">Local MIDI library</span>
        </div>
      </div>
      <div className="topbar-center">
        <span className="topbar-stat">
          <span className="live-dot" />
          <span>{libraryCount.toLocaleString()} files indexed</span>
        </span>
        {scan.active ? (
          <span className="topbar-scan-summary">
            {scan.state === 'paused' ? 'Scan paused' : 'Scanning'}
            <span className="mono"> · {scan.indexed.toLocaleString()} indexed</span>
          </span>
        ) : null}
      </div>
      <div className="topbar-actions">
        <span className="local-chip" title="MIDI Vault runs only on this computer. Nothing is uploaded.">
          Local only
        </span>
        <button
          type="button"
          className={`scan-button ${scanning ? 'is-scanning' : ''}`}
          onClick={onOpenScan}
        >
          {scanning ? <Spinner size={14} /> : <ScanIcon size={16} />}
          <span>{scanning ? (scan.state === 'paused' ? 'Scan paused' : 'Scanning…') : 'Scan computer'}</span>
        </button>
        <IconButton label="Settings" onClick={onOpenSettings} className="settings-button">
          <SettingsIcon size={18} />
        </IconButton>
      </div>
    </header>
  );
}
