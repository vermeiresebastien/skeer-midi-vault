import { createContext, useContext } from 'react';

export type Skin = 'clean' | 'tactile';
export type TileFinish = 'smooth' | 'plastic' | 'rubber';
export type KnobFinish = 'flat' | 'matte' | 'metal';
export type MeterColor = 'accent' | 'orange' | 'green' | 'amber';

export interface Appearance {
  skin: Skin;
  accent: string;
  meterColor: MeterColor;
  tileFinish: TileFinish;
  knobFinish: KnobFinish;
  texture: number;
  panelContrast: number;
  borderStrength: number;
  interfaceScale: number;
  reduceMotion: boolean;
}

export const ACCENTS = [
  { value: '#FF6500', label: 'SKEER Orange' },
  { value: '#C0842E', label: 'Amber' },
  { value: '#2E7C78', label: 'Deep Teal' },
  { value: '#A3463D', label: 'Oxide' },
];

export const defaultAppearance = (): Appearance => ({
  skin: 'clean',
  accent: '#FF6500',
  meterColor: 'accent',
  tileFinish: 'smooth',
  knobFinish: 'flat',
  texture: 22,
  panelContrast: 35,
  borderStrength: 28,
  interfaceScale: 100,
  reduceMotion: false,
});

const STORAGE_KEY = 'skeer.midi-vault.appearance.v1';

export function loadAppearance(): Appearance {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return defaultAppearance();
    const parsed = JSON.parse(stored) as Partial<Appearance>;
    return { ...defaultAppearance(), ...parsed };
  } catch {
    return defaultAppearance();
  }
}

export function saveAppearance(appearance: Appearance): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(appearance));
  } catch {
    // Private browsing or storage pressure: appearance still applies for this session.
  }
}

function parseHex(hex: string): [number, number, number] {
  const clean = hex.replace('#', '');
  if (clean.length !== 6) return [255, 101, 0];
  return [
    Number.parseInt(clean.slice(0, 2), 16),
    Number.parseInt(clean.slice(2, 4), 16),
    Number.parseInt(clean.slice(4, 6), 16),
  ];
}

function mix(a: string, b: string, amount: number): string {
  const [ar, ag, ab] = parseHex(a);
  const [br, bg, bb] = parseHex(b);
  const ratio = Math.max(0, Math.min(1, amount));
  const value = (x: number, y: number) => Math.round(x * (1 - ratio) + y * ratio);
  return `rgb(${value(ar, br)}, ${value(ag, bg)}, ${value(ab, bb)})`;
}

function rgba(hex: string, alpha: number): string {
  const [r, g, b] = parseHex(hex);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export function meterColor(appearance: Appearance): string {
  switch (appearance.meterColor) {
    case 'green':
      return '#00A85A';
    case 'amber':
      return '#C0842E';
    case 'orange':
      return '#FF6500';
    case 'accent':
    default:
      return appearance.accent;
  }
}

export function applyAppearance(appearance: Appearance): void {
  const root = document.documentElement;
  root.dataset.skin = appearance.skin;
  root.dataset.reduceMotion = appearance.reduceMotion ? 'true' : 'false';
  root.dataset.tileFinish = appearance.tileFinish;
  root.dataset.knobFinish = appearance.knobFinish;
  const contrast = Math.max(0, Math.min(100, appearance.panelContrast));
  const texture = Math.max(0, Math.min(100, appearance.texture));
  const border = Math.max(0, Math.min(100, appearance.borderStrength));
  root.style.setProperty('--accent', appearance.accent);
  root.style.setProperty('--accent-strong', mix(appearance.accent, '#000000', 0.16));
  root.style.setProperty('--accent-soft', rgba(appearance.accent, 0.12));
  root.style.setProperty('--accent-faint', rgba(appearance.accent, 0.055));
  root.style.setProperty('--accent-line', rgba(appearance.accent, 0.34));
  root.style.setProperty('--meter', meterColor(appearance));
  root.style.setProperty('--texture-opacity', String(texture / 100));
  root.style.setProperty('--panel-contrast', String(contrast / 100));
  root.style.setProperty('--border-alpha', String(0.18 + border / 100 * 0.42));
  const scale = appearance.interfaceScale / 100;
  root.style.setProperty('--ui-scale', String(scale));
  root.style.setProperty('--ui-inverse', String(1 / scale));
  root.style.setProperty('--paper', mix('#FCFAF6', '#E7E2D8', contrast / 100 * 0.16));
  root.style.setProperty('--stone', mix('#E7E2D8', '#CFC8BC', contrast / 100 * 0.20));
  root.style.setProperty('--canvas', mix('#F5F2EB', '#E7E2D8', contrast / 100 * 0.07));
  root.style.setProperty('--board', mix('#FCFAF6', '#E7E2D8', contrast / 100 * 0.10));
  root.style.setProperty('--line', rgba('#292821', 0.10 + border / 100 * 0.22));
  root.style.setProperty('--line-strong', rgba('#292821', 0.20 + border / 100 * 0.34));
  root.style.setProperty(
    '--shadow-panel',
    appearance.skin === 'tactile'
      ? '0 1px 0 rgba(255,255,255,.72) inset, 0 1px 2px rgba(41,40,33,.10), 0 10px 24px rgba(73,64,48,.08)'
      : '0 1px 0 rgba(255,255,255,.55) inset, 0 1px 2px rgba(41,40,33,.055)',
  );
  root.style.setProperty(
    '--shadow-float',
    appearance.skin === 'tactile'
      ? '0 18px 58px rgba(58,48,34,.22), 0 2px 6px rgba(58,48,34,.12)'
      : '0 16px 48px rgba(58,48,34,.13), 0 2px 4px rgba(58,48,34,.07)',
  );
  root.style.setProperty('--radius-panel', appearance.skin === 'tactile' ? '8px' : '6px');
  root.style.setProperty('--radius-control', appearance.skin === 'tactile' ? '6px' : '5px');
}

export interface AppearanceContextValue {
  appearance: Appearance;
  setAppearance: (updater: Partial<Appearance> | ((current: Appearance) => Appearance)) => void;
  reset: () => void;
}

export const AppearanceContext = createContext<AppearanceContextValue | null>(null);

export function useAppearance(): AppearanceContextValue {
  const value = useContext(AppearanceContext);
  if (!value) throw new Error('AppearanceContext is missing');
  return value;
}
