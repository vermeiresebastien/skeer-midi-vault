export const INSTRUMENT_COLORS: Record<string, string> = {
  'Drums/percussion': '#B55239',
  Bass: '#4E6672',
  'Piano/keys': '#B8862B',
  'Guitar/plucked': '#7B5A3A',
  Strings: '#6A7A55',
  'Brass/woodwinds': '#A57320',
  Synth: '#61747A',
  'Mixed arrangement': '#292821',
  Unknown: '#9A9488',
};

export function instrumentColor(category: string | null | undefined): string {
  return INSTRUMENT_COLORS[category || 'Unknown'] || INSTRUMENT_COLORS.Unknown;
}

export const TRACK_COLORS = [
  '#FF6500',
  '#292821',
  '#2E7C78',
  '#B8862B',
  '#7A4D5E',
  '#6A7A55',
  '#61747A',
  '#B55239',
];

export function trackColor(index: number): string {
  return TRACK_COLORS[index % TRACK_COLORS.length];
}

export const ROLE_LABELS: Record<string, string> = {
  'Drum groove': 'Drum groove',
  'Drum fill': 'Drum fill',
  Bassline: 'Bassline',
  'Chord progression': 'Chord progression',
  'Lead/melody': 'Lead / melody',
  Arpeggio: 'Arpeggio',
  'Pad/sustained harmony': 'Pad / harmony',
  'Complete song or multi-part arrangement': 'Multi-part arrangement',
  'Exercise or technical pattern': 'Exercise / pattern',
  Unknown: 'Unknown',
};

export function roleLabel(role: string | null | undefined): string {
  return ROLE_LABELS[role || 'Unknown'] || role || 'Unknown';
}

export function familyLabel(family: string | null | undefined): string {
  if (!family) return 'Unknown';
  if (family === 'Brass/woodwinds') return 'Brass / woodwinds';
  if (family === 'Piano/keys') return 'Piano / keys';
  if (family === 'Guitar/plucked') return 'Guitar / plucked';
  return family;
}
