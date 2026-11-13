import { useEffect, useMemo, useState } from 'react';
import type { Collection, Facets, FolderRow, LibraryFilters } from '../types';
import { INSTRUMENT_CATEGORIES, ROLE_CATEGORIES } from '../types';
import { instrumentColor, roleLabel } from '../lib/colors';
import { ChevronDown, ChevronRight, CollectionIcon, FolderIcon, PlusIcon, StarIcon } from './Icons';

interface FolderNode {
  name: string;
  path: string;
  count: number;
  children: FolderNode[];
}

function buildFolderTrees(
  folders: FolderRow[],
  sources: Array<{ id: number; label: string; path: string; available: number | boolean; kind: string }>,
): Array<{ source: (typeof sources)[number]; root: FolderNode }> {
  const result: Array<{ source: (typeof sources)[number]; root: FolderNode }> = [];
  const bySource = new Map<number, FolderRow[]>();
  for (const folder of folders) {
    if (!bySource.has(folder.source_id)) bySource.set(folder.source_id, []);
    bySource.get(folder.source_id)!.push(folder);
  }
  for (const source of sources) {
    const rows = bySource.get(source.id) || [];
    if (rows.length === 0) continue;
    const root: FolderNode = {
      name: source.label || source.path,
      path: source.path,
      count: 0,
      children: [],
    };
    const normalRoot = source.path.replace(/[\\/]+$/, '').toLowerCase();
    const nodes = new Map<string, FolderNode>();
    nodes.set(normalRoot, root);
    const sorted = [...rows].sort((a, b) => a.path.localeCompare(b.path));
    for (const row of sorted) {
      const normalPath = row.path.replace(/[\\/]+$/, '').toLowerCase();
      if (normalPath === normalRoot) {
        root.count += row.count;
        continue;
      }
      if (!normalPath.startsWith(normalRoot + '\\') && !normalPath.startsWith(normalRoot + '/')) {
        continue;
      }
      const relative = row.path.slice(source.path.replace(/[\\/]+$/, '').length + 1);
      const segments = relative.split(/[\\/]/).filter(Boolean);
      let parent = root;
      let accumulated = source.path.replace(/[\\/]+$/, '');
      for (const segment of segments) {
        accumulated = `${accumulated}\\${segment}`;
        let node = nodes.get(accumulated.toLowerCase());
        if (!node) {
          node = { name: segment, path: accumulated, count: 0, children: [] };
          nodes.set(accumulated.toLowerCase(), node);
          parent.children.push(node);
        }
        parent = node;
      }
      parent.count += row.count;
    }
    const addCounts = (node: FolderNode): number => {
      let total = node.count;
      for (const child of node.children) total += addCounts(child);
      node.count = total;
      node.children.sort((a, b) => a.name.localeCompare(b.name));
      return total;
    };
    addCounts(root);
    result.push({ source, root });
  }
  return result;
}

export function Sidebar({
  facets,
  filters,
  onPatchFilters,
  folders,
  collections,
  onCreateCollection,
  onOpenScan,
}: {
  facets: Facets | null;
  filters: LibraryFilters;
  onPatchFilters: (patch: Partial<LibraryFilters>) => void;
  folders: FolderRow[];
  collections: Collection[];
  onCreateCollection: (name: string) => Promise<void>;
  onOpenScan: () => void;
}) {
  const [openInstruments, setOpenInstruments] = useState(true);
  const [openRoles, setOpenRoles] = useState(true);
  const [openFolders, setOpenFolders] = useState(true);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  const [newCollection, setNewCollection] = useState(false);
  const [collectionName, setCollectionName] = useState('');
  const totals = facets?.totals;
  const trees = useMemo(
    () => buildFolderTrees(folders, facets?.sources || []),
    [folders, facets?.sources],
  );

  const baseNavigation = {
    favorite: false,
    uncertain: false,
    duplicate: '',
    collection_id: '',
    folder: '',
    page: 1,
  } as Partial<LibraryFilters>;

  const activeView =
    filters.favorite ? 'favorites'
      : filters.uncertain ? 'uncertain'
        : filters.duplicate === 'exact' ? 'exact'
          : filters.duplicate === 'similar' ? 'similar'
            : filters.collection_id ? 'collection'
              : 'all';

  const toggleInstrument = (category: string) => {
    const next = filters.instrument.includes(category)
      ? filters.instrument.filter((item) => item !== category)
      : [...filters.instrument, category];
    onPatchFilters({ instrument: next, page: 1 });
  };

  const toggleRole = (role: string) => {
    const next = filters.role.includes(role)
      ? filters.role.filter((item) => item !== role)
      : [...filters.role, role];
    onPatchFilters({ role: next, page: 1 });
  };

  const toggleFolder = (path: string) => {
    setExpandedFolders((current) => {
      const next = new Set(current);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const selectFolder = (path: string) => {
    onPatchFilters({
      ...baseNavigation,
      folder: path,
      page: 1,
    });
  };

  const renderFolder = (node: FolderNode, depth: number, isRoot = false) => {
    const expanded = expandedFolders.has(node.path);
    const active = filters.folder.toLowerCase() === node.path.toLowerCase();
    const visibleChildren = expanded ? node.children.slice(0, 80) : [];
    return (
      <div key={node.path} className="folder-node">
        <div
          className={`folder-row ${active ? 'is-active' : ''} ${isRoot ? 'is-root' : ''}`}
          style={{ paddingLeft: 10 + depth * 12 }}
        >
          {node.children.length > 0 ? (
            <button
              type="button"
              className="tree-caret"
              onClick={(event) => {
                event.stopPropagation();
                toggleFolder(node.path);
              }}
              aria-label={expanded ? 'Collapse folder' : 'Expand folder'}
            >
              {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </button>
          ) : (
            <span className="tree-caret-spacer" />
          )}
          <button type="button" className="folder-name" onClick={() => selectFolder(node.path)} title={node.path}>
            <FolderIcon size={13} />
            <span>{node.name}</span>
          </button>
          <span className="sidebar-count mono">{node.count}</span>
        </div>
        {expanded ? (
          <div className="folder-children">
            {visibleChildren.map((child) => renderFolder(child, depth + 1))}
            {node.children.length > 80 ? (
              <div className="folder-overflow">+{node.children.length - 80} more folders</div>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-scroll">
        <nav className="sidebar-nav" aria-label="Library views">
          <button
            type="button"
            className={`nav-row ${activeView === 'all' && !filters.folder ? 'is-active' : ''}`}
            onClick={() => onPatchFilters({ ...baseNavigation, instrument: [], role: [], page: 1 })}
          >
            <span className="nav-icon nav-icon-all" aria-hidden="true" />
            <span>All MIDI</span>
            <span className="sidebar-count mono">{totals ? (totals.total - totals.failed).toLocaleString() : '—'}</span>
          </button>
          <button
            type="button"
            className={`nav-row ${filters.favorite ? 'is-active' : ''}`}
            onClick={() => onPatchFilters({ ...baseNavigation, favorite: true, page: 1 })}
          >
            <span className="nav-icon"><StarIcon size={14} filled={filters.favorite} /></span>
            <span>Favorites</span>
            <span className="sidebar-count mono">{totals?.favorites ?? 0}</span>
          </button>
          <button
            type="button"
            className={`nav-row ${filters.uncertain ? 'is-active' : ''}`}
            onClick={() => onPatchFilters({ ...baseNavigation, uncertain: true, page: 1 })}
          >
            <span className="nav-icon"><span className="uncertain-mark">?</span></span>
            <span>Uncertain</span>
            <span className="sidebar-count mono">{totals?.uncertain ?? 0}</span>
          </button>
          <button
            type="button"
            className={`nav-row ${filters.duplicate === 'exact' ? 'is-active' : ''}`}
            onClick={() => onPatchFilters({ ...baseNavigation, duplicate: 'exact', page: 1 })}
          >
            <span className="nav-icon"><span className="duplicate-mark" aria-hidden="true">⧉</span></span>
            <span>Exact duplicates</span>
            <span className="sidebar-count mono">{totals?.exact_duplicates ?? 0}</span>
          </button>
          <button
            type="button"
            className={`nav-row ${filters.duplicate === 'similar' ? 'is-active' : ''}`}
            onClick={() => onPatchFilters({ ...baseNavigation, duplicate: 'similar', page: 1 })}
          >
            <span className="nav-icon"><span className="similar-mark" aria-hidden="true">≈</span></span>
            <span>Similar files</span>
            <span className="sidebar-count mono">{totals?.similar_duplicates ?? 0}</span>
          </button>
        </nav>

        <section className="sidebar-section instrument-section">
          <button
            className="sidebar-section-title"
            onClick={() => setOpenInstruments((value) => !value)}
            type="button"
          >
            <span>Sound family</span>
            {openInstruments ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          </button>
          {openInstruments ? (
            <div className="category-list">
              {INSTRUMENT_CATEGORIES.filter((category) => category !== 'Mixed arrangement' && category !== 'Unknown').map((category) => {
                const count = facets?.instruments.find((item) => item.value === category)?.count || 0;
                const active = filters.instrument.includes(category);
                return (
                  <button
                    key={category}
                    type="button"
                    className={`category-row ${active ? 'is-active' : ''}`}
                    onClick={() => toggleInstrument(category)}
                  >
                    <span className="category-dot" style={{ background: instrumentColor(category) }} />
                    <span>{category === 'Brass/woodwinds' ? 'Brass / woodwinds' : category === 'Piano/keys' ? 'Piano / keys' : category === 'Guitar/plucked' ? 'Guitar / plucked' : category}</span>
                    <span className="sidebar-count mono">{count}</span>
                  </button>
                );
              })}
              {['Mixed arrangement', 'Unknown'].map((category) => {
                const count = facets?.instruments.find((item) => item.value === category)?.count || 0;
                if (!count) return null;
                const active = filters.instrument.includes(category);
                return (
                  <button
                    key={category}
                    type="button"
                    className={`category-row ${active ? 'is-active' : ''}`}
                    onClick={() => toggleInstrument(category)}
                  >
                    <span className="category-dot" style={{ background: instrumentColor(category) }} />
                    <span>{category}</span>
                    <span className="sidebar-count mono">{count}</span>
                  </button>
                );
              })}
            </div>
          ) : null}
        </section>

        <section className="sidebar-section role-section">
          <button
            className="sidebar-section-title"
            onClick={() => setOpenRoles((value) => !value)}
            type="button"
          >
            <span>Musical role</span>
            {openRoles ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          </button>
          {openRoles ? (
            <div className="category-list role-list">
              {ROLE_CATEGORIES.filter((role) => role !== 'Complete song or multi-part arrangement').map((role) => {
                const count = facets?.roles.find((item) => item.value === role)?.count || 0;
                if (!count && role !== 'Unknown') return null;
                const active = filters.role.includes(role);
                return (
                  <button
                    key={role}
                    type="button"
                    className={`category-row ${active ? 'is-active' : ''}`}
                    onClick={() => toggleRole(role)}
                  >
                    <span className="role-dot" aria-hidden="true" />
                    <span>{roleLabel(role)}</span>
                    <span className="sidebar-count mono">{count}</span>
                  </button>
                );
              })}
            </div>
          ) : null}
        </section>

        <section className="sidebar-section collections-section">
          <div className="sidebar-section-title static">
            <span>Collections</span>
            <button
              type="button"
              className="section-add"
              aria-label="New collection"
              onClick={() => setNewCollection((value) => !value)}
            >
              <PlusIcon size={13} />
            </button>
          </div>
          {newCollection ? (
            <form
              className="new-collection"
              onSubmit={async (event) => {
                event.preventDefault();
                if (!collectionName.trim()) return;
                await onCreateCollection(collectionName.trim());
                setCollectionName('');
                setNewCollection(false);
              }}
            >
              <input
                autoFocus
                className="input input-compact"
                placeholder="Collection name"
                value={collectionName}
                onChange={(event) => setCollectionName(event.target.value)}
              />
              <button className="mini-action" type="submit">Add</button>
            </form>
          ) : null}
          <div className="category-list">
            {collections.length === 0 ? (
              <p className="sidebar-empty">Group files without moving them.</p>
            ) : collections.map((collection) => (
              <button
                key={collection.id}
                type="button"
                className={`category-row ${filters.collection_id === String(collection.id) ? 'is-active' : ''}`}
                onClick={() => onPatchFilters({
                  ...baseNavigation,
                  collection_id: String(collection.id),
                  page: 1,
                })}
              >
                <span className="collection-glyph"><CollectionIcon size={13} /></span>
                <span>{collection.name}</span>
                <span className="sidebar-count mono">{collection.count ?? 0}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="sidebar-section folders-section">
          <button
            className="sidebar-section-title"
            onClick={() => setOpenFolders((value) => !value)}
            type="button"
          >
            <span>Folders</span>
            {openFolders ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          </button>
          {openFolders ? (
            trees.length > 0 ? (
              <div className="folder-tree">
                {trees.map(({ root }) => renderFolder(root, 0, true))}
              </div>
            ) : (
              <div className="sidebar-empty folder-empty">
                No indexed folders yet.{' '}
                <button type="button" onClick={onOpenScan}>Scan computer</button>
              </div>
            )
          ) : null}
        </section>
      </div>
      <div className="sidebar-footer">
        <span className="privacy-dot" />
        <span>Files stay on this computer</span>
      </div>
    </aside>
  );
}
