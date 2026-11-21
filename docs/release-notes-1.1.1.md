# SKEER MIDI VAULT 1.1.1 — release notes

Released 2026-11-21. A patch release: it fixes where the Windows installer puts the VST3
plug-in when you install for all users, and it fixes one click in the plug-in that used to
report success it had not had. The app's engine, database schema and interface are unchanged.

## Why this release exists

Version 1.1.0 shipped the VST3 bundle inside Setup, which was new. For a machine-wide install
it put the bundle here:

```
C:\Program Files\VST3\SKEER MIDI VAULT.vst3          ← 1.1.0 with /ALLUSERS
```

and it meant to put it here:

```
C:\Program Files\Common Files\VST3\SKEER MIDI VAULT.vst3
```

The cause is one Inno Setup constant. `{commonpf64}` is `C:\Program Files`; `{commoncf64}` is
`C:\Program Files\Common Files`. The `[Files]` entry used the first ([packaging/skeer-midi-vault.iss:97](../packaging/skeer-midi-vault.iss)),
so Setup wrote the bundle into a folder no VST3 host scans by default — while Setup's own log
line and the documentation both said "Common Files", because the person who wrote them read the
name, not the value. An install that reported success left a plug-in a host could not find.

A per-user install — what you get by accepting the defaults — was never affected: its bundle
goes to `{app}\VST3`, and the only thing to know about that folder is that a host has to be
pointed at it by hand.

## What changed

1. **The installer puts the machine-wide plug-in where hosts look.** `{commoncf64}\VST3`, and
   the Setup log line now prints the expanded path rather than a name, so the log says where the
   bundle actually went. Commit `7055952`.
2. **"Copy path" in the plug-in no longer believes the call, it checks the clipboard.**
   `SystemClipboard::copyTextToClipboard` returns nothing and silently skips the whole write when
   Windows refuses `OpenClipboard` — which a measured 13 of 60 single-shot attempts found happen
   on a real desktop. The click now writes, reads back, retries, and tells you which of the two
   outcomes happened. Measured detail in [docs/limitations.md](limitations.md). Commit `418506d`.
3. **The installer's own end-to-end check can now grade the machine-wide leg** — see
   *The all-users leg, run for the first time* below. Commits `7055952` and `10fbc15`.
4. **Version literals 1.1.0 → 1.1.1** across the eight files the gate reads (the app package,
   Setup's `AppVersion`/`VersionInfoVersion`, the Windows version resource, the desktop launcher,
   `web/package.json`, the plug-in's CMake `project(... VERSION)`, and the licence page's own
   "This version is 1.1.1" line). `python scripts/check_version_consistency.py` prints
   `8 files, 11 values, one version 1.1.1.` and the gate's `gate` stage refuses a half-bump.

Nothing else on the product side moved. Across `v1.1.0..HEAD` the only file that changed inside
`midivault/` is `midivault/__init__.py`, and nothing changed under `web/src/`. **The database
schema is still version 1: an index built by 1.1.0 opens in 1.1.1 unchanged, and no rescan is
required to upgrade.**

## Certified run

`scripts/release_check.ps1` at 2026-11-21 18:51:39Z, run from an elevated terminal so that the
`installed` stage could complete rather than skip:

```
READY - 11 passed, 0 failed, 0 skipped, of 11 stages, release 1.1.1
```

| Stage | Result |
| --- | --- |
| gate | PASS — 8 files, 11 values, one version 1.1.1 |
| suite | PASS — 104 tests, OK |
| web | PASS — `tsc --noEmit` and `vite build`, exit 0 |
| plugin | PASS — ctest 6/6 in `plugin/build` (JUCE 8.0.4) |
| plugin808 | PASS — ctest 6/6 in `plugin/build/tag-808` (JUCE 8.0.8) |
| installer | PASS — Setup 25,671,993 bytes, ZIP 34,694,142 bytes |
| stamp | PASS — commit `10fbc15aeb07`, clean, `web/dist` `dafc8187f542` |
| smoke | PASS — exit 0, bundle built from `10fbc15aeb07` |
| checksums | PASS — 2 rows, 2 release files in `launch/`, `sha256sum -c` exit 0 |
| licence | PASS — no placeholders, licence page states 1.1.1 |
| installed | PASS — install, launch, installed smoke, uninstall logged |

Per-stage logs: `build\work\release-check-20261121-185139\`.

This is the second READY of the day and the first whose `stamp` commit is also the commit the
tree is at. The earlier one, `release-check-20261121-183422`, certified `d8919c57cf48`; the only
commit after it touches `packaging/install_cycle_check.ps1`, which no stage copies into `launch/`
— the `installer` stage rebuilds the deliverables from the same inputs either way.

## The all-users leg, run for the first time

`packaging/install_cycle_check.ps1 -AllUsers`, against the Setup the run above built, 43 seconds
after it finished. It installs the real `launch/` artifact, launches what it registered, runs the
packaged smoke test against the installed executable, uninstalls, and compares the machine to
what it recorded beforehand:

```
CYCLE OK - 18 phases passed
  shared-folder  PASS  2 file(s) placed under C:\Program Files\Common Files\VST3, every one
                       inside our own bundle, and nothing else in that folder moved
  uninstall      PASS  shared VST3 folder still unchanged
  uninstall      PASS  user library at C:\Users\Sebastien\AppData\Local\Skeer\MIDI Vault is
                       still there, untouched
```

The `shared-folder` row is the one this release exists for, and the sentence above it is why it
took two runs to earn. The first run graded it **FAIL** — "the log claims a machine-wide copy but
`C:\Program Files\Common Files\VST3` has no bundle of ours in it". Setup's own log disagreed with
the check: it had created `...\Common Files\VST3\SKEER MIDI VAULT.vst3\Contents\x86_64-win\SKEER MIDI VAULT.vst3`
and `...\Contents\Resources\moduleinfo.json`, and the uninstaller had deleted both. The defect
was in the grader: it matched diff entries against `^SKEER MIDI VAULT\.vst3`, but the helper that
builds the diff prefixes every entry with its verb (`added: <path>`), so nothing could ever
classify as ours and the leg could not pass. Fixed in `10fbc15`, re-run, green above. Evidence:
`build\work\install-cycle-20261121-184006\` (the red run, whose Setup log is the proof) and
`build\work\install-cycle-20261121-185628\` (the green one).

The other arm of that same check was graded 18 seconds earlier, on the same bytes, by the gate's
own `installed` stage: a per-user install, `CYCLE OK - 17 phases passed`
(`install-cycle-20261121-185610`), whose `shared-folder` row reads

```
shared-folder  PASS  Setup logged the per-user placement and 1317 shared VST3 entries are unchanged
```

So both branches of `CommonVst3` were exercised against one build — the machine-wide copy that
this release exists to fix, and the per-user install that must leave the shared folder alone.

Two things that leg did **not** prove, so they are not claims:

- **No host has loaded the bundle from `Common Files\VST3` yet.** That is a session in a real DAW,
  which is the owner's to run; the procedure is [packaging/README.md](../packaging/README.md),
  "A host session — the three questions only a DAW can answer". It will
  not list two tidy candidates. An unrelated `SKEER Vault.vst3` — same family, different product,
  dated 2026-11-19 — already lives in that folder and was counted before and after at the same 1317
  entries, and the scan cache says this host knows seven Skeer-family devices in all: `SKEER Vault`,
  `DRUMGEN`, `DRUMGEN Origin`, `VRAC+`, `SKULPT`, `PulseKit` and `SliceForge`, under three different
  vendor spellings (`SKEER`, `Skeer Audio`, `SKEER Audio`). So the thing to match in a host's list is
  the exact string `SKEER MIDI VAULT` at version `1.1.1`, never a brand prefix.
  What a shell can show, and now does, is that the folder is read at all: this machine's Live wrote a plug-in scan cache at 15:49 local on 2026-11-21 whose 3,531
  rows include 751 naming `C:\Program Files\Common Files\VST3` and **zero** naming
  `C:\Program Files\VST3` — the folder 1.1.0 installed into. `scripts/host_scan_check.ps1` reads all
  four caches on this machine and every one of them has 0 rows for that folder and 0 for our bundle
  name, which is the measurement behind saying the placement was never cosmetic on this host. Recognition of a bundle is not the same as a track instantiating it, so the session
  still owns the answer; the measurement is in the runbook.
- The machine-wide leg was run once, on the machine that builds these files.

## Two self-tests that had stopped being able to bite

The red run quoted above was caught by a filter that had never been exercised, and auditing
that filter turned up two more. `Census-Diff` prefixes every entry it emits with its verb
(`added: <relpath>`), so an anchor written as `^SKEER MIDI VAULT\.vst3` cannot match — which is
exactly why the first machine-wide run read `FAIL` on a copy Setup had really made. All 31 call
sites of that helper were then re-read, and two of them carried the same class of stale
reference: [AGENTS.md](../AGENTS.md) pointed at `packaging/install_cycle_check.ps1:198` and
`:385` for code that now sits at `:225` and `:402`. Both repointed, and the lesson — a filter
that cannot match is not a filter that passes — is written into that file next to the fix,
because the red row's own witness is a gitignored log and the rule has to outlive it.

The second was in the release gate's falsifier. Its version-defect case planted a fault by
replacing the literal `u'1.1.0'` in `build/version_info.txt`, so once the tree read `1.1.1` the
substitution wrote back what it found: the case kept asserting a `FAIL` row against a tree it had
left clean, and no exit code said so. It now moves whatever the tree's own `FileVersion` reads and
appends a PROBLEM when it cannot find one, so a disarmed plant is reported instead of skipped.
Re-run: `FALSIFIER OK`, 33 cases, and the case earns its verdict again —
`[FAIL] gate - exit 1, says 'build/version_info.txt:19 FileVersion: 9.9.9'`.
Test infrastructure, not a shipped byte: none of the commits
after `10fbc15` are read by `packaging/build_installer.ps1`, so `launch/` still holds what that
certified build wrote, byte for byte.

## The tag message counts its own delta from the wrong base

The annotated tag says it carries "three commits after that build - two documentation and one
test-infrastructure - and `build_installer.ps1` reads none of the four distinct files they touch".
Against the build commit it names, `git rev-list --count 10fbc15..v1.1.1^{commit}` is **four** and the
distinct-file list is **eight** - seven documentation files plus `scripts/check_release_gate.py`. The
smaller pair was measured from `a8c9f28`, the commit the tag was moved off the same day: the count was
true of one range and printed inside a sentence about another. A relational claim carries its base,
and this is the same class of defect as the two drifted line anchors above.

None of it moves a shipped byte. `packaging/build_installer.ps1` reads none of those eight files as an
input - its only mentions of `packaging\README.md` are a comment and a log string. The test for that is
a command, not a number:

```
git log --oneline v1.1.1..HEAD -- scripts/release_check.ps1 scripts/check_release_gate.py packaging/build_installer.ps1
```

prints nothing, because no commit past the tag touches a file the build reads. Both artifacts were
re-hashed against `SHA256SUMS.txt` at 21:05Z on 2026-11-21 — Setup `d61324f2…`, ZIP `4a69a841…`, both
MATCH — and the Setup still carries its 18:55:50Z timestamp from the certified run, which is what says the
bytes were never rewritten.

What sat here before pinned a commit count: "the tree seven commits past the tag". That was true of the
tree it was written on and false of the commit it produced, which was the eighth. The tag message above
miscounted by reading a closed range as an open one; this paragraph miscounted by recording its own
post-image. An open-ended count has no stable value, so the carriers now give the command above, and the
live release page lost its number the same way. The tag object's message cannot be edited, only rewritten
and force-pushed, and a second move of a published tag is its owner's call, so this section is where both
discrepancies are recorded rather than silently patched.

## Artifacts

Both carry the same 198 payload files, counted off the artifacts themselves: the ZIP holds 198
files under 15 directory entries, and Setup's log lists those 198 plus its own generated
`unins000.exe`. Two of the 198 are the plug-in bundle, and a machine-wide run installs a second
copy of those two into `Common Files\VST3`. The installer registers the app in Add/Remove
Programs and the ZIP does not.

| File | SHA-256 |
| --- | --- |
| `SKEER-MIDI-VAULT-Setup-1.1.1.exe` | `d61324f201a790f17d637cfef86d6183a0ddf7dac6842d5a0be24fbf68afd588` |
| `SKEER-MIDI-VAULT-Portable-1.1.1.zip` | `4a69a841001e5fe4373d108c74bac4d801e374801b06582d457b667e9c31f0b5` |

`SHA256SUMS.txt` holds both rows, LF-only, and `sha256sum -c` on it exits 0. The bundle's
`_internal/buildinfo/BUILDINFO.json` names commit `10fbc15aeb0743012a856d3df9ee9c7f4ee34a0a`,
built `2026-11-21T18:54:52Z`, not dirty.

The Setup is **unsigned**, so SmartScreen will warn on first run; that is expected until an
Authenticode certificate is applied, and `build_installer.ps1 -Sign` is ready for one but has
never executed.

## Upgrading from 1.1.0

- **Installed per-user (the default):** install 1.1.1 over it, or uninstall first. Your index,
  favorites, tags, notes, collections and manual corrections are in
  `%LOCALAPPDATA%\Skeer\MIDI Vault` and survive both — the 18 phases above include an uninstall
  that checks exactly that.
- **Installed with `/ALLUSERS` on 1.1.0:** 1.1.1 puts its bundle in `Common Files\VST3`. If you
  also want the old copy gone, it is at `C:\Program Files\VST3\SKEER MIDI VAULT.vst3`; nothing
  reads that folder by default, so leaving it costs a duplicate if you ever point a host at it.
- **Using the portable ZIP:** nothing changes for you — the ZIP never had the machine-wide path.

## What this release does not claim

Unchanged from 1.1.0 and stated where it belongs, not here: real-world classification accuracy
is a regression result on self-authored synthetic fixtures; genre is a low-confidence hint;
no physical MIDI device round-trip; no archive extraction; no cloud, accounts or telemetry.
See [docs/limitations.md](limitations.md).
