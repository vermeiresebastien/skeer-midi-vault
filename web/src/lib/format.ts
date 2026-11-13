export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '—';
  const whole = Math.max(0, seconds);
  const minutes = Math.floor(whole / 60);
  const rest = whole - minutes * 60;
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    return `${hours}:${String(minutes % 60).padStart(2, '0')}:${String(Math.floor(rest)).padStart(2, '0')}`;
  }
  return `${minutes}:${rest.toFixed(1).padStart(4, '0')}`;
}

export function formatDurationShort(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '—';
  const whole = Math.max(0, Math.round(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

export function formatTime(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '0:00.0';
  const whole = Math.max(0, seconds);
  const min = Math.floor(whole / 60);
  const sec = whole - min * 60;
  return `${min}:${sec.toFixed(1).padStart(4, '0')}`;
}

export function formatBpm(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return Math.abs(value - Math.round(value)) < 0.05
    ? String(Math.round(value))
    : value.toFixed(1);
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes)) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

export function formatRelativeTime(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  const seconds = (Date.now() - date.getTime()) / 1000;
  if (seconds < 90) return 'just now';
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  if (seconds < 86400 * 7) return `${Math.round(seconds / 86400)} d ago`;
  return date.toLocaleDateString();
}

export function formatPercent(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${Math.round(value * 100)}%`;
}

export function confidenceLabel(value: number | null | undefined): string {
  if (value == null) return 'unknown';
  if (value >= 0.78) return 'high confidence';
  if (value >= 0.55) return 'medium confidence';
  return 'low confidence';
}

export function noteName(pitch: number): string {
  const names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
  const value = Math.max(0, Math.min(127, Math.round(pitch)));
  return `${names[value % 12]}${Math.floor(value / 12) - 1}`;
}

export function keyLabel(key: string | null | undefined, source?: string | null): string {
  if (!key) return '—';
  if (source === 'estimated') return `${key} estimated`;
  if (source === 'embedded') return key;
  return key;
}

export function invalidateFileExtension(filename: string): string {
  const index = filename.lastIndexOf('.');
  return index > 0 ? filename.slice(0, index) : filename;
}

export function basename(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() || path;
}

export function parentPath(path: string): string {
  const parts = path.split(/[\\/]/);
  parts.pop();
  return parts.join('\\') || path;
}
