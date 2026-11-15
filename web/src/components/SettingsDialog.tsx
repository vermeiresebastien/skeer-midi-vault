import { useEffect, useState } from 'react';
import type { Bootstrap } from '../types';
import {
  ACCENTS,
  type Appearance,
  type KnobFinish,
  type MeterColor,
  type Skin,
  type TileFinish,
  useAppearance,
} from '../appearance';
import {
  api,
  backupUrl,
} from '../api';
import { Button, InlineNotice, Modal, RangeField, Segmented, Spinner, Toggle } from './Common';
import { CheckIcon, ExportIcon, InfoIcon, WarningIcon } from './Icons';

type SettingsTab = 'appearance' | 'scanning' | 'data' | 'about';

export function SettingsDialog({
  open,
  onClose,
  bootstrap,
  onRefresh,
  onRebuild,
  onNotify,
}: {
  open: boolean;
  onClose: () => void;
  bootstrap: Bootstrap | null;
  onRefresh: () => Promise<void> | void;
  onRebuild: () => Promise<void>;
  onNotify: (message: string, tone?: 'info' | 'success' | 'error') => void;
}) {
  const { appearance, setAppearance, reset } = useAppearance();
  const [tab, setTab] = useState<SettingsTab>('appearance');
  const [scanIntensity, setScanIntensity] = useState('balanced');
  const [scanMode, setScanMode] = useState('incremental');
  const [parseWorkers, setParseWorkers] = useState(2);
  const [verifyUnchanged, setVerifyUnchanged] = useState(true);
  const [saving, setSaving] = useState(false);
  const [rebuildArmed, setRebuildArmed] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);

  useEffect(() => {
    if (!open || !bootstrap) return;
    setScanIntensity(bootstrap.settings.scan_intensity || 'balanced');
    setScanMode(bootstrap.settings.scan_mode || 'incremental');
    setParseWorkers(Number(bootstrap.settings.parse_workers || 2));
    setVerifyUnchanged(bootstrap.settings.verify_unchanged !== '0');
    setRebuildArmed(false);
  }, [open, bootstrap]);

  const updateAppearance = (patch: Partial<Appearance>) => {
    setAppearance((current) => ({ ...current, ...patch }));
  };

  const saveScanning = async () => {
    setSaving(true);
    try {
      await api.updateSettings({
        scan_intensity: scanIntensity,
        scan_mode: scanMode,
        parse_workers: String(parseWorkers),
        verify_unchanged: verifyUnchanged ? '1' : '0',
      });
      await onRefresh();
      onNotify('Scan settings saved.', 'success');
    } catch (error) {
      onNotify(error instanceof Error ? error.message : 'Could not save scan settings.', 'error');
    } finally {
      setSaving(false);
    }
  };

  const rebuild = async () => {
    if (!rebuildArmed) {
      setRebuildArmed(true);
      return;
    }
    setRebuilding(true);
    try {
      await onRebuild();
      onNotify('Index cache rebuilt. Collections, tags, favorites and manual labels were preserved.', 'success');
      onClose();
    } catch (error) {
      onNotify(error instanceof Error ? error.message : 'Could not rebuild the index.', 'error');
      setRebuildArmed(false);
    } finally {
      setRebuilding(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Settings"
      eyebrow="SKEER MIDI VAULT"
      width="820px"
      className="settings-modal"
      footer={
        tab === 'appearance' ? (
          <>
            <Button variant="ghost" onClick={reset}>Reset appearance</Button>
            <span className="footer-spacer" />
            <Button variant="primary" onClick={onClose}>Done</Button>
          </>
        ) : tab === 'scanning' ? (
          <>
            <span className="footer-spacer" />
            <Button onClick={onClose}>Cancel</Button>
            <Button variant="primary" onClick={() => void saveScanning()} disabled={saving}>
              {saving ? 'Saving…' : 'Save scan settings'}
            </Button>
          </>
        ) : (
          <Button onClick={onClose}>Done</Button>
        )
      }
    >
      <div className="settings-layout">
        <nav className="settings-tabs" aria-label="Settings sections">
          {([
            ['appearance', 'Appearance'],
            ['scanning', 'Scanning'],
            ['data', 'Data & privacy'],
            ['about', 'About'],
          ] as const).map(([value, label]) => (
            <button
              key={value}
              type="button"
              className={tab === value ? 'is-active' : ''}
              onClick={() => setTab(value)}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="settings-content">
          {tab === 'appearance' ? (
            <div className="appearance-settings">
              <section className="settings-section">
                <div className="settings-section-copy">
                  <h3>Studio finish</h3>
                  <p>The same components, two SKEER studio treatments.</p>
                </div>
                <div className="skin-cards">
                  {(['clean', 'tactile'] as Skin[]).map((skin) => (
                    <button
                      key={skin}
                      type="button"
                      className={`skin-card skin-${skin} ${appearance.skin === skin ? 'is-active' : ''}`}
                      onClick={() => updateAppearance({
                        skin,
                        texture: skin === 'tactile' ? 62 : 18,
                        panelContrast: skin === 'tactile' ? 46 : 32,
                        borderStrength: skin === 'tactile' ? 42 : 24,
                      })}
                      aria-pressed={appearance.skin === skin}
                    >
                      <span className="skin-preview">
                        <span className="skin-preview-top" />
                        <span className="skin-preview-left" />
                        <span className="skin-preview-tile tile-a" />
                        <span className="skin-preview-tile tile-b" />
                        <span className="skin-preview-tile tile-c" />
                      </span>
                      <span className="skin-label-row">
                        <span>
                          <strong>{skin === 'clean' ? 'Studio Clean' : 'Studio Tactile'}</strong>
                          <small>{skin === 'clean' ? 'Flat paper, crisp hairlines' : 'Soft grain, raised surfaces'}</small>
                        </span>
                        {appearance.skin === skin ? <span className="skin-check"><CheckIcon size={12} /></span> : null}
                      </span>
                    </button>
                  ))}
                </div>
              </section>

              <section className="settings-section">
                <div className="settings-section-copy">
                  <h3>Colour</h3>
                  <p>Orange remains the SKEER primary. Change it only when the room calls for it.</p>
                </div>
                <div className="settings-field">
                  <span className="settings-field-label">Accent</span>
                  <div className="swatch-row">
                    {ACCENTS.map((accent) => (
                      <button
                        key={accent.value}
                        type="button"
                        className={`swatch ${appearance.accent === accent.value ? 'is-active' : ''}`}
                        style={{ background: accent.value }}
                        onClick={() => updateAppearance({ accent: accent.value })}
                        aria-label={accent.label}
                        title={accent.label}
                      >
                        {appearance.accent === accent.value ? <CheckIcon size={11} /> : null}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="settings-field">
                  <span className="settings-field-label">Meter colour</span>
                  <Segmented<MeterColor>
                    value={appearance.meterColor}
                    onChange={(meterColor) => updateAppearance({ meterColor })}
                    options={[
                      { value: 'accent', label: 'Follow accent' },
                      { value: 'orange', label: 'Orange' },
                      { value: 'green', label: 'Green' },
                      { value: 'amber', label: 'Amber' },
                    ]}
                    ariaLabel="Meter colour"
                  />
                </div>
              </section>

              <section className="settings-section">
                <div className="settings-section-copy">
                  <h3>Surfaces</h3>
                  <p>Finish and contrast apply to compliant tiles, lists and controls.</p>
                </div>
                <div className="settings-field">
                  <span className="settings-field-label">Tile finish</span>
                  <Segmented<TileFinish>
                    value={appearance.tileFinish}
                    onChange={(tileFinish) => updateAppearance({ tileFinish })}
                    options={[
                      { value: 'smooth', label: 'Smooth' },
                      { value: 'plastic', label: 'Plastic' },
                      { value: 'rubber', label: 'Rubber' },
                    ]}
                    ariaLabel="Tile finish"
                  />
                </div>
                <div className="settings-field">
                  <span className="settings-field-label">Tempo knob finish</span>
                  <Segmented<KnobFinish>
                    value={appearance.knobFinish}
                    onChange={(knobFinish) => updateAppearance({ knobFinish })}
                    options={[
                      { value: 'flat', label: 'Flat' },
                      { value: 'matte', label: 'Matte' },
                      { value: 'metal', label: 'Metal' },
                    ]}
                    ariaLabel="Knob finish"
                  />
                </div>
                <RangeField
                  label="Texture strength"
                  value={appearance.texture}
                  min={0}
                  max={100}
                  suffix="%"
                  onChange={(texture) => updateAppearance({ texture })}
                />
                <RangeField
                  label="Panel contrast"
                  value={appearance.panelContrast}
                  min={0}
                  max={100}
                  suffix="%"
                  onChange={(panelContrast) => updateAppearance({ panelContrast })}
                />
                <RangeField
                  label="Border strength"
                  value={appearance.borderStrength}
                  min={0}
                  max={100}
                  suffix="%"
                  onChange={(borderStrength) => updateAppearance({ borderStrength })}
                />
              </section>

              <section className="settings-section">
                <div className="settings-section-copy">
                  <h3>Comfort</h3>
                  <p>Scale the interface to your display. Motion reduction is respected everywhere.</p>
                </div>
                <RangeField
                  label="Interface scale"
                  value={appearance.interfaceScale}
                  min={80}
                  max={125}
                  step={5}
                  suffix="%"
                  onChange={(interfaceScale) => updateAppearance({ interfaceScale })}
                />
                <Toggle
                  label="Reduce motion"
                  description="Removes non-essential transitions and keeps the playhead visible."
                  checked={appearance.reduceMotion}
                  onChange={(reduceMotion) => updateAppearance({ reduceMotion })}
                />
              </section>
            </div>
          ) : null}

          {tab === 'scanning' ? (
            <div className="scanning-settings">
              <section className="settings-section">
                <div className="settings-section-copy">
                  <h3>Default scan behaviour</h3>
                  <p>Used when you open Scan computer. You can override it per scan.</p>
                </div>
                <div className="settings-field">
                  <span className="settings-field-label">Default scan mode</span>
                  <Segmented
                    value={scanMode}
                    onChange={setScanMode}
                    options={[
                      { value: 'incremental', label: 'Incremental' },
                      { value: 'full', label: 'Full reparse' },
                    ]}
                    ariaLabel="Default scan mode"
                  />
                </div>
                <div className="settings-field">
                  <span className="settings-field-label">Background intensity</span>
                  <Segmented
                    value={scanIntensity}
                    onChange={setScanIntensity}
                    options={[
                      { value: 'eco', label: 'Eco' },
                      { value: 'balanced', label: 'Balanced' },
                      { value: 'turbo', label: 'Turbo' },
                    ]}
                    ariaLabel="Default scan intensity"
                  />
                </div>
                <div className="settings-field">
                  <span className="settings-field-label">Parse workers</span>
                  <input
                    className="input worker-input"
                    type="number"
                    min={1}
                    max={8}
                    value={parseWorkers}
                    onChange={(event) => setParseWorkers(Math.max(1, Math.min(8, Number(event.target.value) || 1)))}
                  />
                  <p className="setting-hint">
                    Parsing runs off the interface thread. Eco/Balanced/Turbo choose a default;
                    this value caps the worker pool.
                  </p>
                </div>
                <Toggle
                  label="Re-read files an incremental scan would skip"
                  description="Compares the stored content hash before trusting an unchanged timestamp, so an editor that rewrote a file in place cannot keep a stale analysis. Turn off only for crates too large to re-hash on every pass."
                  checked={verifyUnchanged}
                  onChange={setVerifyUnchanged}
                />
              </section>
              <section className="settings-section">
                <div className="settings-section-copy">
                  <h3>Scanning rules</h3>
                  <p>These are fixed safeguards in this version.</p>
                </div>
                <ul className="settings-check-list">
                  <li><CheckIcon size={13} /> Read-only: source MIDI files are never modified.</li>
                  <li><CheckIcon size={13} /> Symbolic links, junctions and loops are not followed.</li>
                  <li><CheckIcon size={13} /> Cloud-only placeholders are skipped, not downloaded.</li>
                  <li><CheckIcon size={13} /> Archives are not unpacked automatically.</li>
                  <li><CheckIcon size={13} /> Protected system locations and unreadable files are reported.</li>
                  <li><CheckIcon size={13} /> Unavailable drives stay listed with their indexed entries.</li>
                </ul>
                <InlineNotice tone="info">
                  Excluded folders and included drives are managed in the Scan computer dialog.
                </InlineNotice>
              </section>
            </div>
          ) : null}

          {tab === 'data' ? (
            <div className="data-settings">
              <section className="settings-section">
                <div className="settings-section-copy">
                  <h3>Local database</h3>
                  <p>Everything stays in a single SQLite file on this computer.</p>
                </div>
                <div className="database-facts">
                  <div><span>Database</span><code className="mono">{bootstrap?.db.path || '—'}</code></div>
                  <div><span>Size</span><strong className="mono">{formatBytesStatic(bootstrap?.db.size_bytes)}</strong></div>
                  <div><span>Search index</span><strong>{bootstrap?.db.fts_enabled ? 'FTS5 enabled' : 'Fallback search'}</strong></div>
                  <div><span>Schema</span><strong className="mono">v{bootstrap?.versions.schema ?? '—'}</strong></div>
                  <div><span>Fingerprint</span><strong className="mono">v{bootstrap?.versions.fingerprint ?? '—'}</strong></div>
                  <div>
                    <span>Similarity coverage</span>
                    <strong className="mono">
                      {(() => {
                        const coverage = bootstrap?.db.fingerprint_coverage;
                        if (!coverage || !coverage.indexed) return '—';
                        return `${coverage.current} of ${coverage.indexed} file(s)`;
                      })()}
                    </strong>
                  </div>
                </div>
                {(bootstrap?.db.fingerprint_coverage?.legacy ?? 0) > 0 ? (
                  <InlineNotice tone="warning">
                    {bootstrap?.db.fingerprint_coverage?.legacy} file(s) were fingerprinted by an
                    older build. Similar-music grouping will not compare them against current
                    files, so it reports fewer groups until the next scan updates them. Exact
                    duplicates and everything else are unaffected.
                  </InlineNotice>
                ) : null}
                {bootstrap?.db.last_migration ? (
                  <p className="setting-hint">
                    Schema upgraded from v{bootstrap.db.last_migration.from} to
                    v{bootstrap.db.last_migration.to}. The previous index was copied to{' '}
                    <code className="mono">{bootstrap.db.last_migration.backup}</code> first —
                    quit the app and replace the database file to restore it.
                  </p>
                ) : null}
                <div className="settings-actions-row">
                  <a className="btn btn-secondary btn-md" href={backupUrl} download>
                    <span className="btn-icon"><ExportIcon size={14} /></span>
                    <span>Download database backup</span>
                  </a>
                </div>
                <p className="setting-hint">
                  A backup is an online SQLite snapshot. The app can stay open while it is written.
                </p>
              </section>

              <section className="settings-section">
                <div className="settings-section-copy">
                  <h3>Rebuild the index</h3>
                  <p>
                    Invalidates parser and classifier caches and starts a full rescan. Source
                    files are untouched. Favorites, tags, notes, collections and manual
                    classifications are preserved.
                  </p>
                </div>
                <div className="rebuild-row">
                  <Button
                    variant={rebuildArmed ? 'danger' : 'secondary'}
                    onClick={() => void rebuild()}
                    disabled={rebuilding}
                  >
                    {rebuilding ? <Spinner size={14} /> : null}
                    {rebuildArmed ? 'Confirm rebuild' : 'Rebuild index'}
                  </Button>
                  {rebuildArmed ? (
                    <button type="button" className="text-action" onClick={() => setRebuildArmed(false)}>
                      Cancel
                    </button>
                  ) : null}
                </div>
                {rebuildArmed ? (
                  <InlineNotice tone="warning">
                    Rebuilding re-parses every indexed file in the background. It does not delete
                    or modify any MIDI file.
                  </InlineNotice>
                ) : null}
              </section>

              <section className="settings-section">
                <div className="settings-section-copy">
                  <h3>Maintenance</h3>
                </div>
                <div className="settings-actions-row">
                  <Button
                    onClick={async () => {
                      try {
                        await api.clearScanIssues();
                        onNotify('Scan issue list cleared.', 'success');
                      } catch (error) {
                        onNotify(error instanceof Error ? error.message : 'Could not clear issues.', 'error');
                      }
                    }}
                  >
                    Clear scan issue history
                  </Button>
                </div>
              </section>

              {bootstrap?.desktop?.can_quit ? (
                <section className="settings-section">
                  <div className="settings-section-copy">
                    <h3>Application session</h3>
                    <p>
                      The installed application runs as a small local background service with a
                      tray icon. Quitting closes the service; your index and manual labels stay on
                      this computer.
                    </p>
                  </div>
                  <div className="settings-actions-row">
                    <Button
                      variant="danger"
                      onClick={async () => {
                        try {
                          await api.quitApp();
                          onNotify('SKEER MIDI VAULT is closing. You can close this browser tab.', 'info');
                        } catch (error) {
                          onNotify(error instanceof Error ? error.message : 'Could not close the app.', 'error');
                        }
                      }}
                    >
                      Quit SKEER MIDI VAULT
                    </Button>
                  </div>
                </section>
              ) : null}

              <InlineNotice tone="info">
                No uploads. No cloud processing. No telemetry. MIDI files, filenames and paths are
                never sent anywhere by this application.
              </InlineNotice>
            </div>
          ) : null}

          {tab === 'about' ? (
            <div className="about-settings">
              <img src="/brand/skeer-wordmark.png" alt="SKEER" className="about-wordmark" />
              <h3>MIDI VAULT <span>{bootstrap?.app.version || '—'}</span></h3>
              <p className="about-lede">
                A private local MIDI library with transparent musical analysis,
                editable classifications, piano-roll audition and DAW handoff.
              </p>
              <div className="about-grid">
                <div><span>Parser</span><strong className="mono">v{bootstrap?.versions.parser ?? '—'}</strong></div>
                <div><span>Classifier</span><strong className="mono">v{bootstrap?.versions.classifier ?? '—'}</strong></div>
                <div><span>Fingerprint</span><strong className="mono">v{bootstrap?.versions.fingerprint ?? '—'}</strong></div>
                <div><span>Method</span><strong>{bootstrap?.versions.classifier_method || 'SKEER rules'}</strong></div>
                <div><span>Ruleset</span><strong className="mono">{bootstrap?.versions.ruleset || '—'}</strong></div>
                <div><span>Supported</span><strong className="mono">{(bootstrap?.supported_extensions || []).join(' ')}</strong></div>
                <div><span>Formats</span><strong>SMF 0, 1, 2</strong></div>
              </div>
              <div className="about-notes">
                <div><InfoIcon size={14} /> Source files are read-only and never renamed or removed.</div>
                <div><InfoIcon size={14} /> Genre is only a low-confidence hint, never a guaranteed fact.</div>
                <div><InfoIcon size={14} /> Audition sounds are preview instruments and may differ from the original devices.</div>
                <div><WarningIcon size={14} /> Format 2 sequences are indexed independently, never combined.</div>
              </div>
              <p className="about-privacy">SKEER MIDI VAULT · local-only application engine.</p>
            </div>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}

function formatBytesStatic(bytes: number | undefined | null): string {
  if (bytes == null) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}
