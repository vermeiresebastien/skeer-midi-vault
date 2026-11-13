import type {
  Bootstrap,
  Collection,
  Drive,
  Facets,
  FileDetails,
  FolderRow,
  LibraryFilters,
  LibraryResponse,
  ScanIssue,
  ScanStatus,
  Tag,
} from './types';

const BASE = '/api';

export class ApiRequestError extends Error {
  status: number;
  constructor(message: string, status = 0) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...(init?.headers || {}),
      },
    });
  } catch (error) {
    throw new ApiRequestError(
      error instanceof Error
        ? `The local SKEER service is not reachable: ${error.message}`
        : 'The local SKEER service is not reachable.',
      0,
    );
  }
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { error?: string };
      if (payload?.error) message = payload.error;
    } catch {
      // Keep the generic message.
    }
    throw new ApiRequestError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function jsonBody(payload: unknown): RequestInit {
  return { body: JSON.stringify(payload) };
}

export function filtersToQuery(filters: LibraryFilters): string {
  const search = new URLSearchParams();
  if (filters.q.trim()) search.set('q', filters.q.trim());
  if (filters.instrument.length) search.set('instrument', filters.instrument.join(','));
  if (filters.role.length) search.set('role', filters.role.join(','));
  if (filters.style.length) search.set('style', filters.style.join(','));
  const numericKeys = [
    'tempo_min',
    'tempo_max',
    'duration_min',
    'duration_max',
    'bars_min',
    'bars_max',
    'pitch_min',
    'pitch_max',
    'density_min',
    'density_max',
    'confidence_min',
  ] as const;
  for (const key of numericKeys) {
    if (filters[key] !== '') search.set(key, filters[key]);
  }
  if (filters.time_sig) search.set('time_sig', filters.time_sig);
  if (filters.key) search.set('key', filters.key);
  if (filters.key_source) search.set('key_source', filters.key_source);
  if (filters.folder) search.set('folder', filters.folder);
  if (filters.source_id) search.set('source_id', filters.source_id);
  if (filters.favorite) search.set('favorite', '1');
  if (filters.uncertain) search.set('uncertain', '1');
  if (filters.duplicate) search.set('duplicate', filters.duplicate);
  if (filters.scan_state) search.set('scan_state', filters.scan_state);
  if (filters.include_failed) search.set('include_failed', '1');
  if (filters.collection_id) search.set('collection_id', filters.collection_id);
  if (filters.tag) search.set('tag', filters.tag);
  if (filters.sort) search.set('sort', filters.sort);
  search.set('page', String(filters.page));
  search.set('page_size', String(filters.page_size));
  return search.toString();
}

export const api = {
  bootstrap: () => request<Bootstrap>('/bootstrap'),
  health: () => request<Record<string, unknown>>('/health'),
  drives: () => request<{ drives: Drive[]; sources: Bootstrap['sources'] }>('/drives'),
  library: (filters: LibraryFilters) =>
    request<LibraryResponse>(`/library?${filtersToQuery(filters)}`),
  facets: () => request<Facets>('/facets'),
  file: (id: number) => request<FileDetails>(`/library/${id}`),
  updateFile: (id: number, values: { favorite?: boolean; notes?: string }) =>
    request<{ ok: true }>(`/library/${id}`, { method: 'PATCH', ...jsonBody(values) }),
  favorite: (id: number, value: boolean) =>
    request<{ ok: true }>(`/library/${id}/favorite`, { method: 'POST', ...jsonBody({ value }) }),
  setLabel: (
    id: number,
    dimension: 'instrument' | 'role',
    value: string,
    options?: { clear?: boolean },
  ) =>
    request<FileDetails>(`/library/${id}/labels`, {
      method: 'POST',
      ...jsonBody({ dimension, value, clear: options?.clear ?? false }),
    }),
  setTrackLabel: (
    fileId: number,
    sequenceIndex: number,
    trackIndex: number,
    dimension: 'instrument' | 'role',
    value: string,
    options?: { clear?: boolean },
  ) =>
    request<FileDetails>(
      `/library/${fileId}/tracks/${sequenceIndex}/${trackIndex}/labels`,
      {
        method: 'POST',
        ...jsonBody({ dimension, value, clear: options?.clear ?? false }),
      },
    ),
  addTag: (fileId: number, name: string) =>
    request<{ tag: Tag }>(`/library/${fileId}/tags`, { method: 'POST', ...jsonBody({ name }) }),
  removeTag: (fileId: number, tagId: number) =>
    request<{ ok: true }>(`/library/${fileId}/tags/${tagId}`, { method: 'DELETE' }),
  addToCollection: (fileId: number, collectionId: number) =>
    request<{ added: number }>(`/library/${fileId}/collections`, {
      method: 'POST',
      ...jsonBody({ collection_id: collectionId }),
    }),
  removeFromCollection: (fileId: number, collectionId: number) =>
    request<{ removed: number }>(`/library/${fileId}/collections/${collectionId}`, {
      method: 'DELETE',
    }),
  createCollection: (name: string) =>
    request<{ collection: Collection }>('/collections', { method: 'POST', ...jsonBody({ name }) }),
  collections: () => request<{ collections: Collection[] }>('/collections'),
  addCollectionFiles: (collectionId: number, fileIds: number[]) =>
    request<{ added: number }>(`/collections/${collectionId}/files`, {
      method: 'POST',
      ...jsonBody({ file_ids: fileIds }),
    }),
  bulk: (payload: Record<string, unknown>) =>
    request<{ updated: number }>('/library/bulk', { method: 'POST', ...jsonBody(payload) }),
  folders: () =>
    request<{ folders: FolderRow[]; sources: Bootstrap['sources']; truncated: boolean }>('/folders'),
  scanStatus: () => request<ScanStatus>('/scan/status'),
  scanOptions: () =>
    request<{
      sources: Bootstrap['sources'];
      excludes: Bootstrap['excludes'];
      settings: Record<string, string>;
      last_scan: ScanStatus | null;
      drives: Drive[];
    }>('/scan/options'),
  startScan: (payload: { source_ids: number[]; mode: string; intensity: string; workers?: number }) =>
    request<{ scan: ScanStatus }>('/scan/start', { method: 'POST', ...jsonBody(payload) }),
  pauseScan: () => request<ScanStatus>('/scan/pause', { method: 'POST', ...jsonBody({}) }),
  resumeScan: () => request<ScanStatus>('/scan/resume', { method: 'POST', ...jsonBody({}) }),
  cancelScan: () => request<ScanStatus>('/scan/cancel', { method: 'POST', ...jsonBody({}) }),
  scanIssues: (scanId?: number | null) =>
    request<{ issues: ScanIssue[] }>(
      `/scan/issues${scanId ? `?scan_id=${scanId}&limit=200` : '?limit=200'}`,
    ),
  updateSource: (id: number, values: { enabled?: boolean; optional?: boolean; label?: string }) =>
    request<{ source: Bootstrap['sources'][number] }>(`/sources/${id}`, {
      method: 'PATCH',
      ...jsonBody(values),
    }),
  addSource: (path: string, label?: string) =>
    request<{ source: Bootstrap['sources'][number] }>('/sources', {
      method: 'POST',
      ...jsonBody({ path, label, optional: true, enabled: true }),
    }),
  addExclude: (path: string) =>
    request<{ exclude: Bootstrap['excludes'][number] }>('/excludes', {
      method: 'POST',
      ...jsonBody({ path }),
    }),
  removeExclude: (id: number) =>
    request<{ ok: true }>(`/excludes/${id}`, { method: 'DELETE' }),
  updateSettings: (values: Record<string, string>) =>
    request<{ settings: Record<string, string> }>('/settings', {
      method: 'PATCH',
      ...jsonBody(values),
    }),
  reveal: (id: number) =>
    request<{ ok: true }>(`/library/${id}/reveal`, { method: 'POST', ...jsonBody({}) }),
  exportFiles: (fileIds: number[], destination: string) =>
    request<{
      destination: string;
      copied: number;
      failed: number;
      results: Array<{ file_id: number; ok: boolean; destination?: string; error?: string }>;
    }>('/files/export', { method: 'POST', ...jsonBody({ file_ids: fileIds, destination }) }),
  rebuild: (payload: { source_ids?: number[]; intensity?: string } = {}) =>
    request<{ scan: ScanStatus; message: string }>('/rebuild', {
      method: 'POST',
      ...jsonBody(payload),
    }),
  quitApp: () => request<{ ok: true }>('/app/quit', { method: 'POST', ...jsonBody({}) }),
  duplicates: (kind: 'exact' | 'similar') =>
    request<{ kind: string; group_count: number; groups: Array<Record<string, unknown> & { members: unknown[] }> }>(
      `/duplicates?kind=${kind}`,
    ),
};

export const rawFileUrl = (id: number) => `${BASE}/library/${id}/raw`;
export const downloadFileUrl = (id: number) => `${BASE}/library/${id}/download`;
export const backupUrl = `${BASE}/db/backup`;
