import { useEffect, useState } from 'react';
import type { Facets, LibraryFilters } from '../types';
import { Button, Field, Modal, RangeField, Select, Toggle } from './Common';

const TIME_SIGNATURES = ['4/4', '3/4', '2/4', '6/8', '7/8', '5/4', '12/8', '5/8', '9/8'];
const KEYS = [
  'C major', 'G major', 'D major', 'A major', 'E major', 'B major', 'F# major',
  'Cb major', 'Gb major', 'Db major', 'Ab major', 'Eb major', 'Bb major', 'F major',
  'A minor', 'E minor', 'B minor', 'F# minor', 'C# minor', 'G# minor', 'D# minor',
  'Ab minor', 'Eb minor', 'Bb minor', 'F minor', 'C minor', 'G minor', 'D minor',
];
const STYLES = ['straight', 'swung', 'sparse', 'dense', 'syncopated'];

export function FilterDialog({
  open,
  filters,
  facets,
  onClose,
  onApply,
}: {
  open: boolean;
  filters: LibraryFilters;
  facets: Facets | null;
  onClose: () => void;
  onApply: (patch: Partial<LibraryFilters>) => void;
}) {
  const [draft, setDraft] = useState(filters);
  useEffect(() => {
    if (open) setDraft(filters);
  }, [open, filters]);

  const update = (patch: Partial<LibraryFilters>) => setDraft((current) => ({ ...current, ...patch }));
  const confidencePercent = Math.round(Number(draft.confidence_min || 0) * 100);

  const apply = () => {
    onApply({
      instrument: draft.instrument,
      role: draft.role,
      style: draft.style,
      tempo_min: draft.tempo_min,
      tempo_max: draft.tempo_max,
      time_sig: draft.time_sig,
      key: draft.key,
      key_source: draft.key_source,
      duration_min: draft.duration_min,
      duration_max: draft.duration_max,
      bars_min: draft.bars_min,
      bars_max: draft.bars_max,
      pitch_min: draft.pitch_min,
      pitch_max: draft.pitch_max,
      density_min: draft.density_min,
      density_max: draft.density_max,
      confidence_min: draft.confidence_min,
      source_id: draft.source_id,
      favorite: draft.favorite,
      uncertain: draft.uncertain,
      duplicate: draft.duplicate,
      scan_state: draft.scan_state,
      tag: draft.tag,
      include_failed: draft.include_failed,
      page: 1,
    });
    onClose();
  };

  const clear = () => {
    setDraft({
      ...draft,
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
      source_id: '',
      favorite: false,
      uncertain: false,
      duplicate: '',
      scan_state: '',
      tag: '',
      include_failed: false,
    });
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Refine the library"
      eyebrow="Filters"
      width="760px"
      footer={
        <>
          <Button variant="ghost" onClick={clear}>Clear filters</Button>
          <span className="footer-spacer" />
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={apply}>Apply filters</Button>
        </>
      }
    >
      <div className="filter-dialog">
        <section className="filter-section">
          <h3>Show only</h3>
          <div className="filter-row three">
            <Toggle
              label="Favorites"
              checked={draft.favorite}
              onChange={(value) => update({ favorite: value })}
            />
            <Toggle
              label="Uncertain classifications"
              checked={draft.uncertain}
              onChange={(value) => update({ uncertain: value })}
            />
            <Toggle
              label="Scan issues and failed files"
              checked={draft.include_failed}
              onChange={(value) => update({ include_failed: value })}
            />
          </div>
        </section>

        <section className="filter-section">
          <h3>Musical values</h3>
          <div className="filter-grid">
            <Field label="Tempo from" hint="BPM">
              <input
                className="input"
                type="number"
                inputMode="decimal"
                placeholder="Any"
                value={draft.tempo_min}
                onChange={(event) => update({ tempo_min: event.target.value })}
              />
            </Field>
            <Field label="Tempo to" hint="BPM">
              <input
                className="input"
                type="number"
                inputMode="decimal"
                placeholder="Any"
                value={draft.tempo_max}
                onChange={(event) => update({ tempo_max: event.target.value })}
              />
            </Field>
            <Field label="Time signature">
              <Select value={draft.time_sig} onChange={(event) => update({ time_sig: event.target.value })}>
                <option value="">Any meter</option>
                {TIME_SIGNATURES.map((meter) => <option key={meter}>{meter}</option>)}
              </Select>
            </Field>
            <Field label="Key">
              <Select value={draft.key} onChange={(event) => update({ key: event.target.value })}>
                <option value="">Any key</option>
                {KEYS.map((key) => <option key={key}>{key}</option>)}
              </Select>
            </Field>
            <Field label="Key evidence">
              <Select value={draft.key_source} onChange={(event) => update({ key_source: event.target.value })}>
                <option value="">Any evidence</option>
                <option value="embedded">Embedded signature</option>
                <option value="estimated">Estimated key</option>
                <option value="none">No key</option>
              </Select>
            </Field>
            <Field label="Source">
              <Select value={draft.source_id} onChange={(event) => update({ source_id: event.target.value })}>
                <option value="">All sources</option>
                {(facets?.sources || []).map((source) => (
                  <option key={source.id} value={source.id}>{source.label || source.path}</option>
                ))}
              </Select>
            </Field>
            <Field label="Duration from" hint="seconds">
              <input
                className="input"
                type="number"
                inputMode="decimal"
                placeholder="Any"
                value={draft.duration_min}
                onChange={(event) => update({ duration_min: event.target.value })}
              />
            </Field>
            <Field label="Duration to" hint="seconds">
              <input
                className="input"
                type="number"
                inputMode="decimal"
                placeholder="Any"
                value={draft.duration_max}
                onChange={(event) => update({ duration_max: event.target.value })}
              />
            </Field>
            <Field label="Bars from" hint="approx.">
              <input
                className="input"
                type="number"
                inputMode="decimal"
                placeholder="Any"
                value={draft.bars_min}
                onChange={(event) => update({ bars_min: event.target.value })}
              />
            </Field>
            <Field label="Bars to" hint="approx.">
              <input
                className="input"
                type="number"
                inputMode="decimal"
                placeholder="Any"
                value={draft.bars_max}
                onChange={(event) => update({ bars_max: event.target.value })}
              />
            </Field>
            <Field label="Lowest pitch" hint="MIDI 0–127">
              <input
                className="input"
                type="number"
                min={0}
                max={127}
                placeholder="Any"
                value={draft.pitch_min}
                onChange={(event) => update({ pitch_min: event.target.value })}
              />
            </Field>
            <Field label="Highest pitch" hint="MIDI 0–127">
              <input
                className="input"
                type="number"
                min={0}
                max={127}
                placeholder="Any"
                value={draft.pitch_max}
                onChange={(event) => update({ pitch_max: event.target.value })}
              />
            </Field>
            <Field label="Note density from" hint="notes per beat">
              <input
                className="input"
                type="number"
                inputMode="decimal"
                placeholder="Any"
                value={draft.density_min}
                onChange={(event) => update({ density_min: event.target.value })}
              />
            </Field>
            <Field label="Note density to">
              <input
                className="input"
                type="number"
                inputMode="decimal"
                placeholder="Any"
                value={draft.density_max}
                onChange={(event) => update({ density_max: event.target.value })}
              />
            </Field>
          </div>
        </section>

        <section className="filter-section">
          <h3>Feel and evidence</h3>
          <div className="filter-chip-row">
            {STYLES.map((style) => (
              <button
                key={style}
                type="button"
                className={`filter-tag ${draft.style.includes(style) ? 'is-active' : ''}`}
                onClick={() => update({
                  style: draft.style.includes(style)
                    ? draft.style.filter((item) => item !== style)
                    : [...draft.style, style],
                })}
              >
                {style}
              </button>
            ))}
          </div>
          <div className="filter-row two">
            <label className="inline-field">
              <span>Duplicate status</span>
              <Select
                value={draft.duplicate}
                onChange={(event) => update({ duplicate: event.target.value })}
              >
                <option value="">Any file</option>
                <option value="unique">No duplicate match</option>
                <option value="exact">Exact content duplicate</option>
                <option value="similar">Musically similar</option>
              </Select>
            </label>
            <label className="inline-field">
              <span>User tag</span>
              <input
                className="input"
                placeholder="Tag name"
                value={draft.tag}
                onChange={(event) => update({ tag: event.target.value })}
              />
            </label>
          </div>
          <RangeField
            label="Minimum classification confidence"
            value={confidencePercent}
            min={0}
            max={90}
            step={5}
            suffix="%"
            onChange={(value) => update({ confidence_min: value ? String(value / 100) : '' })}
          />
        </section>

        <p className="filter-note">
          Filters combine with AND. Choose multiple sound families or roles from the sidebar to widen a category.
        </p>
      </div>
    </Modal>
  );
}
