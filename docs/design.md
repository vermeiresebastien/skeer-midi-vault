# Interface and identity implementation

SKEER MIDI VAULT uses the approved SKEER visual language rather than a generic
dark music-app theme. The reference material was used for tokens, typography and
control grammar only; no product samples, presets or proprietary assets from
VRAC+ or REDRUM are included.

## Palette

The exact reference tokens live in `web/src/styles/tokens.css`:

| Role | Value |
| --- | --- |
| Warm ivory background | `#F5F2EB` |
| Paper-white panels | `#FCFAF6` |
| Pale-stone secondary surface | `#E7E2D8` |
| Charcoal text | `#292821` |
| Muted text | `#716C63` |
| Primary orange | `#FF6500` |
| Playback green | `#00CC66` |
| Error red | `#D9382E` |

Hairlines are warm-gray at low opacity. Orange is reserved for primary actions,
current selection and the active navigation state. Green is used for transport
activity and playback meters. Red appears only for errors and destructive-looking
states; there are no destructive source operations in this application.

## Typography

- **IBM Plex Sans** for interface labels, prose and controls.
- **IBM Plex Mono** for musical values: BPM, key, duration, note counts, paths,
  MIDI values, confidence percentages, scan counters and numeric metadata.
- **Barlow Condensed** is used only for the SKEER / MIDI VAULT lock-up lettering.

The fonts are bundled through the `@fontsource` packages and compiled into the
local Vite output (woff2), so the application does not call an external font CDN.

## Layout

The shell is a single-window library workspace:

- **Top bar:** approved logo/wordmark, library totals, local-only indicator,
  Settings and the orange Scan computer action.
- **Left rail:** All MIDI, Favorites, Uncertain, exact duplicates, similar files,
  collections, source folder tree, sound-family facets and role facets.
- **Center:** search, filter controls, sort, file count and the library table.
  Rows carry name, source folder, family, role, BPM, key, length, confidence and
  duplicate badges. Bulk actions appear only when rows are selected.
- **Right:** musical preview with track legend and canvas piano roll; original
  metadata; transparent classification with evidence/revert; tags, notes,
  collections; tracks with mute/solo.
- **Bottom transport:** play/pause, stop, loop, seek, audition tempo knob, source
  tempo, output selector, level meter and scan status. The transport stays put
  while the library scrolls.
- **Dialogs:** Scan computer, Settings, Filters and Export. Scanning configuration
  and appearance options live in settings/dialogs, not in the ordinary browsing
  flow.

## Studio Clean and Studio Tactile

Both skins are token sets over the same components; no component forks by skin.

- **Studio Clean:** flat paper panels, crisp one-pixel hairlines, minimal shadow,
  low texture. The default first-run skin.
- **Studio Tactile:** warmer paper, soft raised panels, subtle grain, deeper
  borders and a more physical tempo knob. Same layout, same controls.

The skin previews in Settings are miniature renderings of the same token system.

## Appearance controls

`web/src/appearance.ts` defines the default and persists a single local JSON
preference. The settings panel exposes:

| Control | Implementation |
| --- | --- |
| Studio Clean / Studio Tactile | `data-skin` token set |
| Accent | orange / ochre / teal / brick; drives selection and action color |
| Meter color | follow accent / orange / green / amber |
| Tile finish | smooth / plastic / rubber (subtle surface treatment on padded controls) |
| Tempo knob finish | flat / matte / metal |
| Texture strength | 0–100%, pre-rasterized paper-grain PNG overlay (no SVG filter or blend mode) |
| Panel contrast | 0–100% |
| Border strength | 0–100% |
| Interface scale | 80–125%, CSS zoom with inverse viewport compensation |
| Reduced motion | disables transitions and all non-essential animation |

Every change writes CSS custom properties on the document root. Reset returns to
the shipped Studio Clean defaults. The controls are application-real: the tempo
knob changes audition tempo, the level meter is driven by the audio analyser, and
the selected finish has a visible effect. No decorative blank knobs or fake
meters are used.

The paper grain is delivered as a small static PNG tile rather than a full-screen
SVG `feTurbulence` filter with `mix-blend-mode`. The earlier filter forced the
browser compositor to rasterize and blend a viewport-sized layer on every repaint;
during continuous pointer interaction on some GPUs this could crash the renderer
to a white tab. The static tile looks equivalent at normal viewing size and is far
safer under sustained canvas/transport updates. The piano roll likewise paints its
notes into a static canvas and draws the moving playhead as a lightweight DOM
overlay.

## Interaction details

- Search has an orange focus ring; `⌘/Ctrl+K` focuses it.
- Keyboard space toggles transport when focus is not inside a form control;
  arrow keys adjust the tempo knob when it is focused.
- Toggles use a clear on/off treatment and maintain accessible labels.
- Classification rows show confidence, evidence buttons and explicit
  "revert to auto" only when a manual label exists.
- The piano roll shows track colors, velocity lane, bar grid and notes; clicking
  a note seeks preview; click-and-drag inside the roll seeks after snapping.
- Long file names and folder paths truncate without hiding the full path from the
  details panel; every row has a source label.

## Responsive behavior

- Below 1360 px the top totals compress and low-priority columns hide.
- Below 1120 px the right details column becomes an overlay sheet and the sidebar
  label shortens.
- Below 760 px the layout stacks to a compact browse/detail flow; the transport
  remains reachable.
- Interface scale multiplies the shell with inverse width/height compensation so
  125% does not overflow a 1440×1000 window.

## Brand assets

`web/public/brand/` contains the approved ivory SKEER logo and generated crops
used for the wordmark, compact mark and favicon. The crops are produced by
`scripts/crop_brand.py`; no recolor, outline or unapproved restyling is applied.

## Accessibility and motion

Focus-visible outlines use the accent color. Controls have text labels or
`aria-label`, toggles expose `role="switch"`/checked state, confidence is never
conveyed by color alone, and reduced motion is a real persisted preference. The
keyboard path covers search, table selection, transport, settings, dialogs and
tag/collection entry.
