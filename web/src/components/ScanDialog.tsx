import { useEffect, useMemo, useState } from 'react';
import type { ApiSource, ScanIssue, ScanStatus } from '../types';
import { api } from '../api';
import { formatBytes, formatDurationShort, formatRelativeTime } from '../lib/format';
import { Badge, Button, InlineNotice, Modal, Segmented, Spinner } from './Common';
import {
  CheckIcon,
  FolderIcon,
  PauseIcon,
  PlayIcon,
  ScanIcon,
  StopIcon,
  WarningIcon,
} from './Icons';

interface Exclude {
  id: number;
  path: string;
  note?: string | null;
}

export function ScanDialog({
  open,
  scan,
  onClose,
  onStart,
  onPause,
  onResume,
  onCancel,
  onNotify,
  onRefreshApp,
}: {
  open: boolean;
  scan: ScanStatus;
  onClose: () => void;
  onStart: (payload: { source_ids: number[]; mode: string; intensity: string }) => Promise<void>;
  onPause: () => void;
  onResume: () => void;
  onCancel: () => void;
  onNotify: (message: string, tone?: 'info' | 'success' | 'error') => void;
  onRefreshApp: () => Promise<void> | void;
}) {
  const [sources, setSources] = useState<ApiSource[]>([]);
  const [excludes, setExcludes] = useState<Exclude[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [mode, setMode] = useState<'incremental' | 'full'>('incremental');
  const [intensity, setIntensity] = useState<'eco' | 'balanced' | 'turbo'>('balanced');
  const [newFolder, setNewFolder] = useState('');
  const [newExclude, setNewExclude] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [issues, setIssues] = useState<ScanIssue[]>([]);
  const [showIssues, setShowIssues] = useState(false);
  const [lastScan, setLastScan] = useState<ScanStatus | null>(null);
  const [showAddFolder, setShowAddFolder] = useState(false);
  const [showAddExclude, setShowAddExclude] = useState(false);
  const scanning = scan.active || scan.state === 'cancelling';
  const paused = scan.state === 'paused';

  const load = async () => {
    setLoading(true);
    try {
      const options = await api.scanOptions();
      setSources(options.sources);
      setExcludes(options.excludes);
      setSelected(new Set(options.sources.filter((source) => Boolean(source.enabled)).map((source) => source.id)));
      setMode((options.settings.scan_mode as 'incremental' | 'full') || 'incremental');
      setIntensity((options.settings.scan_intensity as 'eco' | 'balanced' | 'turbo') || 'balanced');
      setLastScan(options.last_scan || null);
    } catch (error) {
      onNotify(error instanceof Error ? error.message : 'Could not load scan options.', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!open) return;
    void load();
    setShowIssues(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open || scan.active) return;
    if (scan.state === 'completed' || scan.state === 'cancelled' || scan.state === 'error') {
      void load();
    }
    // Only refresh when a scan lifecycle ends; load is intentionally local.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, scan.active, scan.state, scan.scan_id]);

  useEffect(() => {
    if (!open) return;
    api.scanIssues(scan.scan_id)
      .then((result) => setIssues(result.issues))
      .catch(() => undefined);
  }, [open, scan.scan_id, scan.indexed, scan.failed]);

  const sourceGroups = useMemo(() => {
    const local = sources.filter((source) => source.kind !== 'network' && source.kind !== 'removable' && source.kind !== 'optical');
    const optional = sources.filter((source) => source.kind === 'network' || source.kind === 'removable' || source.kind === 'optical');
    return { local, optional };
  }, [sources]);

  const toggleSource = async (source: ApiSource) => {
    if (scanning) return;
    const next = new Set(selected);
    const enable = !next.has(source.id);
    if (enable) next.add(source.id);
    else next.delete(source.id);
    setSelected(next);
    try {
      const result = await api.updateSource(source.id, { enabled: enable });
      setSources((current) => current.map((item) => item.id === source.id ? result.source : item));
    } catch (error) {
      onNotify(error instanceof Error ? error.message : 'Could not update the source.', 'error');
    }
  };

  const addFolder = async () => {
    const value = newFolder.trim();
    if (!value) return;
    setBusy(true);
    try {
      const result = await api.addSource(value);
      setSources((current) => [...current.filter((item) => item.id !== result.source.id), result.source]);
      setSelected((current) => new Set(current).add(result.source.id));
      setNewFolder('');
      setShowAddFolder(false);
      onNotify('Folder added to scan sources.', 'success');
    } catch (error) {
      onNotify(error instanceof Error ? error.message : 'Could not add that folder.', 'error');
    } finally {
      setBusy(false);
    }
  };

  const addExclude = async () => {
    const value = newExclude.trim();
    if (!value) return;
    setBusy(true);
    try {
      const result = await api.addExclude(value);
      setExcludes((current) => [...current, result.exclude]);
      setNewExclude('');
      setShowAddExclude(false);
      onNotify('Folder excluded from scans.', 'success');
    } catch (error) {
      onNotify(error instanceof Error ? error.message : 'Could not add that exclusion.', 'error');
    } finally {
      setBusy(false);
    }
  };

  const removeExclude = async (exclude: Exclude) => {
    setBusy(true);
    try {
      await api.removeExclude(exclude.id);
      setExcludes((current) => current.filter((item) => item.id !== exclude.id));
    } catch (error) {
      onNotify(error instanceof Error ? error.message : 'Could not remove that exclusion.', 'error');
    } finally {
      setBusy(false);
    }
  };

  const start = async () => {
    if (selected.size === 0) {
      onNotify('Select at least one drive or folder to scan.', 'error');
      return;
    }
    setBusy(true);
    try {
      await onStart({ source_ids: [...selected], mode, intensity });
      setShowIssues(false);
    } catch (error) {
      onNotify(error instanceof Error ? error.message : 'Could not start the scan.', 'error');
    } finally {
      setBusy(false);
    }
  };

  const closeAfterScan = async () => {
    onClose();
    await onRefreshApp();
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={scanning ? (paused ? 'Scan paused' : 'Scanning computer') : 'Scan computer'}
      eyebrow="Private local indexing"
      width="820px"
      footer={
        scanning ? (
          <>
            <span className="footer-note"><span className="live-dot" /> You can keep browsing during the scan.</span>
            <span className="footer-spacer" />
            <Button icon={<ScanIcon size={14} />} onClick={closeAfterScan}>Close &amp; browse</Button>
            {scan.state === 'cancelling' ? (
              <Button disabled variant="danger">Cancelling…</Button>
            ) : (
              <Button variant="danger" icon={<StopIcon size={13} />} onClick={onCancel}>Cancel scan</Button>
            )}
          </>
        ) : (
          <>
            <span className="footer-note">
              {selected.size} source{selected.size === 1 ? '' : 's'} selected
            </span>
            <span className="footer-spacer" />
            <Button onClick={onClose}>Not now</Button>
            <Button
              variant="primary"
              icon={<PlayIcon size={14} />}
              onClick={() => void start()}
              disabled={busy || loading || selected.size === 0}
            >
              Start scan
            </Button>
          </>
        )
      }
    >
      {scanning ? (
        <div className="scan-live">
          <div className="scan-live-hero">
            <div className="scan-orbit">
              <span className="scan-orbit-ring" />
              <ScanIcon size={28} />
            </div>
            <div className="scan-live-copy">
              <h3>{paused ? 'Indexing is paused' : 'Discovering MIDI files'}</h3>
              <p>
                Scanning runs in the background. Existing library browsing, search,
                and playback stay available.
              </p>
              <div className="scan-progress">
                <span style={{ width: `${Math.max(2, scan.completion)}%` }} />
              </div>
              <span className="scan-current-path mono" title={scan.current_path}>{scan.current_path || 'Preparing sources…'}</span>
            </div>
          </div>
          <div className="scan-metrics">
            <div><span>Discovered</span><strong className="mono">{scan.discovered.toLocaleString()}</strong></div>
            <div><span>Indexed</span><strong className="mono">{scan.indexed.toLocaleString()}</strong></div>
            <div><span>Unchanged</span><strong className="mono">{scan.skipped.toLocaleString()}</strong></div>
            <div><span>Failed</span><strong className={`mono ${scan.failed ? 'is-danger' : ''}`}>{scan.failed.toLocaleString()}</strong></div>
            <div><span>Source directories</span><strong className="mono">{scan.sources_completed}/{scan.total_sources}</strong></div>
            <div><span>Current speed</span><strong className="mono">{scan.files_per_second.toFixed(1)}/s</strong></div>
          </div>
          <div className="scan-live-actions">
            {paused ? (
              <Button icon={<PlayIcon size={13} />} onClick={onResume}>Resume scan</Button>
            ) : (
              <Button icon={<PauseIcon size={13} />} onClick={onPause} disabled={scan.state === 'cancelling'}>Pause scan</Button>
            )}
            <span className="scan-cloud-note">
              {scan.skipped_cloud > 0 ? `${scan.skipped_cloud} cloud-only placeholder(s) skipped. ` : ''}
              {scan.skipped_links > 0 ? `${scan.skipped_links} link/junction(s) not followed.` : 'Symbolic links and junctions are never followed.'}
            </span>
          </div>
          {scan.issues_detail?.length ? (
            <div className="scan-issue-summary">
              <WarningIcon size={14} />
              <span>{scan.issues_detail.length} location issue{scan.issues_detail.length === 1 ? '' : 's'} reported. Unreadable locations do not stop the scan.</span>
              <button type="button" className="text-action" onClick={() => setShowIssues((value) => !value)}>
                {showIssues ? 'hide' : 'show'}
              </button>
            </div>
          ) : null}
          {showIssues || issues.length ? (
            <div className="scan-issues-list">
              {(showIssues ? issues : issues.slice(0, 2)).map((issue) => (
                <div key={issue.id} className="scan-issue-row">
                  <span className={`issue-kind kind-${issue.kind}`}>{issue.kind}</span>
                  <span className="cell-ellipsis" title={issue.path}>{issue.path || '—'}</span>
                  <span className="issue-message cell-ellipsis" title={issue.message}>{issue.message}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : (
        <div className="scan-config">
          {loading ? (
            <div className="scan-loading"><Spinner size={20} /> Reading drives…</div>
          ) : (
            <>
              <section className="scan-section">
                <div className="scan-section-heading">
                  <div>
                    <h3>Sources</h3>
                    <p>Choose the drives and folders to index. Network, removable and optical sources are optional.</p>
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => setShowAddFolder((value) => !value)}>
                    <FolderIcon size={13} /> Add folder
                  </Button>
                </div>
                {showAddFolder ? (
                  <form
                    className="path-add-row"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void addFolder();
                    }}
                  >
                    <input
                      className="input"
                      autoFocus
                      placeholder="Absolute folder path, e.g. D:\Music\MIDI"
                      value={newFolder}
                      onChange={(event) => setNewFolder(event.target.value)}
                    />
                    <Button type="submit" size="sm" disabled={busy}>Add</Button>
                  </form>
                ) : null}
                <div className="source-list">
                  {sources.length === 0 ? (
                    <p className="scan-empty">No drives were detected. Add a folder to get started.</p>
                  ) : null}
                  {[...sourceGroups.local, ...sourceGroups.optional].map((source) => {
                    const optional = Boolean(source.optional);
                    const unavailable = !Boolean(source.available);
                    const checked = selected.has(source.id);
                    const total = source.total_bytes ?? null;
                    return (
                      <label
                        key={source.id}
                        className={`source-row ${checked ? 'is-checked' : ''} ${unavailable ? 'is-unavailable' : ''}`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => void toggleSource(source)}
                          disabled={unavailable}
                        />
                        <span className="custom-check">{checked ? <CheckIcon size={11} /> : null}</span>
                        <span className="source-icon">{optional && source.kind !== 'folder' ? <span className="source-badge">{source.kind}</span> : <span className="source-drive-letter">{driveLetter(source.path)}</span>}</span>
                        <span className="source-copy">
                          <span className="source-label-row">
                            <strong>{source.label || source.path}</strong>
                            {optional ? <Badge tone="neutral">optional</Badge> : null}
                            {unavailable ? <Badge tone="red">unavailable</Badge> : null}
                          </span>
                          <span className="source-path mono">{source.path}{total ? ` · ${formatBytes(total)}` : ''}</span>
                        </span>
                        <span className="source-count mono">
                          {source.counts?.indexed?.toLocaleString() ?? 0}
                          <em>indexed</em>
                        </span>
                      </label>
                    );
                  })}
                </div>
                <p className="scan-footnote">
                  Protected system locations are always skipped. Cloud-only placeholders are
                  never downloaded. Archives are not opened.
                </p>
              </section>

              <section className="scan-section">
                <div className="scan-section-heading">
                  <div>
                    <h3>Excluded folders</h3>
                    <p>These paths are skipped, even when their drive is included.</p>
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => setShowAddExclude((value) => !value)}>
                    Add exclusion
                  </Button>
                </div>
                {showAddExclude ? (
                  <form
                    className="path-add-row"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void addExclude();
                    }}
                  >
                    <input
                      className="input"
                      autoFocus
                      placeholder="Absolute folder path to exclude"
                      value={newExclude}
                      onChange={(event) => setNewExclude(event.target.value)}
                    />
                    <Button type="submit" size="sm" disabled={busy}>Exclude</Button>
                  </form>
                ) : null}
                <div className="exclude-list">
                  {excludes.length === 0 ? (
                    <p className="scan-empty">No user exclusions.</p>
                  ) : excludes.map((exclude) => (
                    <div key={exclude.id} className="exclude-row">
                      <FolderIcon size={14} />
                      <span className="mono cell-ellipsis">{exclude.path}</span>
                      <button type="button" className="text-action" onClick={() => void removeExclude(exclude)}>remove</button>
                    </div>
                  ))}
                </div>
              </section>

              <section className="scan-section">
                <div className="scan-options-grid">
                  <div>
                    <h3>Scan mode</h3>
                    <Segmented
                      value={mode}
                      options={[
                        { value: 'incremental', label: 'Incremental' },
                        { value: 'full', label: 'Full reparse' },
                      ]}
                      onChange={(value) => setMode(value)}
                      ariaLabel="Scan mode"
                    />
                    <p className="scan-option-hint">
                      Incremental reuses unchanged files. Full reparse re-reads every MIDI file but keeps your favorites, tags, collections, notes and manual labels.
                    </p>
                  </div>
                  <div>
                    <h3>Intensity</h3>
                    <Segmented
                      value={intensity}
                      options={[
                        { value: 'eco', label: 'Eco' },
                        { value: 'balanced', label: 'Balanced' },
                        { value: 'turbo', label: 'Turbo' },
                      ]}
                      onChange={(value) => setIntensity(value)}
                      ariaLabel="Scan intensity"
                    />
                    <p className="scan-option-hint">
                      Eco uses one background worker, Balanced uses two, Turbo up to four. Lower intensity leaves more room for your DAW.
                    </p>
                  </div>
                </div>
              </section>

              <InlineNotice tone="info">
                MIDI Vault only reads files. It never modifies, moves, renames or deletes source files.
                Analysis and classifications stay on this computer.
              </InlineNotice>

              {lastScan ? (
                <section className="last-scan-summary">
                  <div>
                    <span>Last scan</span>
                    <strong>{lastScan.state}</strong>
                  </div>
                  <div>
                    <span>Discovered</span>
                    <strong className="mono">{lastScan.discovered.toLocaleString()}</strong>
                  </div>
                  <div>
                    <span>Indexed</span>
                    <strong className="mono">{lastScan.indexed.toLocaleString()}</strong>
                  </div>
                  <div>
                    <span>Failed</span>
                    <strong className={`mono ${lastScan.failed ? 'is-danger' : ''}`}>{lastScan.failed.toLocaleString()}</strong>
                  </div>
                  <div>
                    <span>Duration</span>
                    <strong className="mono">{formatDurationShort(lastScan.elapsed_seconds)}</strong>
                  </div>
                  <div>
                    <span>Finished</span>
                    <strong>{lastScan.ended_at ? formatRelativeTime(lastScan.ended_at) : '—'}</strong>
                  </div>
                </section>
              ) : null}
              {issues.length > 0 ? (
                <section className="scan-issues-config">
                  <div className="scan-section-heading">
                    <div>
                      <h3>Last scan issues</h3>
                      <p>Unreadable files or locations are recorded without stopping the scan.</p>
                    </div>
                    <Button size="sm" variant="ghost" onClick={() => setShowIssues((value) => !value)}>
                      {showIssues ? 'Hide' : `Show ${issues.length}`}
                    </Button>
                  </div>
                  {showIssues ? (
                    <div className="scan-issues-list">
                      {issues.map((issue) => (
                        <div key={issue.id} className="scan-issue-row">
                          <span className={`issue-kind kind-${issue.kind}`}>{issue.kind}</span>
                          <span className="cell-ellipsis" title={issue.path}>{issue.path || '—'}</span>
                          <span className="issue-message cell-ellipsis" title={issue.message}>{issue.message}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </section>
              ) : null}
            </>
          )}
        </div>
      )}
    </Modal>
  );
}

function driveLetter(path: string): string {
  const match = path.match(/^([A-Za-z]):/);
  return match ? match[1] : '•';
}
