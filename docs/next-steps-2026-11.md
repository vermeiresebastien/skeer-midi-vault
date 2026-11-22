# SKEER MIDI VAULT — next steps plan (2026-11-14)

Prepared from seven independent research lanes over the tree (gap ledger, UX, engine,
hardening, audition/sound, 2026 competitive landscape, form factor). Every claim below
that drives a sequencing decision was re-verified against the files, not taken from the
lanes. Effort: **S** = under an hour, **M** = a few hours, **L** = a day-plus.

Dated note, 2026-11-17: this is the plan as written on 2026-11-14, and several of the
defects it describes have since been fixed, so most inline `path:line` citations here are
against the pre-fix tree and drift by a line or land on code that no longer matches the
sentence. The step entries that carry a ✅ state what is true now and re-cite themselves;
re-open the file before acting on any citation in a paragraph without one.

---

## 1. The decision

**Trust before features.** Four of seven lanes independently landed on the same shape:
the product is not missing capabilities so much as it is capable of being *silently
wrong*, and its next desirable feature set actively depends on fixing that first.

The load-bearing dependency is this:

- Duplicate/similar detection compares fingerprint vectors with weighted cosine
  (`midivault/engine/duplicates.py:85-92`), and `db.py:812-814` loads whatever
  `fingerprint_json` is in the table.
- Cache invalidation knows only `PARSER_VERSION` and `CLASSIFIER_VERSION`
  (`midivault/engine/versions.py:10-13`, checked in `midivault/scanner.py:315-323`).
  **There is no fingerprint version.** Verified: grep for `FINGERPRINT` in `midivault/`
  returns nothing.
- The intelligence avenues we actually want next — transposition-invariant similarity,
  groove vectors, chord sequences — all change the fingerprint.

That three-bullet premise is superseded, and it is left standing above as the reason the
sequencing went the way it did. Re-checked against the 1.1.0 tree on 2026-11-17:
`FINGERPRINT_VERSION = 1` and `LEGACY_FINGERPRINT_VERSION = 0` exist
([`versions.py:25-26`](../midivault/engine/versions.py)), `scanner.py:255` skips a cached
record whose generation is not the current one, `duplicates.py:62-72` reads that generation
out of the vector and returns *legacy* rather than guessing, and
`db.py:965-981` only feeds `fingerprint_json` into similarity once
`fingerprint_version` agrees. The line citations in the bullets above are the 2026-11-14
ones and no longer point at the code they describe — `duplicates.py:85-92` is now the
tempo/duration gates, not the cosine (`_cosine` is `duplicates.py:28`), `db.py:812-814` is
tag and label assembly, `versions.py:10-13` is the `SCHEMA_VERSION` paragraph and
`scanner.py:315-323` is failure recording. Step 2 of §3 is where that work is recorded
as done.

So the first useful similarity feature silently corrupts every existing library by
comparing old vectors against new ones, and nothing in the app can tell the user.
That is the reason the hardening wave precedes the feature wave, not a preference.

The same silent-wrongness recurs elsewhere and each instance violates a stated product
rule: `schema_version` is written but never compared (`db.py` as it read on 2026-11-14; the comparison exists today as `_stored_schema_version`), so a v2 build
opens a v1 DB and errors at runtime despite two docs claiming migrations exist; the
prediction "audit trail" is destroyed on re-run (`db.py:582` `DELETE FROM predictions
WHERE file_id=?`); the evaluation harness feeds the fixture's own folder name into the
classifier, so "100% accuracy" is partly the answer key leaking into the question; the
output chain can clip with no limiter and a meter that cannot show it; and notes over
the voice cap vanish without a trace.

Read as a present-tense list, that ledger is 2026-11-14 and one line has moved since. Checked
against the tree on 2026-11-18: the first item is closed — `schema_version` is read back and
compared (`_stored_schema_version` at `db.py:103`, the migrate-or-refuse branch at
`db.py:147-161`), which is Step 2's ✅. The other four are open and were confirmed still open:
the predictions overwrite (now `db.py:744`, and no step owns it), the answer-key leak
(`scripts/evaluate_classification.py:135` and `tests/test_demo_accuracy.py:27` both still pass
the fixture's own folder into `classify`), the unbounded output chain (no `WaveShaper` anywhere
in `web/src/audio/engine.ts`) and the silent voice drop (`engine.ts:730-732`, not `:686-689` —
still `skippedNotes += 1; return;`). Steps 3, 4 and 6 are where the last three are scheduled.

**Second decision: compete on the audition loop, not on more metadata.** The landscape
lane established that MIDI Xplorer is the benchmark — key + scale with confidence, BPM,
chords, tempo-synced preview, piano roll, non-destructive — and is **macOS-only**, with
Windows only "considered". Nobody in the table offers Windows + cross-DAW + offline
index + corrections trusted over auto-tags. That flank is open and it is ours. But
tempo-synced audition, transpose-before-load and a verified DAW handoff are table
stakes that all four credible competitors have and we half-have. Meanwhile our own audit
shows the loop stalls exactly where a producer spends his time: `patchFilters` discards
the selection on every facet click (`App.tsx:541-544`, verified), select-all is
page-scoped over 60 rows, and autoplay arms once per click with no sequence-end hook in
the engine. One click per file is Explorer with extra steps.

**Third decision: the form factor stays a standalone app.** Reversed 2026-11-15, when the
user chose Lane 2 -- a self-contained C++ reader, with SQLite vendored as source rather
than linked from a cache nobody can attribute. What still holds from this paragraph: the
engine-purity claim is true at the import level (verified: importing `midivault.engine`
pulls in no `sqlite3`, `http`, `db`, `api` or `scanner`), which is what makes a thin CLI
cheap. What Lane 2 settled rather than guessed: the plug-in never talks to
`127.0.0.1:8737` -- it reads the same index file with its own C++ reader over SQLite
vendored as source, so a running service is not a precondition for it working. And it now
does read that index: the editor panel's explicit Connect click opens it read-only, and
nothing before that click touches the file (measured by `vault-editor-test`, which lists
the index folder on both sides of building the panel).

---

## 2. Avenues, ranked

| # | Avenue | Lane | Value | Risk | Verdict |
|---|---|---|---|---|---|
| 1 | Seal the loopback boundary (Host allowlist, POST/CSRF discipline) | hardening | High | Low | **Do now** — every later feature widens this surface |
| 2 | `FINGERPRINT_VERSION` + real schema migration | hardening + engine | High | Low | **Do now** — precondition for 5, 6, 7 |
| 3 | Honest audio: limiter, peak/clip meter, no silent voice drop | audition | High | Low | **Do now** — owner-facing, violates current rules |
| 4 | Close remaining correction→audio holes | audition | High | Low | **Do now** — a promised behaviour that still leaks |
| 5 | Audition loop: selection model → keyboard → auto-advance | UX | High | Low | **Do now** — the differentiator, cheap first step |
| 6 | GM voice table + real drum kit | audition | High | Low | **Do now** — biggest perceptual gain, no dependency |
| 7 | Tempo-sync preview + transpose-before-load | market + audition | High | Med | **Next** — parity obligation |
| 8 | Verify DAW handoff (drag, clipboard, loopback MIDI out) | platform + UX | High | Med | **Next** — needs a manual test session, not code |
| 9 | Transposition-invariant similarity | engine | High | Low | **Next, gated on 2** — loudest current miss |
| 10 | Wire orphaned routes (delete source, rename/delete collection, bulk tag) | UX + gaps | Med | Low | **Cheap** — half-built backend, ~1 day total |
| 11 | Chord sequence over time; groove vector | engine | High | Med | **Later** — gated on 2, then it is genuinely new ground |
| 12 | Scale pass: facet caching, incremental duplicates, indexes | hardening | Med | Med | **Later** — real, but only bites at 50k+ files |
| 13 | Release gate (CI, version consistency, installer cycle) | hardening + gaps | Med | Low | **Now, minimal** — one Actions file, one script |
| 14 | Honest evaluation harness (stop leaking the answer key) | engine + gaps | Med | Low | **Now** — cheap, protects the "honesty in labels" rule |
| 15 | Soundfont / sample-based instruments | audition | High | High | **Blocked on a licensing decision** (§5) |
| 16 | Live Remote Script → project tempo/key into the vault | platform | Med | Med | **Later** — no supported Windows mechanism exists today |
| 17 | CLI `analyse/query/scan` | platform | Med | Low | **Optional** — do as a consequence of 2, not before it |
| 18 | VST3 browser + previewer | platform | Low | High | **Building** — Lane 2; plugin steps 1/3/4/5 and 9 (state restore) are committed. Steps 6 (the editor panel) and 7 (drag out, Copy path, Save clip as…) are committed as `eb7e4d9`: 6 suites, 15/24+1/35+1/77/136/26 checks, identical on JUCE 8.0.4 and 8.0.8. An independent review of that delta returned **not safe to commit**; both data-loss paths, the strip check that could not fail, and the three MEDIUM findings are now closed, each proven red against a revert of its own fix and green again byte-exact (see the status block at the end of this file). It is still **not accepted**: step 8 — a session in a real host — has not happened, and that is the only thing left on this row. The plan's Step 7 version gate reads 10 literals in 6 files |
| 19 | MCP/SSE machine endpoint | platform | Low | Med | **Defer** — duplicates the CLI, widens the boundary |
| 20 | Embedding / semantic search | engine | Low | High | **Reject under stdlib-only** — no model weights, no ANN; FTS5+BM25 already covers text |

---

## 3. Wave 1 — Trust (do this before any new capability)

**Step 1 — Refuse requests that don't come from us.** *S/M.* ✅ **Done 2026-11-15** — guards in
`api.py` (`_host_is_allowed`, `Sec-Fetch-Site`/Origin write rejection, `X-SKEER-Token`, 415 on
non-JSON) proven by `tests/test_http_boundary.py`. What was found: no code inspected
`Host`; the CORS loopback filter (`api.py:97-104`) is irrelevant to DNS rebinding because
after the A-record flips, `evil.tld` **is** same-origin and sends no `Origin` at all.
Today a page on the open internet can read `/api/db/backup` (`api.py:473,622-644`) which
streams the entire SQLite file — every path, note and correction — and can POST without
rebinding because `_read_json` ignores Content-Type (`api.py:136-152`): `/api/rebuild`,
`/api/scan/start`, `DELETE /api/sources/{id}`, and worst of all `/api/files/export`,
which does `mkdir(parents=True)` + `shutil.copy2` into an attacker-supplied absolute
`destination` (`api.py:659-716`). Source MIDI files are never touched, so the original
promise holds — this is disclosure plus arbitrary file planting.
Add: `Host` must resolve to the bound loopback name and port or be rejected with 403;
reject cross-origin writes; require `application/json` on mutating routes; mint a
per-session token in `desktop.py` and require it on every non-GET.
*Done when:* a new `tests/test_http_boundary.py` proves a `Host: evil.tld` GET and a
`text/plain` cross-origin POST to `/api/rebuild` both fail — and watch it fail against
current code before it passes. *Met*, and the same suite ran red against the pre-fix `api.py`.

**Step 2 — Version the fingerprint, then migrate the schema.** *S.* ✅ **Done 2026-11-15** —
`FINGERPRINT_VERSION`/`LEGACY_FINGERPRINT_VERSION` in `versions.py`, stamped by `pipeline.py`,
stored in `files.fingerprint_version`, refused across generations by `duplicates.similar_groups`,
forced through one re-index by the scanner's incremental skip, and surfaced in Settings → Data and
About. `SCHEMA_VERSION` is 2 with `MIGRATIONS[1]`, a pre-migration online-backup snapshot, and
fail-closed `SchemaError` on a newer or unmapped index; `tests/test_schema_migration.py` (9 tests)
runs red against the pre-migration code. The finding, for the record: `db.py` wrote
`schema_version` unconditionally, with no comparison and no `ALTER` anywhere, while the README's
migration prose (`README.md:238` as it read on 2026-11-15; that paragraph is gone, and migrations
are now only a line in the file map) and `docs/completed-partial-missing.md:80` — the
"schema versioning/migration" checkbox — described a mechanism that did not exist — the first
column-changing bump would have bricked existing installs rather than upgraded them.
*Done when:* a test builds a v1 DB, opens it with v2 code, and asserts the data survived
**and** the version advanced. *Met*, with extra coverage for the pre-migration backup, the
newer-index refusal, and legacy fingerprints rejoining similarity after exactly one scan.

**Step 3 — Nothing may leave the output chain unbounded.** *S.* Verified chain is
`master → compressor → analyser → destination` (`engine.ts:1072-1083`) with the
compressor at threshold −14 / knee 18 / ratio 4 / attack 4 ms — a huge knee and slow
attack that lets transients through. Summing is unnormalised (≈20 melodic voices at
`velocity*0.07` ≈ 1.4, × 0.78 master ≈ 1.09 pre-compressor), drum voices sit ~11 dB
above melodic (0.24 kick absolute vs 0.07-scaled), and the meter is post-compressor RMS
×3.6 with no peak-hold and no clip flag (`engine.ts:1114-1127`,
`TransportBar.tsx:222-227`) so it is invisible when it happens.
Add a `WaveShaper` soft-clip stage after the compressor, a peak-hold plus a latching
clip indicator, and make the drum-vs-melodic imbalance an **explicit per-family trim
control**, not automatic gain — an auto-correct here would be exactly the silent
compensation this product has committed to avoiding. Ramp `setVolume` instead of writing
`gain.value` (`engine.ts:291`), which currently clicks.
*Done when:* a deterministic level test renders a known dense arrangement and asserts
output never exceeds the safety ceiling, with the clip indicator having been observed.

**Step 4 — Never drop a note without saying so.** *S.* Verified: over
`MAX_POLYPHONY` the code does `this.stats.skippedNotes += 1; return;`
(`engine.ts:686-689`) — the loop you auditioned is missing notes and the UI is silent.
Notes under 12 ms are dropped the same way (`engine.ts:587`). Implement oldest/quietest
voice stealing, and surface a visible "N voices stolen on this file" badge with the cap
itself as a control. Silent loss is the worst class of automatic behaviour.
*Done when:* a test asserts polyphony is respected **and** note count played equals note
count present.

**Step 5 — Close the last correction→audio holes.** *M.* `b424bd4` claimed this area and
three leaks remain. (a) Verified: `App.tsx:476-477` returns early when identity and
signature match, and `soundSignature` (`sounds.ts:317-321`) covers only
`key|sound|role|channel` — so a re-parse that fixes note lengths, tempo or duration
never reaches the loaded engine until you select another file and back. Fold a content
hash of the sequence into the guard. (b) `setTrackFilter` releases and re-silences
(`engine.ts:346-361`) but `sendMidiProgramChanges` runs only on start/restart
(`1195-1213`), so un-muting a part mid-playback returns it wearing another channel's
patch on hardware. (c) Optimistic label writes carry no `corrections`
(`App.tsx:423-438` vs `600-638`), so between click and round-trip the audio can voice
the *file* category instead of your part correction.
*Done when:* one regression test per hole, each demonstrated red against current code.

**Step 6 — Make the accuracy claim honest.** *S.* Both harnesses pass the fixture's
filename **and its folder** into `classify` (`scripts/evaluate_classification.py:134-135`,
`tests/test_demo_accuracy.py:26-27`, folder from `fixtures/demo_labels.json`), so
"100% on 31 files" is largely the generator leaking its answer key. The only defensible
number today is track-role 84.6%. Re-run evaluation content-only and report both figures
separately. Two of this step's asks are discharged rather than open:
`docs/release-notes-1.0.0.md:52` keeps its 51/51 as the dated 1.0.0 record, and the
current counts live in `docs/release-notes-1.1.0.md` plus the dated 2026-11-17
re-verification in `docs/test-report.md` (**Ran 104 tests — OK**); and the `AGENTS.md`
vitest note is corrected against the tree — vitest *is* declared (`web/package.json:30`)
and installed, and `npm --prefix web test` exits 1 with `No test files found` because no
`src/**/*.test.ts` spec exists.

**Step 7 — A gate that fails.** *S.* ✅ **Gate and its red case done 2026-11-16; no CI by
choice.** No `.github/`, no hooks, no lint, and the only check between an edit and a
shipped EXE used to be remembering. `scripts/check_version_consistency.py` now reads every
version literal the repo states and exits non-zero on any disagreement. What it probes is
in the script and in the table it prints — never in a prose tally like the one this
paragraph used to carry, which was hand-counted, already stale and short by the literal
that matters most. Its own output on 2026-11-16:

```
  file:line                              literal               value
  midivault/__init__.py:8                __version__           1.0.0
  packaging/skeer-midi-vault.iss:8       AppVersion            1.0.0
  packaging/skeer-midi-vault.iss:20      VersionInfoVersion    1.0.0.0
  build/version_info.txt:3               filevers              1, 0, 0, 0
  build/version_info.txt:4               prodvers              1, 0, 0, 0
  build/version_info.txt:19              FileVersion           1.0.0
  build/version_info.txt:24              ProductVersion        1.0.0
  desktop.py:40                          VERSION               1.0.0
  web/package.json:4                     version               1.0.0
  plugin/CMakeLists.txt:3                project VERSION       1.0.0

6 files, 10 values, one version 1.0.0.
```

That copy is dated evidence, not a maintained list — re-run the script after a bump.
Superseded on 2026-11-17 by the 1.1.0 bump, which took the set to 8 files and 11 values:
`packaging/EULA.txt` gained a checked licence-version line, and the checker now also
probes for an *absence* — no version literal in `packaging/build_installer.ps1`, which
must read the number out of `midivault/__init__.py`. The current table is the gate's own
`gate` stage output under `build\work\release-check-<utc>\`, and its one-line verdict is
quoted in `docs/release-notes-1.1.0.md`.
Four of the ten sit in `build/version_info.txt` (lines 3, 4, 19 and 24), because Windows
reads the fixed file info and the string table separately: a bump that reaches `filevers`
and misses `prodvers` or either string ships an installer whose product version disagrees
with the binary inside it, and one probe never sees that. `plugin/CMakeLists.txt:3` is in
the list precisely because it is the literal that lands in the shipped bundle.
`tests/test_version_consistency.py` runs the gate from `unittest discover` and adds the red
case — the six targets copied into a temp directory with one literal moved, required to
exit 1 and name the disagreement — because a checker that probes nothing also exits 0.
Still open: the minimal Actions workflow running `unittest discover` + `npm run build`
(which is the typecheck) + this script. The 2026-11-16 assignment that built the gate ruled
new CI infrastructure out, so that stays a plan. `midivault/api/` is empty and untracked —
git never carried it — so there is nothing to delete in the repo.

---

## 4. Wave 2 — The audition loop

**Step 8 — Selection that survives filtering and spans pages.** *S.* ✅ **Half done
2026-11-15** — `patchFilters` no longer wipes the selection, and `tests/autoplay-deck.mjs`
holds a filter click over a two-file selection to prove it. Still open: select-all is
page-scoped over 60 rows (`LibraryView.tsx:281-293`), so making selection query-scoped across
pages, with an explicit "clear", remains. This is the enabler for 9 and 10.

**Step 9 — Keyboard browsing.** *S.* Rows are `role="option" tabIndex=0` with no listbox
parent and no arrow handler (`LibraryView.tsx:305-324`); global keys are only `/` and
Space (`App.tsx:497-522`). Add ↑/↓/Home/End moving the selection, autoplay riding it, and
a real `role="listbox"` parent. Also removes the accessibility gap `limitations.md` admits.

**Step 10 — Autoplay deck: play → auto-advance.** *M.* ✅ **Done 2026-11-15** —
`PreviewEngine.subscribeEnd()` fires only from `naturalEnd()`, so a pause, Stop or seek can
never read as "finished"; `App.tsx` derives the deck from the current list (or the selection
around the open file), advances on that event while Autoplay is on, steps with prev/next in the
transport, and reports `n / total`. Proven in a real browser by `tests/autoplay-deck.mjs` (8
checkpoints), which is red on `b424bd4` for both the advance and the selection. What it replaced:
autoplay armed once per click (`App.tsx:200-205,470-490`) with no sequence-end hook at all, so
ear-scanning a pack cost one click per file.

**Step 11 — GM-program-aware voice table.** *M.* `track.program` already reaches the
engine (`model.py:175`, engine.ts `gmProgramFor`) but is used only for MIDI-out; the synth path
reads no CCs and ignores CC10, deriving pan from a hash of the track number
(engine.ts `trackHash` → `pan.pan.value`). Map the 128 GM programs onto the 9 recipes plus per-family
cutoff/decay/trim. Zero dependencies, zero licensing, immediately audible.

**Step 12 — A snare that is a snare.** *M.* `buildDrum` collapses 17 GM keys into 6
synthesised gestures with everything else a square blip (engine.ts `buildDrum`), reuses one
cached noise buffer for every hit so all snares share a phase-locked noise stamp
(`826-836`), treats side stick (37) as cymbal noise (`875-888`), and flattens velocity
with a linear floor of 0.12 (`699,757`) so ghosts read as "quiet" rather than "light".
Full GM 35-81 coverage, per-instrument filter/decay, velocity→brightness, per-hit noise
offsets. Producers judge a loop on its drums first, so this outranks most new metadata.

**Step 13 — Bar-grid audition.** *M.* Loop wraps at the last event tick rather than the
bar (`smf_parser.py:832-836`, `engine.ts:602-622`) and truncates notes crossing the wrap
(`580-583`); seek steps 0.01 s with no snap (`TransportBar.tsx:173-196`); first-note delay
is ~60 ms (`engine.ts:495`) plus an async `resume()`. Add bar/beat snap for seek and loop,
region loop, count-in, and trim the start latency. The grid maths already exists for the
roll (`PianoRoll.tsx:43-102`) — reuse it. Fix `originalBpm` while here: it reads only the
first tempo event (engine.ts `firstTempo`) and reports the assumed 120 for SMPTE files, so
the readout is fiction where the audio is correct.

**Step 14 — Preview at a target tempo, and transpose before load.** *M.* Parity, not
differentiation: every credible competitor plays a file at the project's tempo and lets
you shift key before committing. `setAuditionBpm` (`engine.ts:305-318`) already does the
scaling — feed it a global target instead of only the first embedded event, and add an
explicit transposition control that affects audition and export alike. Keep both visible
and user-set; never infer the project tempo automatically.

---

## 5. Wave 3 — Handoff and similarity

**Step 15 — Verify the DAW handoff, then choose it.** *M, mostly manual.* Drag uses
Chromium `DownloadURL` (`LibraryView.tsx:86-92`, `DetailsPanel.tsx:251-258`) and the
**DAW drag target verification** bullet in `docs/completed-partial-missing.md` (under *Missing*) concedes it was never tested against a real DAW
target. Whether a Chromium drag lands a file in Ableton is the question; one session
with Live open answers it. In parallel test Web MIDI out to a loopback port — Live can
arm a track from one, which gives audition-through-Live's-own-synths with no audio engine
at all; note Windows ships no virtual MIDI port, so this needs loopMIDI and therefore an
install outside the repo. Add copy-path-to-clipboard regardless (*S*, no dependency).
This step is a decision point, not a task list: the outcome picks the next two.

**Step 16 — Transposition-invariant similarity.** *M.* The single loudest dedup miss: the
pitch-class vector is absolute (`pipeline.py:45`) so a transposed copy is invisible, and
a musical-content match additionally dies on the seconds-based duration gate
(duplicates.py `fingerprint_generation`), on any classifier label difference (the gates demand identical
instrument *and* role, `49-50`), and on a silent 240-file bucket cap (`122-127,150-152`).
Rotate PC vectors to the estimated tonic before cosine. **Gated on Step 2** — without a
fingerprint version this change poisons every existing index.

**Step 17 — Wire the routes the backend already has.** *S each, ~1 day total.* Verified
absent from `web/src/`: `DELETE /api/sources/{id}` — you can add a scan root and never
remove one; `PATCH`/`DELETE /api/collections/{id}` and `DELETE /collections/{id}/files` —
collections can be created but not renamed, deleted or pruned; bulk `action:"tag"`
(`api.py:315`) though the bulk bar offers only favorite/label/collection; `GET /api/stats`,
`/api/tags`, `/api/db/health`. Client-side dead code to remove or wire: `api.duplicates`,
`api.addCollectionFiles`, `api.health`, `api.drives`. Also render facets the server already
sends — `bootstrap.tags` and `facets.styles` are fetched and discarded while
`FilterDialog` hardcodes `STYLES` (`FilterDialog.tsx:12`) and makes tags free text, though
`db.py:1209` returns counts. And delete the unreachable `scan_state` chip branch: no
control ever sets it.

**Step 18 — Groove and harmony, if the index can carry it.** *L.* Ordered chord skeleton
per track rather than one hypothesis over the whole file (`analytics.py:208-220` runs 9
templates over a duration-weighted histogram), and a normalised drum vector — GM kit map
to {kick, snare, hat, cymbal, tom}, per-bar 16/32-step grid, swing offset — which makes
"same groove, different kit" searchable. Also kill the dead code found here:
`grid_occupancy` is structurally always 1.0 (`analytics.py:287`). Gate each behind
`FINGERPRINT_VERSION` plus `CLASSIFIER_VERSION` and expect a full re-index, since
invalidation is all-or-nothing per file with no partial path.

**Step 19 — Scale pass, sized to the real library.** *M.* `facets()` (`db.py:1166-1229`)
runs four unindexed aggregates and pulls every `style_tags` string into Python to count,
from `/api/bootstrap` **and** a 1-second poll while scanning (`App.tsx:254-256,326-342`) —
on a USB HDD the sidebar fights the scanner for the disk head. `finalise_duplicate_groups`
recomputes the entire library at the end of every scan including 3-file increments
(`scanner.py:424`). Missing indexes on `filename` (the default sort, `db.py:980`),
every numeric filter column, and the group-id columns; OFFSET pagination with a 200 cap;
folder tree truncated at 80 children behind a dead "+N more" label (`Sidebar.tsx:155`)
over a `LIMIT 8000` query. Fix facets-caching, incremental duplicates and the `filename`
index first; the rest only matters past ~5k files.

**Step 20 — Ship 1.0.1 properly.** *M.* Run the installer cycle for real — install,
shortcut, launch, uninstall — which the **Installer verification** bullet in
`docs/completed-partial-missing.md` (under *Missing*) admitted, as this was written, had never
happened. **That half is done, and this line is the annotation rather than the task:** the
elevated install -> launch -> installed-smoke -> uninstall cycle closed on 1.1.1 on both
placement arms - 17 phases per-user, graded by the release gate's own `installed` stage, and 18
with `/ALLUSERS`, recorded in `docs/release-notes-1.1.1.md` - and the release this step was
written for shipped as 1.1.1. What is left of it is the code-signing decision (SmartScreen is the
practical blocker for anyone else running this). Decide the soundfont question in §6 before touching
packaging. Then the release-notes and AGENTS.md corrections from Step 6 land here.

---

## 6. Needs your decision before it can be scheduled

**Soundfont licensing posture.** The audition lane ranks real sampled instruments highest
in value *and* highest in risk, and the blocker is not code — `web/` has no stdlib
constraint and zero audio deps today. The blocker is that a bundled GM soundfont is a
100-150 MB local asset (must stay local, not a CDN) needing an SF2 decoder, plus
redistribution rights, plus `packaging/` and `.spec` changes. Personal-use embedding is a
different risk class from shipping it inside `SKEER-MIDI-VAULT-Setup.exe`, which is what
this would become. Three viable answers: stay pure-synth and invest in Steps 11-12
(no new assets, no exposure); let the user point the app at a soundfont folder they own
(the best ceiling with the least legal surface); or bundle an openly-licensed bank such
as FluidR3 with attribution (zero cost to the user, permanent licence review). Steps
11-12 are worth doing under all three, so they are already scheduled — but Step 20 and
any packaging work wait on this.

**Is this shipping to other people?** Signing, the installer cycle, accessibility and
scale all harden if yes and stay optional if this is your own tool plus a portfolio
piece. The landscape says the niche is real but small and indie-priced at $39-49
one-time, with the direct Windows analogue absent — which is an argument for shipping,
but it is your call and it reorders Waves 2 and 3.

**Which handoff wins.** Step 15 is genuinely unresolved and cheap to resolve. If a
Chromium drag lands in Live, that is the whole story and loopMIDI is unnecessary. If it
does not, the choice is a watched import folder versus a third-party virtual port that
every user must also install — and that second option carries a dependency this project
has so far avoided entirely.

**Where a per-user install puts the plug-in.** 1.1.1 fixed the machine-wide destination, and the
evidence for it turned up the per-user counterpart on the same run: this host's own scan cache lists
bundles it enumerated out of `%LOCALAPPDATA%\Programs\Common\VST3` — 4 rows in the `12.3.5` cache,
including `SKEER Vault.vst3` and `Expressive Drum.vst3`, every one `ok`. That is the Windows per-user
VST3 folder, it needs no elevation to write, and our per-user Setup puts nothing there: it uses
`{app}\VST3`, a root that appears in **no** scan cache on this machine. So the install a buyer gets by
accepting the defaults ships a plug-in no host can see without a manual step, and closing it is one
`[Files]` destination rather than a design change. It waits here, not in a build, because a shipped
installer is involved: the `installed` leg and the cycle check have to be re-run against new bytes, a
`[Files]` change is behaviour and so this is 1.1.2 and not a doc patch, and two questions are yours —
whether the new destination *replaces* `{app}\VST3` (an upgrade would then leave the old copy orphaned
under `Programs\SKEER MIDI VAULT\VST3`, which Setup will not delete) or sits beside it, and how that
squares with your standing rule that a bundle lives in exactly one place. Measurement and the three
install routes are in `packaging/README.md`, "A host session".

**The machine-wide install puts the plug-in bundle in two places, and the Setup log only names one.**
Found 2026-11-22 at 03:34 local, on the first real `/ALLUSERS` install of the published 1.1.1 Setup run
on this machine (exit 0, 201 files, HKLM uninstall key `{B7E2D5A8-…}_is1` at `1.1.1`). A census of every
root by class ID tail — not by file name — found two copies of `SKEER MIDI VAULT.vst3`, both byte-identical
to the staged bundle in `launch/VST3` (PE `a2f15767…`, 7,566,336 B; moduleinfo `4fcc32b8…`, 1,339 B):

- `C:\Program Files\Common Files\VST3\SKEER MIDI VAULT.vst3` — the one every host looks in by default, and
  the fix 1.1.1 shipped to get.
- `C:\Program Files\SKEER MIDI VAULT\VST3\SKEER MIDI VAULT.vst3` — inside the app folder, so a host is only
  ever shown it if a person points one at it by hand.

The cause is two `[Files]` lines that disagree about intent: `packaging/skeer-midi-vault.iss:93` copies
`launch\VST3\*` to `{app}\VST3` with no `Check:`, and `:97` copies the same source to `{commoncf64}\VST3`
`Check: CommonVst3` — which is true only in admin mode. Per-user therefore gets one bundle; machine-wide
gets two. The `[Code]` log makes it hard to see from the outside: the admin branch logs "VST3: installing
into C:\Program Files\Common Files\VST3." and stops, while the per-user branch logs "installed only in
{app}\VST3". Both statements are true and only one of them is complete.

Why it is a defect rather than a curiosity: the product rule for this family is one bundle in one scanned
place, because two copies of one class ID is how a producer ends up editing a plug-in that a saved project
is not using. It is quiet today, and after the 2026-11-22 scan that is observed rather than inferred: the
host wrote exactly **one** module row and **one** device row for `SkAuMvlt` while two byte-identical copies
sat on disk. It stays quiet only because of which folders this machine's Live reads — the scanner log names
them per pass, and `{app}\VST3` is not among them. Take the two witnesses as different questions: on
2026-11-22 the logged passes read `C:\Program Files\Common Files\VST3` (global) and
`%LOCALAPPDATA%\Programs\Common\VST3` (custom), which is what this host reads *now*, while the cache also
carries rows naming a `K:\` folder that no logged pass ever scanned — what once produced rows is not the
same list as what is configured. A host that scans its own plug-in folder too, or a user who adds
`{app}\VST3` to a scan path, sees the same plug-in twice with no way to tell which is which.

Decision wanted for 1.1.2: give `:93` a `Check: not CommonVst3` so exactly one bundle lands in either mode,
or keep the app-folder copy deliberately and say in the release notes that a machine-wide install leaves a
second, unscanned copy behind. The first is one line and matches what the installer's own comment on `:94-96`
argues; the second is defensible only if a host somewhere is expected to want `{app}\VST3`. Either way the
admin log line should name both destinations it is about to write, because the log — not the README — is what
this was read from. And the certification hole is worth naming too: `install_cycle_check.ps1 -AllUsers`
proved the shared folder received a bundle and never asked how many bundles the machine received, so a green
`shared-folder PASS` row and a duplicate were compatible. The count-across-roots assertion now exists, in
`scripts/host_scan_check.ps1`: it walks every root the host's caches have ever named plus the two install
destinations, reads each `moduleinfo.json` with a regex rather than `ConvertFrom-Json` (JUCE has been
measured writing trailing commas, and a strict parser had already dropped one bundle silently that
evening), matches on the class ID tail, hashes each `Contents\x86_64-win` binary and compares it to the
staged one in `launch/VST3`, then exits 1 unless the machine holds exactly one copy. Measured against the
live state 2026-11-22 at 03:55 local, it went red on the real defect rather than on a planted one: 2 copies
of `SkAuMvlt`, both `sha256=A2F15767…`, 1 inside a root this host reads, exit **1**. The green control is the
same code path pointed at a pair that exists once — `-VendorCode Sker -PluginCode Skrv`, sample-vault's
bundle — which reported `one copy, in a root this host reads` and exit **0**. Both directions have now been
seen, so the row means something. What is still open is wiring it into the certification: it belongs in
`install_cycle_check.ps1`'s `-AllUsers` grading, and that is deliberately not done here, because the
machine carries the duplicate *today* and the published 1.1.1 Setup produces it — turning a shipped
release's gate red is the owner's call on 1.1.2, not a side-effect of adding a check.

**The host files the plug-in as an audio effect, where every sibling is an instrument.** Found
2026-11-22 at 16:22 local, in the first scan-cache row this product has ever had: our device row reads
`device:vst3:audiofx:…` with sub-category `"Fx"`. The same cache holds **11** Skeer-family device rows
counting ours, and the other ten are all `instr`:

```
  audiofx | SKEER MIDI VAULT  | Skeer Audio  | 1.1.1 | Fx
  instr   | BASSGEN           | SKEER        | 1.0.0 | Instrument
  instr   | DRUMGEN           | SKEER        | 1.0.0 | Instrument|Drum
  instr   | DRUMGEN Origin    | SKEER        | 0.1.0 | Instrument|Drum
  instr   | Groovebox         | Earworm      | 0.2.1 | Instrument|Drum
  instr   | PulseKit          | Skeer Audio  | 1.0.0 | Instrument|Synth
  instr   | SKEER Vault       | SKEER Audio  | 1.1.0 | Instrument|Instrument|Synth
  instr   | SKULPT            | Skeer Audio  | 1.2.0 | Instrument|Drum
  instr   | SliceForge        | SKEER        | 1.0.0 | Instrument|Drum
  instr   | VRAC+             | Earworm      | 1.0.0 | Instrument|Drum
  instr   | VRAC+             | SKEER        | 1.0.0 | Instrument|Drum
```

So this is not the family's convention drifting around us: we are the outlier, and one word in the build
causes it. `IS_SYNTH` in `juce_add_plugin` is what JUCE turns into the VST3 device class and sub-category a
host files a plug-in under — [plugin/CMakeLists.txt:102](../plugin/CMakeLists.txt) sets `FALSE`, while
`sample-vault/vst/CMakeLists.txt:121`, `pulsekit/CMakeLists.txt:64` and `skulpt/CMakeLists.txt:175` each set
`TRUE`. For scale, so the split is not mistaken for a quirk of these eleven: of the 1,416 VST3 device rows this reader
parses out of the cache, 1,298 are `audiofx` and 118 `instr` — a live set carries far more processing than
sound sources, which is also why the two populations sit in different places in the browser. The cache holds
1,614 device rows in all; the 198 this reader skips belong to other plug-in APIs, not to VST3.

Those numbers are the entire filing scheme, and saying so closes a reading of our own code. Counted across
every device row in that cache, the class-id kinds are `audiofx` and `instr` and nothing else — 1,298 and 118
for VST3, and 184 and 14 for the legacy VST2 rows, which are exactly the 198 the sentence above calls "other
plug-in APIs". There is no third kind, so there was never a MIDI-effect drawer for
`VaultMIDIProcessor.h:86`'s `isMidiEffect() == true` to land us in. What that override is for is a separate
question and not answered here — no audio bus count is configured anywhere under `plugin/Source/`, so nothing
in this tree shows the flag changing anything a person can observe, and this host certainly did not use it to
file us. The practical consequence for the decision below is that this is a two-drawer choice,
not a menu-placement detail: `instr` or `audiofx`, and the open question is whether the effect drawer will
accept a device that only speaks MIDI.

What that costs a producer is **not measured**, and this item should not be read as though it were. No
instance of ours has been loaded on a track, so nobody has observed whether the host routes MIDI notes to an
instrument-shaped processor filed as an effect, nor which menu a user thinks to open. The design question is
the second one: this plug-in's job is to hand the host a MIDI clip, and someone hunting for a source of notes
looks under Instruments, not under the reverb.

Decision wanted for 1.1.2, and the change is one word — `IS_SYNTH TRUE`. Be exact about what it moves: the
device class and the sub-category, not the class ID, which comes from the manufacturer/plugin-code pair, so a
project saved against today's device still resolves after the change (§6 below is about that pair, and this
flag does not touch it). It is still a behaviour change inside a shipped bundle, so it wants the same rebuild,
reinstall and rescan as the `{app}\VST3` decision rather than a doc-only release. And no check in this repo
would catch a regression: the category a host reports is only visible in that host's scan cache, which the gate
cannot own, so the assertion that stays inside the tree is one that reads the flag out of
`plugin/CMakeLists.txt` in the plug-in lane — a build-behaviour change, therefore a 1.1.2 decision of its own
rather than something to slip into a doc patch.
 Found while answering question 1 of the
host runbook, and it is a family decision rather than a midi-vault one. A VST3 has two vendor strings
and they do not have the same status. `COMPANY_NAME` is a display string: it is what a host shows in
its Vendor column and what folder it puts the plug-in in. `PLUGIN_MANUFACTURER_CODE` + `PLUGIN_CODE`
are the first half of the product's permanent identity — measured, not inferred: bytes 9-16 of the
class ID in `moduleinfo.json` are those four characters each in ASCII, ending in `SkAu` + `Mvlt` for us
(`ABCDEF019182FAEB536B41754D766C74`). Read across the bundles on this machine and the declarations in the
sibling repos, seven pairs line up — BASSGEN `SkBgBsgn`↔`bassgen`, DRUMGEN `SkDgDrgn`↔`drumgen`, SKEER
Vault `SkerSkrv`↔`sample-vault`, PulseKit `WkauPlkt`↔`pulsekit`, SKULPT `SkAuSkpt`↔`skulpt`, VRAC+
`ErwmVrac`↔`vrac-plus`, MIDI VAULT `SkAuMvlt`↔here. The eighth bundle on disk, `drumgenorigin`
(`SkDODgOr`), matched no declaration in the four drumgen CMakeLists files that were read. And
`SliceForge.vst3` carries `ErwmVrac` — VRAC+'s pair rather than its own, which is the reuse hazard
below already realised once on this disk.

The host's own cache now says it back without being asked. `scripts/host_scan_check.ps1` counts a
class-ID pair in `%APPDATA%\Ableton\Live *\Preferences\PluginScanDb.txt`; run against a sibling pair as
a control (`-VendorCode Sker -PluginCode Vrac`) it finds one device row carrying `SkerVrac`, and the
product-half needle finds three carrying `Vrac` — `VRAC+` twice, once as `SkerVrac` under vendor `SKEER`
and once as `ErwmVrac` under vendor `Earworm`, plus `SliceForge` under `ErwmVrac`. So the reuse hazard
above is not only on the disk: it is in the browser menu a producer reads, as two entries with one name
and one entry wearing another product's identity. That is the argument for testing recognition by ID.
The same control settled how to spell the needle — Live writes a CID in 8-4-4-4-12 groups, so our pair
appears as `536b-41754d766c74` and never as the contiguous sixteen hex digits, and a script that counted
only the contiguous form would report "not installed" about a plug-in this host has recognised. Both
spellings are counted and the larger taken, measured 2026-11-21 at 22:14Z.

The drift then wrote itself down unasked. In one scan pass at 05:47:07 on 2026-11-22 the host emitted two
adjacent records for two bundles sitting in the same folder — ours as `vendor: Skeer Audio`, the sibling's as
`vendor: SKEER Audio` — forty milliseconds apart. So the three-spelling split is no longer something
reconstructed from a `moduleinfo.json` census and a cache read hours apart: it is one file, one pass, one
instant, two capitalisations of one company. The eleven-row device table in the item above is the same kind of
witness for the pair the rule protects: it shows two `VRAC+` rows, one product name, vendors `Earworm` and
`SKEER`, both still standing in the host's list.

PulseKit is the natural experiment that settles the asymmetry, and this machine's own scan cache
witnesses it: the row for `PulseKit.vst3` names the vendor **"Workshop Audio"** while the moduleinfo of
that same bundle on disk reads `Skeer Audio` — the spelling was changed, the host has not rescanned
since, and the class ID in both is the same `WkauPlkt` (`Wkau` being an abbreviation of the name that
no longer exists). The display string is stale and a scan fixes it; the code is load-bearing and stays
forever. VRAC+ shows the cost of getting that backwards: the cache holds **two** devices for that one
product name, one ending `SkerVrac` and one `ErwmVrac`, so the manufacturer half of its identity was
changed at some point and the old identity was never reclaimed — a host carrying both is exactly the
orphaned-project situation the rule prevents. A third data point in the same direction:
`Eruw` in `groovebox/CMakeLists.txt:96` and `Erwm` in `vrac-plus/native/CMakeLists.txt:110` are one
transposition apart, and both are now permanent. (Whether the VRAC+ change and that transposition are
the same decision belongs to those repos; what is measured here is that a code change abandons an
identity rather than moving it.)

Two things follow, and only the first is free. **Unify the display string** whenever you like: this
family currently ships three spellings across seven bundles (`SKEER`, `SKEER Audio`, `Skeer Audio`,
with ours as an eighth using the third), which is why Live's browser carries three separate vendor nodes
and why the MCP bridge cannot address one of them: its path lookup case-folds, so all three spellings
return the `SKEER Audio` node and the `Skeer Audio` node — the one ours would appear under — is
unreachable by query. Unifying the string collapses the nodes; it costs a host rescan and nothing else.
**Never change our code pair again** — that is the half that would orphan a customer's saved project,
and it is now stated in `plugin/CMakeLists.txt` where
somebody would otherwise edit it. Note that `SkAu` is already shared with SKULPT: the *pair* is unique,
the manufacturer half is not, so a future product must not be handed `Mvlt`. Nothing currently checks
that, and the cheapest place to check it is the block in `packaging/build_installer.ps1` that already
refuses to ship a bundle whose `moduleinfo.json` disagrees with the release — have it assert the CID
tail reads `SkAuMvlt` too, which turns an accidental identity change into a build failure instead of a
support ticket about projects that lost their plug-in. That is a build-script behaviour change, so it
wants the gate re-run with it: 1.1.2, filed here rather than done.

---

## 7. Explicitly not doing

**VST3 browser/previewer** — no longer belongs on this list, and the two reasons given for
it did not survive the code. It was going to need "a C++ re-implementation or IPC fork of a
Python engine": the re-implementation is a locator, one read-only SQLite connection and one
`juce::MidiFile`, because the plug-in never needed the engine -- the index already holds
what the engine decided, corrections included, which was the ownership worry answered rather
than worked around. The panel talking to `127.0.0.1:8737` really was the wrong shape, and
Lane 2 exists to avoid shipping it. And "SQLite concurrency is *not* the obstacle" was half
right: `busy_timeout` (db.py:74) never came up because nothing here writes, but three other
things did -- `immutable=1` silently read stale pages, a read-only open creates the `-shm`
and `-wal` beside the user's index and cannot remove them, and a round trip through JUCE's
writer adds closing note-offs on every pass without ever converging. All three are measured
in `plugin/tests/` and written into the sources they constrain.
**MCP/SSE endpoint** — thin, but duplicates a CLI and enlarges a boundary we are still
closing in Step 1; better to be a client of an existing Live MCP than a host.
**Embedding-based semantic search** — infeasible under stdlib-only: no model weights, no
ANN structure, and pure-Python cosine is already capped at O(n²) per bucket; text search is
already FTS5 + BM25.
**Live project state** — no supported Windows mechanism exposes Live's transport to an
external process; Remote Script or Max for Live is the only sanctioned route, Ableton Link
needs a C++ dependency, and parsing `.als` is barred by the project's own no-archive rule
(`docs/supported-formats.md:82`).
**Moving sound overrides into SQLite** — they live in localStorage deliberately.
**Re-fixing what already holds** — 64 MB cap, parser track/note caps, per-file exception
isolation, batch-write fallback, WAL, kill-mid-scan recovery, incremental skip, user-data
survival across reprocess, and cloud/junction skipping are all genuinely implemented and
tested; several lanes verified them independently.

---

## 8. Sequencing

```
Wave 1  1 boundary ─┐
        2 fingerprint+schema ─┤→ unlocks 16, 18
        3 limiter+peak meter  ├── Trust       (~3-4 sessions)
        4 voice stealing      │
        5 correction→audio ───┘
        6 honest eval · 7 version gate          (independent, cheap)

Wave 2  8 selection model → 9 keyboard → 10 auto-advance
       11 GM voice table → 12 drums → 13 bar grid → 14 tempo+transpose

Wave 3  15 handoff verify (decides 15b) · 16 similarity · 17 orphaned routes
       18 groove/harmony · 19 scale pass · 20 ship 1.0.1
```

If only three steps get done: **1, 2, 10.** One removes a live disclosure and file-planting
path on a fixed port; one stops the index from lying to itself; one turns a file browser
into something a producer can actually ear-scan a pack with.

**Status 2026-11-15:** those three are built and verified, along with the selection-preserving
half of 8, and committed as `67ff177`. 1 and 2 are covered by `tests/test_http_boundary.py` and
`tests/test_schema_migration.py` (both red against the pre-fix tree); 10 and 8 by
`tests/autoplay-deck.mjs` in a real browser (red against `b424bd4`).

**Status 2026-11-16 — the plug-in lane (row 18, Lane 2):** steps 1/3/4/5 and 9 (state restore)
were built and committed earlier. Step 6 (the editor panel) and step 7 (drag a clip out of the
list, Copy path, Save clip as…) are committed as `eb7e4d9` on top of them; step 8 is
not built, because step 8 is a human session in a real host.

Six headless C++ suites cover the lane — 15 / 24+1 skipped / 35+1 skipped / 77 / 136 / 26 checks —
measured identical on JUCE 8.0.4 and 8.0.8 by running `plugin/build.ps1` against each tree (both
invocations are in `AGENTS.md`). Those numbers are a measurement, obtained by running each
executable, not a comment copied forward. The editor suite went 70 → 136 in the fix round below:
sixty-six checks for the branches the review could reach but the suite could not.

**What the suites prove.** A restored project naming a real clip makes the bundle emit MIDI
through the VST3 wrapper. Building the panel opens nothing in the user's data folder — a probe
that connected at construction turns four checks red, one of them a folder diff — and the index is
read only after an explicit Connect. An exported clip hashes to the same SHA-256 as its source, so
it is the original bytes and not a re-encode. No run of anything in this lane wrote to a source
`.mid` or to the index, and that was re-measured for this commit rather than carried forward: the
37 files under `fixtures/demo_library` hash to one aggregate (`6e293445…`) that is identical before
and after every run above, `git diff` against the previous commit on that folder is empty, and the
live index is still `da691fce…` at 449,347,584 bytes with the `-shm` and `-wal` beside it still
stamped 2026-11-15 18:51 — the suites point at their own temporary index and never open that
folder at all.

**What the review found, and where each finding stands now.** An independent read of the same
delta returned *not safe to commit*, and two of its findings were data-loss paths reachable from
the two buttons step 7 adds:

- the replace-confirmation box compared its button result the wrong way round, so **Cancel replaced
  the file and Replace did nothing** (JUCE's non-native `AlertWindow` numbers the first button 1 and
  the second 0 — verified against the checkout this build compiles, not inferred);
- a **0-byte source file deleted the target** instead of writing it, because `File::replaceWithData`
  turns a zero-length write into `deleteFile()`;
- the strip check could not fail — it substring-matched `byte-identical`, which the *refusal*
  sentence contains too — and the post-write re-hash, the only defence against a short write, had
  no assertion depending on it;
- plus three MEDIUM findings: a save note that outlived its own subject, a transient read failure
  that threw away a Connect the user had asked for, and four branches no check reached.

All six are closed. The confirm box is **gone rather than re-numbered**: the chooser now launches
with `warnAboutOverwriting`, so the OS asks the replace question, `saveChooserFlags()` is the single
source of truth a check reads, and `handleChosenTarget()` is the dialog-free seam the answer lands
on — which is what makes that half provable at all. An empty source is refused before any write,
with its own outcome and a message that says the target was left alone. The strip check now compares
the success sentence's exact prefix and asserts it does not begin with the refusal, and a read-back
cap drives the `bytesDiffer` verdict on purpose. A failed read keeps the index path and says "not
read this time"; Disconnect is the only click that forgets it. The unreachable branches are reached,
including the clipboard, which is proven by reading back what was put there.

The closure is differential, not asserted: each fix was reverted one at a time and the suite went
red for the reason that fix exists — the empty-source revert reproduced the deletion on screen, the
re-hash revert turned exactly the two `bytesDiffer` checks red, the flag and `overwriteExisting`
reverts each put the replace contract back under a check, the keep-the-connection revert produced
the literal "Index: not connected" in nine places, and the note-clearing revert failed its four
retirement checks. Each file was then restored and proven byte-identical by SHA-256 before the green
re-run.

Three things remain out of reach of any suite here, by construction: a real OLE drag (only the
container's answer function is called, never `startDrag`), the operating system's own overwrite
prompt (a modal dialog owned by the shell — the plug-in's box was deleted precisely because nobody
could drive it), and whether a hosted editor keeps keyboard focus. Those need a window and a host,
which is step 8. So the honest statement on this row is: **built, reviewed, closed and re-measured
on what the suites can see; not accepted.**

Two calls in it are the owner's and were taken by the builder because nothing said otherwise. The
panel's layout — one column, filter box on top, library list, the three exported controls always
visible, a status strip under them — was built without the design agreement the brief asked for, so
it is a proposal drawn in C++ rather than an approved design; nothing about it is hard to move. And
`EDITOR_WANTS_KEYBOARD_FOCUS` went FALSE → TRUE so the filter box could receive keystrokes, which
means the host routes typing to this window while it has focus. That is what every plug-in with a
search field does and it is one line to put back, but it changes how the plug-in feels in a session
and belongs to him, not to this lane. Both are written down in `docs/limitations.md`.

**The suite's one *assertion* flake is retired, and by its negative control rather than by a green
run.** This says nothing about the separate, harness-level failure `AGENTS.md` documents: Windows holding a
just-closed WAL file so `tearDown` reports a failure on a run where every assertion passed, about one suite
in six *before* `ignore_cleanup_errors=True` was set. No repeated-run evidence for the post-mitigation rate
is recorded anywhere, so do not read either paragraph as "the suite is clean" — read the rate, and say which
assertion the rate belongs to.
It was never a suite-order effect: 1 red in 6 full-suite runs and 2 red in 10 isolated runs of a
Python tree identical to `df30202`, every failure the same `AssertionError: 2 not greater than or
equal to 3`. The test started the scan and installed its own recording spy two lines later, so the
count depended on how far the worker had got before the spy was in place — a slow run's tail met the
`>= 3` floor and a fast run's head missed it. The fix opens the window before `start()` and gates on
the fixture's own file count, `len(seen) == db.stats()["files"]`, with the expected four pinned by a
separate assertion so a fixture change that emptied the index could not quietly turn equality into a
comparison with zero (`tests/test_scanner_db.py:492` is the gate, `:478` the count).

Measured on the tree as committed: 20 consecutive isolated runs of that test and 6 full runs of
`python -m unittest discover -s tests`, every one exit 0 and every full one `Ran 100 tests — OK`.
Then the two mutations, changing only the recording window and leaving the assertions exactly as the
fix wrote them. Opening the window *after* the run ends fails 3 times in 3, so the equality gate has
teeth. Putting the original order back — the race, re-induced — fails 11 times in 20, with `3 != 4`
seven times, `2 != 4` twice and `1 != 4` and `0 != 4` once each. Twenty green runs in a row have
about a 1.2e-7 chance on that measured rate, which is why 20 is the sample and not 3. The old floor
would have passed seven of those eleven failures: `>= 3` was not a weak threshold, it was a
threshold the defect could satisfy while still losing a quarter of the lookups it claimed to count.
