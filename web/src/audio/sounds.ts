/**
 * Preview sound palette.
 *
 * One place that owns three things the rest of the app used to scatter:
 *   1. the named sounds the user can pick,
 *   2. how a classification (category + role, or the file's category) maps to one,
 *   3. the General MIDI program each sound stands for when a hardware device is
 *      the output.
 *
 * Precedence, highest first (see resolveTrackSound):
 *   explicit user choice  →  channel 10 percussion  →  the track's effective
 *   category/role  →  the file's effective category when the track is Unknown or
 *   Mixed arrangement  →  the plain fallback.
 *
 * Headroom rule: every recipe keeps peakScale at or below 1.0, where 1.0 is the
 * level the synth already used (velocity * 0.07). No sound here is allowed to be
 * louder than the existing behaviour; sustained voices are quieter on purpose.
 */

export type SoundId =
  | 'auto'
  | 'default'
  | 'drum-kit'
  | 'piano'
  | 'electric-piano'
  | 'bass'
  | 'pluck'
  | 'strings'
  | 'brass'
  | 'synth-lead'
  | 'synth-pad';

export interface SoundRecipe {
  /** Primary oscillator waveform, or null for the percussion kit. */
  waveform: OscillatorType | null;
  /** Lowpass cutoff in Hz. */
  cutoff: number;
  /** Lowpass resonance. */
  q: number;
  /** Seconds from note-on to peak. */
  attack: number;
  /** Seconds of tail after the note's end. */
  release: number;
  /** Fraction of the peak held until the release starts. */
  sustain: number;
  /** Optional early fall (hammer/pluck decay) measured from the attack. */
  decay?: { fraction: number; seconds: number };
  /** Multiplier on the existing velocity→peak scale; must not exceed 1. */
  peakScale: number;
  /** Bass glide: start the oscillator an octave down and bend up. */
  subJump?: boolean;
  /** Extra detuned oscillator for width or bite. */
  detune?: { waveform: OscillatorType; cents: number; gain: number };
  /** Extra oscillator at a frequency ratio, for bell-like partials. */
  harmonic?: { ratio: number; gain: number };
  /** Rendered with the pitched percussion kit instead of a tone. */
  drum?: boolean;
}

export interface SoundDefinition {
  id: SoundId;
  /** Shown in the picker and the track chip. */
  label: string;
  /** One honest line about what the sound is standing in for. */
  hint: string;
  /** GM program for MIDI hardware output; null = leave the file's own program. */
  gmProgram: number | null;
  recipe: SoundRecipe;
}

/** Categories that carry no opinion about timbre, so the file label may decide. */
const UNSPECIFIED: readonly string[] = ['Unknown', 'Mixed arrangement', ''];

const RECIPES: Record<Exclude<SoundId, 'auto'>, SoundDefinition> = {
  default: {
    id: 'default',
    label: 'Soft default',
    hint: 'Plain rounded tone used when nothing else fits.',
    gmProgram: null,
    recipe: {
      waveform: 'triangle', cutoff: 4800, q: 0.4, attack: 0.012, release: 0.12,
      sustain: 0.72, peakScale: 1,
    },
  },
  'drum-kit': {
    id: 'drum-kit',
    label: 'Drum kit',
    hint: 'Pitched percussion map: kick, snare, hats, toms and cymbals.',
    gmProgram: null,
    recipe: {
      waveform: null, cutoff: 4800, q: 0.4, attack: 0.004, release: 0.1,
      sustain: 0.5, peakScale: 1, drum: true,
    },
  },
  piano: {
    id: 'piano',
    label: 'Grand piano',
    hint: 'Bright attack with a short hammer decay.',
    gmProgram: 0,
    recipe: {
      waveform: 'triangle', cutoff: 4800, q: 0.4, attack: 0.006, release: 0.18,
      sustain: 0.5, decay: { fraction: 0.62, seconds: 0.3 }, peakScale: 0.95,
      harmonic: { ratio: 2, gain: 0.35 },
    },
  },
  'electric-piano': {
    id: 'electric-piano',
    label: 'Electric piano',
    hint: 'Softer, rounder keys with a gentle top partial.',
    gmProgram: 4,
    recipe: {
      waveform: 'sine', cutoff: 3000, q: 0.4, attack: 0.008, release: 0.2,
      sustain: 0.45, decay: { fraction: 0.7, seconds: 0.25 }, peakScale: 0.9,
      harmonic: { ratio: 2, gain: 0.22 },
    },
  },
  bass: {
    id: 'bass',
    label: 'Bass',
    hint: 'Sine sub with a low cutoff and a small octave bend in.',
    gmProgram: 33,
    recipe: {
      waveform: 'sine', cutoff: 900, q: 0.4, attack: 0.01, release: 0.1,
      sustain: 0.8, peakScale: 1, subJump: true,
    },
  },
  pluck: {
    id: 'pluck',
    label: 'Plucked string',
    hint: 'Guitar or harp stand-in: immediate attack, fast fall.',
    gmProgram: 24,
    recipe: {
      waveform: 'triangle', cutoff: 3200, q: 0.4, attack: 0.004, release: 0.08,
      sustain: 0.25, decay: { fraction: 0.25, seconds: 0.12 }, peakScale: 1,
    },
  },
  strings: {
    id: 'strings',
    label: 'Strings',
    hint: 'Two detuned saws with a slow bow attack.',
    gmProgram: 48,
    recipe: {
      waveform: 'sawtooth', cutoff: 4800, q: 0.4, attack: 0.12, release: 0.32,
      sustain: 0.85, peakScale: 1, detune: { waveform: 'sawtooth', cents: -7, gain: 0.4 },
    },
  },
  brass: {
    id: 'brass',
    label: 'Brass',
    hint: 'Square lead with a narrow octave partial.',
    gmProgram: 62,
    recipe: {
      waveform: 'square', cutoff: 4800, q: 0.4, attack: 0.02, release: 0.14,
      sustain: 0.8, peakScale: 1, harmonic: { ratio: 2, gain: 0.18 },
    },
  },
  'synth-lead': {
    id: 'synth-lead',
    label: 'Synth lead',
    hint: 'Saw with a square detune for width and bite.',
    gmProgram: 80,
    recipe: {
      waveform: 'sawtooth', cutoff: 4800, q: 0.4, attack: 0.008, release: 0.12,
      sustain: 0.75, peakScale: 1, detune: { waveform: 'square', cents: 8, gain: 0.28 },
    },
  },
  'synth-pad': {
    id: 'synth-pad',
    label: 'Synth pad',
    hint: 'Slow, quiet sustained bed — the pad level trim keeps it the softest voice.',
    gmProgram: 89,
    recipe: {
      waveform: 'sawtooth', cutoff: 2600, q: 0.4, attack: 0.12, release: 0.32,
      sustain: 0.9, peakScale: 1, detune: { waveform: 'square', cents: 8, gain: 0.28 },
    },
  },
};

/** Everything the module knows, including the two non-selectable ids. */
export const SOUNDS: Record<SoundId, SoundDefinition | null> = {
  auto: null,
  ...RECIPES,
};

/**
 * Own-property lookup only. A plain `SOUNDS[id]` on an untrusted id would hand
 * back Object.prototype members (`constructor`, `__proto__`) instead of nothing,
 * so every accessor below goes through this.
 */
function definition(id: string): SoundDefinition | null {
  return Object.prototype.hasOwnProperty.call(SOUNDS, id)
    ? SOUNDS[id as SoundId]
    : null;
}

/** The ids that appear in the picker: Auto plus the nine real sounds. */
export const SELECTABLE_SOUNDS: readonly SoundId[] = [
  'auto', 'drum-kit', 'piano', 'electric-piano', 'bass', 'pluck', 'strings',
  'brass', 'synth-lead', 'synth-pad',
];

/** Ids that may be stored as an explicit preference. */
export const STORED_SOUNDS: readonly SoundId[] = SELECTABLE_SOUNDS.filter((id) => id !== 'auto');

export function isSoundId(value: unknown): value is SoundId {
  return typeof value === 'string' && Object.prototype.hasOwnProperty.call(SOUNDS, value);
}

export function soundDefinition(id: string): SoundDefinition | null {
  return definition(id);
}

export function soundLabel(id: string): string {
  return definition(id)?.label ?? 'Auto';
}

export function soundHint(id: string): string {
  return definition(id)?.hint
    ?? 'Follow the category and role, or the file category when the track has none.';
}

export function soundRecipe(id: string): SoundRecipe {
  return definition(id)?.recipe ?? RECIPES.default.recipe;
}

/**
 * GM program for MIDI hardware output. 'auto', 'default' and the kit leave the
 * file's own program alone: the kit is played on the percussion channel where a
 * melodic program number means nothing, and 'default' is the preview synth's
 * neutral tone with no honest GM equivalent.
 */
export function gmProgramFor(id: SoundId, fallback: number | null): number | null {
  if (id === 'auto' || id === 'default' || id === 'drum-kit') return fallback;
  return definition(id)?.gmProgram ?? fallback;
}

/** Direct category/role mapping. Returns null when the pair says nothing. */
export function soundFromLabels(instrument: string, role: string): SoundId | null {
  if (instrument === 'Drums/percussion' || role.startsWith('Drum')) return 'drum-kit';
  if (instrument === 'Bass') return 'bass';
  if (instrument === 'Guitar/plucked') return 'pluck';
  if (instrument === 'Strings') return 'strings';
  if (instrument === 'Brass/woodwinds') return 'brass';
  if (instrument === 'Synth') return role === 'Pad/sustained harmony' ? 'synth-pad' : 'synth-lead';
  if (instrument === 'Piano/keys') {
    return role === 'Pad/sustained harmony' ? 'electric-piano' : 'piano';
  }
  return null;
}

export interface SoundInput {
  /** The user's explicit pick for this track, or 'auto' / null when unset. */
  override?: SoundId | null;
  instrument: string;
  role: string;
  channel: number;
  /** 'user' when the track's own category was corrected by hand. */
  instrumentSource?: string | null;
  /** The file's effective category, and whether the user corrected it. */
  fileInstrument?: string | null;
  fileInstrumentSource?: string | null;
}

/**
 * Resolve the sound one track should play with. Pure and synchronous so the
 * library row, the track chip and the audio engine always agree.
 *
 * The order is a statement about trust, not about scope. A hand-made choice
 * beats a guessed one at any level, so correcting a misread file category
 * reaches parts whose automatic label was wrong too — which is precisely the
 * case that made the preview sound stuck. Between two automatic labels the
 * track's own wins, because it describes the notes rather than the average.
 */
export function resolveTrackSound({
  override,
  instrument,
  role,
  channel,
  instrumentSource,
  fileInstrument,
  fileInstrumentSource,
}: SoundInput): SoundId {
  if (override && override !== 'auto' && isSoundId(override)) return override;
  const fromTrack = soundFromLabels(instrument, role);
  const trackSaysNothing = UNSPECIFIED.includes(instrument);
  // Channel 9 is the percussion convention, and with nothing better to go on it
  // wins. A category the reviewer corrected by hand is better: a kit sample
  // mapped onto channel 9 as a piano part should sound like a piano, so the
  // convention never overrides an explicit human statement about the track.
  if (channel === 9 && !(fromTrack && instrumentSource === 'user')) return 'drum-kit';
  // A hand-corrected track label is the most specific human statement available.
  if (fromTrack && instrumentSource === 'user') return fromTrack;
  if (fileInstrument && !UNSPECIFIED.includes(fileInstrument)) {
    const fromFile = soundFromLabels(fileInstrument, trackSaysNothing ? (role === 'Unknown' ? '' : role) : role);
    // Use the file's category when the human corrected it, or when the track
    // itself has no opinion. An uncorrected track label still wins otherwise.
    if (fromFile && (fileInstrumentSource === 'user' || trackSaysNothing)) return fromFile;
  }
  if (fromTrack) return fromTrack;
  // A channel-9 track the reviewer set to something the table cannot voice
  // still plays the kit; the correction only redirects a family we recognise.
  if (channel === 9) return 'drum-kit';
  return 'default';
}

/**
 * Stable fingerprint of everything the audio build reads per track. The engine
 * rebuilds when this changes and only when it changes, so a correction that
 * alters no voice costs nothing, and the optimistic update plus the server
 * response collapse into a single rebuild instead of two.
 *
 * It has to cover more than the sound id. The synth path also branches on the
 * role (a pad part gets a slower attack and a level trim) and on the channel
 * (percussion uses the kit voice), so a role-only correction is an audible
 * correction and must not be treated as "nothing changed".
 */
export function soundSignature(
  tracks: Array<{ key: string; sound: SoundId; role: string; channel: number }>,
): string {
  return tracks.map((track) => `${track.key}=${track.sound}|${track.role}|${track.channel}`).join(',');
}
