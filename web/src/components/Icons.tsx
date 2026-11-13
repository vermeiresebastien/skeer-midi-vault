import type { SVGProps } from 'react';

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 16, ...props }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
    ...props,
  };
}

export const SearchIcon = (p: IconProps) => (
  <svg {...base(p)}><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.2 4.2" /></svg>
);
export const FilterIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M3.5 5h17M6.5 12h11M9.5 19h5" /></svg>
);
export const ScanIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16" /><path d="M7 12h10" /></svg>
);
export const SettingsIcon = (p: IconProps) => (
  <svg {...base(p)}><circle cx="12" cy="12" r="3.1" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-1.84 1.84-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V20h-2.6v-.09a1.7 1.7 0 0 0-1.03-1.56 1.7 1.7 0 0 0-1.88.34l-.06.06L5.58 16.9l.06-.06A1.7 1.7 0 0 0 5.98 15a1.7 1.7 0 0 0-1.56-1.03H4.3v-2.6h.12A1.7 1.7 0 0 0 5.98 10a1.7 1.7 0 0 0-.34-1.88l-.06-.06 1.84-1.84.06.06A1.7 1.7 0 0 0 9.36 6a1.7 1.7 0 0 0 1.03-1.56V4.3h2.6v.14A1.7 1.7 0 0 0 14.02 6a1.7 1.7 0 0 0 1.88-.34l.06-.06 1.84 1.84-.06.06A1.7 1.7 0 0 0 17.4 9.4a1.7 1.7 0 0 0 1.56 1.03h.14v2.6h-.14A1.7 1.7 0 0 0 17.4 14Z" /></svg>
);
export const PlayIcon = (p: IconProps) => (
  <svg {...base({ fill: 'currentColor', stroke: 'none', ...p })}><path d="M8 5.8v12.4c0 .9 1 1.4 1.7.9l9-6.2a1.1 1.1 0 0 0 0-1.8l-9-6.2A1.1 1.1 0 0 0 8 5.8Z" /></svg>
);
export const PauseIcon = (p: IconProps) => (
  <svg {...base({ fill: 'currentColor', stroke: 'none', ...p })}><rect x="7" y="5" width="3.5" height="14" rx="1" /><rect x="13.5" y="5" width="3.5" height="14" rx="1" /></svg>
);
export const StopIcon = (p: IconProps) => (
  <svg {...base({ fill: 'currentColor', stroke: 'none', ...p })}><rect x="6.5" y="6.5" width="11" height="11" rx="1.4" /></svg>
);
export const LoopIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M4.8 9.2A6.5 6.5 0 0 1 17 6.4l2 2M19.2 14.8A6.5 6.5 0 0 1 7 17.6l-2-2" /><path d="M19 4.5v3.9h-3.9M5 19.5v-3.9h3.9" /></svg>
);
export const ChevronDown = (p: IconProps) => (
  <svg {...base(p)}><path d="m6 9 6 6 6-6" /></svg>
);
export const ChevronRight = (p: IconProps) => (
  <svg {...base(p)}><path d="m9 6 6 6-6 6" /></svg>
);
export const ChevronLeft = (p: IconProps) => (
  <svg {...base(p)}><path d="m15 6-6 6 6 6" /></svg>
);
export const CloseIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="m6 6 12 12M18 6 6 18" /></svg>
);
export const StarIcon = ({ filled, ...p }: IconProps & { filled?: boolean }) => (
  <svg {...base({ ...p, fill: filled ? 'currentColor' : 'none' })}><path d="m12 3.8 2.46 5 5.54.8-4 3.9.94 5.5L12 16.4 7.06 19l.94-5.5-4-3.9 5.54-.8Z" /></svg>
);
export const FolderIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M3.5 7.2A2.2 2.2 0 0 1 5.7 5h3l2 2h7.6a2.2 2.2 0 0 1 2.2 2.2v8.6a2.2 2.2 0 0 1-2.2 2.2H5.7a2.2 2.2 0 0 1-2.2-2.2Z" /></svg>
);
export const FileIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M6 3.8h7.2L18 8.6v11.6H6Z" /><path d="M13 3.8V9h5M9 13h6M9 16.4h4.5" /></svg>
);
export const PlusIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 5v14M5 12h14" /></svg>
);
export const TagIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="m4 12.4 8.4-8.4 7.6.2.2 7.6L12 20.2 4 12.4Z" /><circle cx="15.5" cy="8.5" r="1.2" /></svg>
);
export const CollectionIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M4 6.2h7.4l2 2H20v9.6a2 2 0 0 1-2 2H4Z" /><path d="M4 10.6h16" /></svg>
);
export const RevealIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M4 12s2.8-5 8-5 8 5 8 5-2.8 5-8 5-8-5-8-5Z" /><circle cx="12" cy="12" r="2.1" /></svg>
);
export const ExportIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 3v11M8 10l4 4 4-4M5 16v3.2A1.8 1.8 0 0 0 6.8 21h10.4a1.8 1.8 0 0 0 1.8-1.8V16" /></svg>
);
export const NoteIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M9 18V5.8l9-2v11.4" /><circle cx="6.8" cy="18" r="2.4" /><circle cx="15.8" cy="15.2" r="2.4" /></svg>
);
export const WarningIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 4 21 20H3Z" /><path d="M12 9v5M12 17.2v.1" /></svg>
);
export const CheckIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="m4.5 12.5 5 5 10-11" /></svg>
);
export const InfoIcon = (p: IconProps) => (
  <svg {...base(p)}><circle cx="12" cy="12" r="9" /><path d="M12 10.5V17M12 7.3v.1" /></svg>
);
export const MidiIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M5 4h14v16H5Z" /><path d="M8 4v8M11 4v8M14 4v8M17 4v8M7.2 12h9.6M8 20v-4M16 20v-4" /></svg>
);
export const SparkIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 3.5 13.6 9l5.4 1.6-5.4 1.6L12 17.6l-1.6-5.4L5 10.6 10.4 9ZM18.2 15.4l.7 2.2 2.1.7-2.1.7-.7 2.2-.7-2.2-2.1-.7 2.1-.7Z" /></svg>
);
export const DragIcon = (p: IconProps) => (
  <svg {...base(p)}><circle cx="8" cy="7" r=".9" /><circle cx="16" cy="7" r=".9" /><circle cx="8" cy="12" r=".9" /><circle cx="16" cy="12" r=".9" /><circle cx="8" cy="17" r=".9" /><circle cx="16" cy="17" r=".9" /></svg>
);
export const MoreIcon = (p: IconProps) => (
  <svg {...base(p)}><circle cx="5" cy="12" r="1.2" fill="currentColor" stroke="none" /><circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none" /><circle cx="19" cy="12" r="1.2" fill="currentColor" stroke="none" /></svg>
);
export const CopyIcon = (p: IconProps) => (
  <svg {...base(p)}><rect x="8" y="8" width="11" height="12" rx="1.8" /><path d="M16 8V6.2A2.2 2.2 0 0 0 13.8 4H6.2A2.2 2.2 0 0 0 4 6.2v9.6A2.2 2.2 0 0 0 6.2 18H8" /></svg>
);
