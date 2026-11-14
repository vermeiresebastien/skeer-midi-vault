/**
 * Per-track preview sound preferences.
 *
 * These are audition taste, not library data: they live in the browser, not in
 * SQLite, so they never touch the index and are not part of a backup. They are
 * keyed by file path rather than database id because an index rebuild can hand
 * out new ids, and an id-keyed map would silently apply one file's preference
 * to an unrelated one. Moving or renaming a source file orphans its
 * preferences — documented in docs/limitations.md.
 *
 * Shape: { [path]: { [`${sequenceIndex}:${trackIndex}`]: SoundId } }
 */
import { STORED_SOUNDS, isSoundId, type SoundId } from './audio/sounds';

const STORAGE_KEY = 'skeer.midi-vault.trackSounds.v1';

export type SoundPreferences = Record<string, Record<string, SoundId>>;

/** Same `${sequenceIndex}:${trackIndex}` identity the mute/solo state uses. */
export function trackSoundKey(sequenceIndex: number, trackIndex: number): string {
  return `${Math.trunc(sequenceIndex)}:${Math.trunc(trackIndex)}`;
}

function isStorableSound(value: unknown): value is SoundId {
  return isSoundId(value) && STORED_SOUNDS.includes(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Read and revalidate everything. Anything unexpected — a hand-edited store,
 * an id from an older palette, a wrong shape — is dropped rather than trusted,
 * so a bad entry can never reach the audio graph.
 */
export function loadSoundPreferences(): SoundPreferences {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return {};
    const parsed: unknown = JSON.parse(stored);
    if (!isRecord(parsed)) return {};
    const clean: SoundPreferences = {};
    for (const [path, entry] of Object.entries(parsed)) {
      if (!path || !isRecord(entry)) continue;
      const tracks: Record<string, SoundId> = {};
      for (const [key, sound] of Object.entries(entry)) {
        if (isStorableSound(sound)) tracks[key] = sound;
      }
      if (Object.keys(tracks).length > 0) clean[path] = tracks;
    }
    return clean;
  } catch {
    return {};
  }
}

/** False means the write failed (private browsing or quota); the session still works. */
export function saveSoundPreferences(preferences: SoundPreferences): boolean {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
    return true;
  } catch {
    return false;
  }
}

/** Explicit pick for one track, or null when it should follow the analysis. */
export function soundOverrideFor(
  preferences: SoundPreferences,
  path: string | null | undefined,
  sequenceIndex: number,
  trackIndex: number,
): SoundId | null {
  if (!path) return null;
  const sound = preferences[path]?.[trackSoundKey(sequenceIndex, trackIndex)];
  return isStorableSound(sound) ? sound : null;
}

/** Overrides for the whole sequence, keyed by track_index for the engine. */
export function sequenceOverrides(
  preferences: SoundPreferences,
  path: string | null | undefined,
  sequenceIndex: number,
): Map<number, SoundId> {
  const found = new Map<number, SoundId>();
  if (!path) return found;
  for (const [key, sound] of Object.entries(preferences[path] || {})) {
    const [seq, track] = key.split(':');
    if (Number.parseInt(seq, 10) !== sequenceIndex) continue;
    const index = Number.parseInt(track, 10);
    if (Number.isFinite(index) && isStorableSound(sound)) found.set(index, sound);
  }
  return found;
}

/**
 * Immutably set or clear one track's pick. 'auto' and 'default' clear it, so
 * "reset to auto" and "no preference" cannot drift apart, and empty file maps
 * are removed instead of accumulating.
 */
export function withSoundOverride(
  preferences: SoundPreferences,
  path: string,
  sequenceIndex: number,
  trackIndex: number,
  sound: SoundId | null,
): SoundPreferences {
  const key = trackSoundKey(sequenceIndex, trackIndex);
  const next: SoundPreferences = { ...preferences };
  const tracks = { ...(next[path] || {}) };
  if (sound && isStorableSound(sound)) tracks[key] = sound;
  else delete tracks[key];
  if (Object.keys(tracks).length > 0) next[path] = tracks;
  else delete next[path];
  return next;
}

/** The same pick for every listed track — the "sound for all tracks" action. */
export function withSoundOverrides(
  preferences: SoundPreferences,
  path: string,
  sequenceIndex: number,
  trackIndexes: number[],
  sound: SoundId | null,
): SoundPreferences {
  return trackIndexes.reduce(
    (current, trackIndex) => withSoundOverride(current, path, sequenceIndex, trackIndex, sound),
    preferences,
  );
}

export function countSoundOverrides(preferences: SoundPreferences): number {
  return Object.values(preferences)
    .reduce((total, tracks) => total + Object.keys(tracks).length, 0);
}
