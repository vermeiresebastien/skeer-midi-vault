import {
  useEffect,
  useId,
  useRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  type SelectHTMLAttributes,
} from 'react';
import { createPortal } from 'react-dom';
import { CloseIcon, WarningIcon } from './Icons';

export function Button({
  variant = 'secondary',
  size = 'md',
  icon,
  children,
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  icon?: ReactNode;
}) {
  return (
    <button
      {...props}
      className={`btn btn-${variant} btn-${size} ${className}`}
      type={props.type ?? 'button'}
    >
      {icon ? <span className="btn-icon">{icon}</span> : null}
      {children ? <span>{children}</span> : null}
    </button>
  );
}

export function IconButton({
  label,
  active = false,
  children,
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  active?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      {...props}
      type={props.type ?? 'button'}
      className={`icon-btn ${active ? 'is-active' : ''} ${className}`}
      aria-label={label}
      title={label}
    >
      {children}
    </button>
  );
}

export function Badge({
  children,
  tone = 'neutral',
  className = '',
  title,
}: {
  children: ReactNode;
  tone?: 'neutral' | 'orange' | 'green' | 'red' | 'amber' | 'ink';
  className?: string;
  title?: string;
}) {
  return <span className={`badge badge-${tone} ${className}`} title={title}>{children}</span>;
}

export function Field({
  label,
  hint,
  children,
  className = '',
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={`field ${className}`}>
      <span className="field-label">{label}</span>
      {children}
      {hint ? <span className="field-hint">{hint}</span> : null}
    </label>
  );
}

export function Select({
  className = '',
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { children: ReactNode }) {
  return (
    <span className="select-wrap">
      <select {...props} className={`select ${className}`}>{children}</select>
      <span className="select-chevron" aria-hidden="true">⌄</span>
    </span>
  );
}

export function Input({
  className = '',
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`input ${className}`} />;
}

export function RangeField({
  label,
  value,
  min,
  max,
  step = 1,
  suffix,
  onChange,
  disabled,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  suffix?: string;
  onChange: (value: number) => void;
  disabled?: boolean;
}) {
  return (
    <label className={`range-field ${disabled ? 'is-disabled' : ''}`}>
      <span className="range-header">
        <span>{label}</span>
        <span className="mono">{value}{suffix ? <em>{suffix}</em> : null}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  className = '',
}: {
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
  ariaLabel: string;
  className?: string;
}) {
  return (
    <div className={`segmented ${className}`} role="group" aria-label={ariaLabel}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={option.value === value ? 'is-active' : ''}
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  description,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className={`toggle-row ${disabled ? 'is-disabled' : ''}`}>
      <div className="toggle-copy">
        <label htmlFor={id}>{label}</label>
        {description ? <span>{description}</span> : null}
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        className={`switch ${checked ? 'is-on' : ''}`}
        onClick={() => !disabled && onChange(!checked)}
        disabled={disabled}
      >
        <span className="switch-thumb" />
      </button>
    </div>
  );
}

export function Knob({
  value,
  min,
  max,
  step = 1,
  label,
  onChange,
  size = 38,
  disabled = false,
  valueLabel,
  onReset,
  onDragEnd,
}: {
  value: number;
  min: number;
  max: number;
  step?: number;
  label: string;
  onChange: (value: number) => void;
  size?: number;
  disabled?: boolean;
  valueLabel?: string;
  onReset?: () => void;
  onDragEnd?: () => void;
}) {
  const drag = useRef<{ startY: number; startValue: number } | null>(null);
  const range = Math.max(0.0001, max - min);
  const rotation = -135 + ((value - min) / range) * 270;
  const pointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (disabled) return;
    drag.current = { startY: event.clientY, startValue: value };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const pointerMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (!drag.current || disabled) return;
    const sensitivity = event.shiftKey ? 0.0015 : 0.006;
    const delta = (drag.current.startY - event.clientY) * range * sensitivity;
    let next = drag.current.startValue + delta;
    next = Math.round(next / step) * step;
    next = Math.max(min, Math.min(max, next));
    onChange(next);
  };
  const pointerUp = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const wasDragging = drag.current !== null;
    drag.current = null;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // ignore
    }
    if (wasDragging) onDragEnd?.();
  };
  return (
    <div className="knob-field">
      <button
        type="button"
        className="knob"
        style={{ width: size, height: size }}
        role="slider"
        aria-label={label}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={value}
        aria-valuetext={valueLabel || String(value)}
        disabled={disabled}
        onPointerDown={pointerDown}
        onPointerMove={pointerMove}
        onPointerUp={pointerUp}
        onPointerCancel={pointerUp}
        onWheel={(event) => {
          if (disabled) return;
          const direction = event.deltaY < 0 ? 1 : -1;
          const next = Math.max(min, Math.min(max, value + direction * step));
          onChange(next);
        }}
        onKeyDown={(event) => {
          if (disabled) return;
          if (event.key === 'ArrowUp' || event.key === 'ArrowRight') {
            event.preventDefault();
            onChange(Math.min(max, value + step));
          } else if (event.key === 'ArrowDown' || event.key === 'ArrowLeft') {
            event.preventDefault();
            onChange(Math.max(min, value - step));
          } else if (event.key === 'Home') {
            event.preventDefault();
            onChange(min);
          } else if (event.key === 'End') {
            event.preventDefault();
            onChange(max);
          }
        }}
        onDoubleClick={() => {
          if (disabled) return;
          if (onReset) onReset();
        }}
        title={`${label} — drag or scroll`}
      >
        <span className="knob-track" />
        <span
          className="knob-face"
          style={{ transform: `rotate(${rotation}deg)` }}
        >
          <span className="knob-indicator" />
        </span>
      </button>
      <span className="knob-label">{label}</span>
    </div>
  );
}

export function Modal({
  open,
  title,
  eyebrow,
  onClose,
  children,
  footer,
  width = '720px',
  className = '',
}: {
  open: boolean;
  title: string;
  eyebrow?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: string;
  className?: string;
}) {
  useEffect(() => {
    if (!open) return undefined;
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handler);
      document.body.style.overflow = oldOverflow;
    };
  }, [open, onClose]);
  if (!open) return null;
  return createPortal(
    <div className="modal-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section
        className={`modal ${className}`}
        style={{ width }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        <header className="modal-header">
          <div>
            {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
            <h2 id="modal-title">{title}</h2>
          </div>
          <IconButton label="Close" onClick={onClose}><CloseIcon /></IconButton>
        </header>
        <div className="modal-body">{children}</div>
        {footer ? <footer className="modal-footer">{footer}</footer> : null}
      </section>
    </div>,
    document.body,
  );
}

export function Confidence({
  value,
  source,
  compact = false,
}: {
  value: number | null | undefined;
  source?: string;
  compact?: boolean;
}) {
  const percent = value == null ? 0 : Math.max(0, Math.min(1, value)) * 100;
  const tone = source === 'user' ? 'user' : percent >= 72 ? 'high' : percent >= 50 ? 'mid' : 'low';
  return (
    <span className={`confidence confidence-${tone} ${compact ? 'is-compact' : ''}`}>
      <span className="confidence-bar"><span style={{ width: `${percent}%` }} /></span>
      <span className="confidence-value mono">
        {source === 'user' ? 'edited' : value == null ? '—' : `${Math.round(percent)}%`}
      </span>
    </span>
  );
}

export function InlineNotice({
  tone = 'info',
  children,
  action,
}: {
  tone?: 'info' | 'warning' | 'error' | 'success';
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className={`inline-notice notice-${tone}`}>
      {tone === 'warning' || tone === 'error' ? <WarningIcon size={15} /> : null}
      <span>{children}</span>
      {action ? <span className="notice-action">{action}</span> : null}
    </div>
  );
}

export function Spinner({ size = 16 }: { size?: number }) {
  return <span className="spinner" style={{ width: size, height: size }} aria-label="Loading" />;
}

export function SectionHeader({
  title,
  meta,
  action,
}: {
  title: string;
  meta?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="section-header">
      <div className="section-heading">
        <h3>{title}</h3>
        {meta ? <span className="section-meta">{meta}</span> : null}
      </div>
      {action}
    </div>
  );
}
