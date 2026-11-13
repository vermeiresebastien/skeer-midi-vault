import { useMemo, type DragEvent } from 'react';
import type {
  Collection,
  Facets,
  LibraryFilters,
  LibraryItem,
  LibraryResponse,
} from '../types';
import { INSTRUMENT_CATEGORIES, ROLE_CATEGORIES } from '../types';
import { api, rawFileUrl } from '../api';
import {
  formatBpm,
  formatDurationShort,
  formatTime,
  basename,
} from '../lib/format';
import { familyLabel, instrumentColor, roleLabel, trackColor } from '../lib/colors';
import {
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  CloseIcon,
  DragIcon,
  ExportIcon,
  FileIcon,
  FilterIcon,
  SearchIcon,
  StarIcon,
} from './Icons';
import { Badge, Button, IconButton, Select, Spinner } from './Common';

export function LibraryView({
  library,
  filters,
  facets,
  collections,
  loading,
  selectedId,
  selectedIds,
  title,
  subtitle,
  onPatchFilters,
  onSelect,
  onToggleSelected,
  onSelectAll,
  onClearSelection,
  onToggleFavorite,
  onOpenFilters,
  onOpenScan,
  onBulkAction,
  onExportSelected,
  onRefresh,
}: {
  library: LibraryResponse | null;
  filters: LibraryFilters;
  facets: Facets | null;
  collections: Collection[];
  loading: boolean;
  selectedId: number | null;
  selectedIds: Set<number>;
  title: string;
  subtitle: string;
  onPatchFilters: (patch: Partial<LibraryFilters>) => void;
  onSelect: (item: LibraryItem) => void;
  onToggleSelected: (id: number) => void;
  onSelectAll: (ids: number[]) => void;
  onClearSelection: () => void;
  onToggleFavorite: (item: LibraryItem) => void;
  onOpenFilters: () => void;
  onOpenScan: () => void;
  onBulkAction: (action: 'favorite' | 'collection' | 'label', payload?: {
    dimension?: 'instrument' | 'role';
    value?: string;
    collectionId?: number;
    favorite?: boolean;
  }) => void;
  onExportSelected: () => void;
  onRefresh: () => void;
}) {
  const items = library?.items ?? [];
  const pageIds = items.map((item) => item.id);
  const allSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id));
  const activeFilterCount = countActiveFilters(filters);
  const activeChips = buildActiveChips(filters, facets, collections);

  const startDrag = (event: DragEvent<HTMLElement>, item: LibraryItem) => {
    const url = new URL(rawFileUrl(item.id), window.location.href).toString();
    const mime = 'audio/midi';
    event.dataTransfer.effectAllowed = 'copy';
    event.dataTransfer.setData('DownloadURL', `${mime}:${item.filename}:${url}`);
    event.dataTransfer.setData('text/plain', item.path);
  };

  const emptyTitle = activeFilterCount > 0 || filters.q ? 'No files match these filters' : 'Your MIDI library is empty';
  const emptyBody = activeFilterCount > 0 || filters.q
    ? 'Try removing a filter or broadening the search.'
    : 'Scan your drives or add a folder. MIDI Vault indexes everything locally and never changes the source files.';

  return (
    <section className="library-pane">
      <header className="library-heading">
        <div className="library-title-block">
          <div className="library-kicker">
            <span>Library</span>
            {loading ? <Spinner size={12} /> : null}
          </div>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
        <div className="library-heading-actions">
          <div className="search-wrap">
            <SearchIcon size={16} />
            <input
              id="library-search"
              type="search"
              className="search-input"
              placeholder="Search filenames, paths, track names, tags, notes…"
              value={filters.q}
              onChange={(event) => onPatchFilters({ q: event.target.value, page: 1 })}
              aria-label="Search library"
              autoComplete="off"
            />
            <kbd>/</kbd>
          </div>
          <Button
            variant={activeFilterCount > 0 ? 'primary-soft' as 'secondary' : 'secondary'}
            icon={<FilterIcon size={15} />}
            onClick={onOpenFilters}
            className={activeFilterCount > 0 ? 'is-filtered' : ''}
          >
            Filters
            {activeFilterCount > 0 ? <span className="filter-count">{activeFilterCount}</span> : null}
          </Button>
        </div>
      </header>

      <div className="library-toolbar">
        <div className="toolbar-left">
          <span className="result-count">
            {library ? (
              <>
                <strong>{library.total.toLocaleString()}</strong>{' '}
                {library.total === 1 ? 'file' : 'files'}
              </>
            ) : 'Loading…'}
          </span>
          {activeChips.length > 0 ? (
            <div className="active-filters">
              {activeChips.map((chip) => (
                <button
                  key={chip.key}
                  type="button"
                  className="filter-chip"
                  onClick={() => onPatchFilters(chip.patch)}
                  title={`Remove ${chip.label}`}
                >
                  <span>{chip.label}</span>
                  <CloseIcon size={11} />
                </button>
              ))}
              <button
                type="button"
                className="clear-filters"
                onClick={() => onPatchFilters({
                  q: '',
                  instrument: [],
                  role: [],
                  style: [],
                  tempo_min: '',
                  tempo_max: '',
                  time_sig: '',
                  key: '',
                  key_source: '',
                  duration_min: '',
                  duration_max: '',
                  bars_min: '',
                  bars_max: '',
                  pitch_min: '',
                  pitch_max: '',
                  density_min: '',
                  density_max: '',
                  confidence_min: '',
                  folder: '',
                  source_id: '',
                  favorite: false,
                  uncertain: false,
                  duplicate: '',
                  scan_state: '',
                  collection_id: '',
                  tag: '',
                  include_failed: false,
                  page: 1,
                })}
              >
                Clear all
              </button>
            </div>
          ) : null}
        </div>
        <div className="toolbar-right">
          <label className="sort-control">
            <span>Sort</span>
            <Select
              value={filters.sort}
              onChange={(event) => onPatchFilters({ sort: event.target.value, page: 1 })}
              aria-label="Sort files"
            >
              {filters.q ? <option value="relevance">Relevance</option> : null}
              <option value="name">Name</option>
              <option value="recent">Recently indexed</option>
              <option value="duration">Longest</option>
              <option value="tempo">Tempo</option>
              <option value="bars">Bar length</option>
              <option value="confidence">Confidence</option>
            </Select>
          </label>
          <IconButton label="Refresh library" onClick={onRefresh} className={loading ? 'is-busy' : ''}>
            <span className={loading ? 'spin' : ''} style={{ display: 'inline-flex' }}>⟳</span>
          </IconButton>
        </div>
      </div>

      {selectedIds.size > 0 ? (
        <div className="bulk-bar">
          <div className="bulk-summary">
            <span className="bulk-count mono">{selectedIds.size}</span>
            <span>selected</span>
          </div>
          <div className="bulk-actions">
            <button type="button" className="bulk-action" onClick={() => onBulkAction('favorite', { favorite: true })}>
              <StarIcon size={13} /> Favorite
            </button>
            <label className="bulk-select">
              <span>Set family</span>
              <Select
                value=""
                onChange={(event) => {
                  if (event.target.value) onBulkAction('label', { dimension: 'instrument', value: event.target.value });
                }}
              >
                <option value="">Choose…</option>
                {INSTRUMENT_CATEGORIES.map((category) => (
                  <option key={category} value={category}>{category}</option>
                ))}
              </Select>
            </label>
            <label className="bulk-select">
              <span>Set role</span>
              <Select
                value=""
                onChange={(event) => {
                  if (event.target.value) onBulkAction('label', { dimension: 'role', value: event.target.value });
                }}
              >
                <option value="">Choose…</option>
                {ROLE_CATEGORIES.map((role) => (
                  <option key={role} value={role}>{roleLabel(role)}</option>
                ))}
              </Select>
            </label>
            {collections.length > 0 ? (
              <label className="bulk-select">
                <span>Add to</span>
                <Select
                  value=""
                  onChange={(event) => {
                    if (event.target.value) onBulkAction('collection', { collectionId: Number(event.target.value) });
                  }}
                >
                  <option value="">Collection…</option>
                  {collections.map((collection) => (
                    <option key={collection.id} value={collection.id}>{collection.name}</option>
                  ))}
                </Select>
              </label>
            ) : null}
            <button type="button" className="bulk-action" onClick={onExportSelected}>
              <ExportIcon size={13} /> Export
            </button>
          </div>
          <IconButton label="Clear selection" onClick={onClearSelection}><CloseIcon size={14} /></IconButton>
        </div>
      ) : null}

      <div className={`file-list-wrap ${loading ? 'is-loading' : ''}`}>
        <div className="file-table-header">
          <span className="check-cell">
            <input
              type="checkbox"
              aria-label="Select all files on page"
              checked={allSelected}
              onChange={() => (allSelected ? onClearSelection() : onSelectAll(pageIds))}
            />
          </span>
          <span className="fav-cell" />
          <span className="name-cell">Name</span>
          <span>Sound family</span>
          <span className="role-cell">Musical role</span>
          <span className="num-cell">BPM</span>
          <span className="key-cell">Key</span>
          <span className="num-cell">Length</span>
          <span className="confidence-cell">Conf.</span>
        </div>
        <div className="file-table-body">
          {items.map((item, index) => {
            const active = selectedId === item.id;
            const selected = selectedIds.has(item.id);
            return (
              <div
                key={item.id}
                role="option"
                aria-selected={active}
                tabIndex={0}
                draggable
                onDragStart={(event) => startDrag(event, item)}
                className={`file-row ${active ? 'is-active' : ''} ${selected ? 'is-selected' : ''} ${item.scan_state !== 'indexed' ? 'is-issue' : ''}`}
                onClick={() => onSelect(item)}
                onDoubleClick={() => onSelect(item)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    onSelect(item);
                  }
                }}
                style={{ animationDelay: `${Math.min(index, 12) * 10}ms` }}
              >
                <span className="check-cell" onClick={(event) => event.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={selected}
                    aria-label={`Select ${item.filename}`}
                    onChange={() => onToggleSelected(item.id)}
                  />
                </span>
                <span className="fav-cell">
                  <button
                    type="button"
                    className={`row-star ${item.favorite ? 'is-favorite' : ''}`}
                    aria-label={item.favorite ? 'Remove favorite' : 'Add favorite'}
                    onClick={(event) => {
                      event.stopPropagation();
                      onToggleFavorite(item);
                    }}
                  >
                    <StarIcon size={14} filled={item.favorite} />
                  </button>
                </span>
                <span className="name-cell">
                  <span className="file-name-line">
                    <span className="file-name">{item.filename}</span>
                    {item.exact_group_id ? <Badge tone="amber" title="Exact content duplicate">copy</Badge> : null}
                    {!item.exact_group_id && item.similar_group_id ? <Badge tone="neutral" title="Musically similar file">similar</Badge> : null}
                    {item.uncertain ? <span className="uncertain-indicator" title="Classification uncertain" /> : null}
                    {item.scan_state !== 'indexed' ? (
                      <Badge tone="red">{item.scan_state === 'missing' ? 'missing' : 'issue'}</Badge>
                    ) : null}
                  </span>
                  <span className="file-subline" title={item.path}>
                    <button
                      type="button"
                      className="source-link"
                      onClick={(event) => {
                        event.stopPropagation();
                        event.preventDefault();
                        if (item.source_id != null) {
                          onPatchFilters({ source_id: String(item.source_id), page: 1 });
                        }
                      }}
                      tabIndex={-1}
                      title={item.source_id != null ? 'Show this source only' : undefined}
                    >
                      {item.source_label || basename(item.dirname)}
                    </button>
                    <span className="path-sep">/</span>
                    <span className="file-folder">{folderTail(item.dirname)}</span>
                    {item.format === 2 ? <span className="format-pill">F2</span> : null}
                    {item.is_missing || item.source_available === false ? <Badge tone="red">offline</Badge> : null}
                  </span>
                </span>
                <span className="family-cell">
                  <span className="family-dot" style={{ background: instrumentColor(item.instrument) }} />
                  <span className="cell-ellipsis">{familyLabel(item.instrument)}</span>
                </span>
                <span className="role-cell cell-ellipsis">{roleLabel(item.role)}</span>
                <span className="num-cell mono">{formatBpm(item.tempo_bpm)}</span>
                <span className="key-cell key-name">
                  {item.key_name ? (
                    <span title={item.key_source === 'estimated' ? 'Estimated key, not embedded MIDI metadata' : 'Embedded key signature'}>
                      {item.key_source === 'estimated' ? <span className="key-estimated">~</span> : null}
                      {shortKey(item.key_name)}
                    </span>
                  ) : '—'}
                </span>
                <span className="num-cell mono">{formatDurationShort(item.duration_seconds)}</span>
                <span className="confidence-cell">
                  <span
                    className={`confidence-dot ${(item.instrument_source === 'user' || item.role_source === 'user') ? 'is-user' : ''}`}
                    title={`${Math.round((Math.min(item.instrument_confidence || 0, item.role_confidence || 0)) * 100)}% classification confidence`}
                  >
                    <span
                      style={{
                        height: `${Math.max(12, Math.min(100, (Math.min(item.instrument_confidence || 0, item.role_confidence || 0)) * 100))}%`,
                      }}
                    />
                  </span>
                </span>
              </div>
            );
          })}
          {!items.length && !loading ? (
            <div className="empty-library">
              <div className="empty-mark">
                <img src="/brand/skeer-mark.png" alt="" />
              </div>
              <h2>{emptyTitle}</h2>
              <p>{emptyBody}</p>
              <div className="empty-actions">
                {activeFilterCount > 0 || filters.q ? (
                  <Button
                    onClick={() => onPatchFilters({
                      q: '',
                      instrument: [],
                      role: [],
                      style: [],
                      tempo_min: '',
                      tempo_max: '',
                      time_sig: '',
                      key: '',
                      key_source: '',
                      duration_min: '',
                      duration_max: '',
                      bars_min: '',
                      bars_max: '',
                      pitch_min: '',
                      pitch_max: '',
                      density_min: '',
                      density_max: '',
                      confidence_min: '',
                      folder: '',
                      source_id: '',
                      favorite: false,
                      uncertain: false,
                      duplicate: '',
                      scan_state: '',
                      collection_id: '',
                      tag: '',
                      include_failed: false,
                      page: 1,
                    })}
                  >
                    Clear filters
                  </Button>
                ) : (
                  <Button variant="primary" onClick={onOpenScan}>Scan computer</Button>
                )}
              </div>
              <div className="empty-hint">
                <span className="drag-hint"><DragIcon size={13} /> Drag a file into your DAW at any time.</span>
              </div>
            </div>
          ) : null}
        </div>
        {loading && !items.length ? (
          <div className="skeleton-list">
            {Array.from({ length: 7 }).map((_, index) => (
              <div key={index} className="skeleton-row">
                <span /><span /><span /><span /><span />
              </div>
            ))}
          </div>
        ) : null}
      </div>

      <footer className="library-footer">
        <div className="library-hint">
          <FileIcon size={13} />
          <span>MIDI only · {facets?.totals.total ? `${facets.totals.total.toLocaleString()} indexed entries` : 'No files yet'}</span>
          {library?.fts ? <span className="fts-hint">full-text index</span> : null}
        </div>
        {library && library.pages > 1 ? (
          <div className="pagination">
            <IconButton
              label="Previous page"
              disabled={filters.page <= 1 || loading}
              onClick={() => onPatchFilters({ page: Math.max(1, filters.page - 1) })}
            >
              <ChevronLeft size={14} />
            </IconButton>
            <span className="mono">page {filters.page} / {library.pages}</span>
            <IconButton
              label="Next page"
              disabled={filters.page >= library.pages || loading}
              onClick={() => onPatchFilters({ page: Math.min(library.pages, filters.page + 1) })}
            >
              <ChevronRight size={14} />
            </IconButton>
          </div>
        ) : null}
      </footer>
    </section>
  );
}

function countActiveFilters(filters: LibraryFilters): number {
  let count = 0;
  if (filters.q) count += 1;
  count += filters.instrument.length + filters.role.length + filters.style.length;
  const singles = [
    filters.tempo_min, filters.tempo_max, filters.time_sig, filters.key,
    filters.key_source, filters.duration_min, filters.duration_max,
    filters.bars_min, filters.bars_max, filters.pitch_min, filters.pitch_max,
    filters.density_min, filters.density_max, filters.confidence_min,
    filters.folder, filters.source_id, filters.duplicate, filters.scan_state,
    filters.collection_id, filters.tag,
  ];
  count += singles.filter((value) => value !== '').length;
  if (filters.favorite) count += 1;
  if (filters.uncertain) count += 1;
  if (filters.include_failed) count += 1;
  return count;
}

function folderTail(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts.slice(-2).join(' / ');
}

function shortKey(key: string): string {
  return key
    .replace(' major', '')
    .replace(' minor', 'm');
}

function buildActiveChips(
  filters: LibraryFilters,
  facets: Facets | null,
  collections: Collection[],
): Array<{ key: string; label: string; patch: Partial<LibraryFilters> }> {
  const chips: Array<{ key: string; label: string; patch: Partial<LibraryFilters> }> = [];
  for (const category of filters.instrument) {
    chips.push({
      key: `instrument-${category}`,
      label: familyLabel(category),
      patch: { instrument: filters.instrument.filter((item) => item !== category), page: 1 },
    });
  }
  for (const role of filters.role) {
    chips.push({
      key: `role-${role}`,
      label: roleLabel(role),
      patch: { role: filters.role.filter((item) => item !== role), page: 1 },
    });
  }
  for (const style of filters.style) {
    chips.push({
      key: `style-${style}`,
      label: style,
      patch: { style: filters.style.filter((item) => item !== style), page: 1 },
    });
  }
  if (filters.favorite) chips.push({ key: 'favorites', label: 'Favorites', patch: { favorite: false, page: 1 } });
  if (filters.uncertain) chips.push({ key: 'uncertain', label: 'Uncertain', patch: { uncertain: false, page: 1 } });
  if (filters.duplicate) {
    chips.push({
      key: 'duplicate',
      label: filters.duplicate === 'exact' ? 'Exact duplicates' : 'Similar files',
      patch: { duplicate: '', page: 1 },
    });
  }
  if (filters.folder) {
    chips.push({ key: 'folder', label: basename(filters.folder), patch: { folder: '', page: 1 } });
  }
  if (filters.collection_id) {
    const collection = collections.find((item) => String(item.id) === filters.collection_id);
    chips.push({
      key: 'collection',
      label: collection?.name || 'Collection',
      patch: { collection_id: '', page: 1 },
    });
  }
  if (filters.source_id) {
    const source = facets?.sources.find((item) => String(item.id) === filters.source_id);
    chips.push({ key: 'source', label: source?.label || 'Source', patch: { source_id: '', page: 1 } });
  }
  if (filters.tempo_min || filters.tempo_max) {
    chips.push({
      key: 'tempo',
      label: `${filters.tempo_min || '0'}–${filters.tempo_max || '∞'} BPM`,
      patch: { tempo_min: '', tempo_max: '', page: 1 },
    });
  }
  if (filters.time_sig) chips.push({ key: 'meter', label: filters.time_sig, patch: { time_sig: '', page: 1 } });
  if (filters.key) chips.push({ key: 'key', label: filters.key, patch: { key: '', page: 1 } });
  if (filters.key_source) {
    chips.push({ key: 'keysource', label: `${filters.key_source} key`, patch: { key_source: '', page: 1 } });
  }
  if (filters.duration_min || filters.duration_max) {
    chips.push({
      key: 'duration',
      label: `${filters.duration_min || '0'}–${filters.duration_max || '∞'} sec`,
      patch: { duration_min: '', duration_max: '', page: 1 },
    });
  }
  if (filters.bars_min || filters.bars_max) {
    chips.push({
      key: 'bars',
      label: `${filters.bars_min || '0'}–${filters.bars_max || '∞'} bars`,
      patch: { bars_min: '', bars_max: '', page: 1 },
    });
  }
  if (filters.pitch_min || filters.pitch_max) {
    chips.push({
      key: 'pitch',
      label: `pitch ${filters.pitch_min || '0'}–${filters.pitch_max || '127'}`,
      patch: { pitch_min: '', pitch_max: '', page: 1 },
    });
  }
  if (filters.density_min || filters.density_max) {
    chips.push({
      key: 'density',
      label: `density ${filters.density_min || '0'}–${filters.density_max || '∞'}`,
      patch: { density_min: '', density_max: '', page: 1 },
    });
  }
  if (filters.confidence_min) {
    chips.push({
      key: 'confidence',
      label: `confidence ≥ ${Math.round(Number(filters.confidence_min) * 100)}%`,
      patch: { confidence_min: '', page: 1 },
    });
  }
  if (filters.tag) chips.push({ key: 'tag', label: `#${filters.tag}`, patch: { tag: '', page: 1 } });
  if (filters.scan_state) {
    chips.push({ key: 'state', label: filters.scan_state, patch: { scan_state: '', page: 1 } });
  }
  if (filters.include_failed) {
    chips.push({ key: 'failed', label: 'Include issues', patch: { include_failed: false, page: 1 } });
  }
  return chips;
}
