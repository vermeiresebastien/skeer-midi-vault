<#
.SYNOPSIS
  Read the host's own VST3 scan cache and say what it proves about our bundle.
.DESCRIPTION
  Question 1 of the host-session runbook (packaging/README.md, "A host session") is whether a DAW
  finds the plug-in. Half of that is answerable without opening one: Ableton Live rewrites
  %APPDATA%\Ableton\Live <version>\Preferences\PluginScanDb.txt when it recognises plug-ins, so the
  file records which folders the host has actually read a bundle from.
  This script reads that file and prints counts. It writes nothing, opens nothing, and starts no DAW.
  It refuses rather than reporting zeros when its own patterns cannot work - a counter that can only
  print 0 is worse than no counter, because 0 on this question reads as "not installed".
  It also censuses *every* VST3 root the cache names, not just the ones listed below, because a needle
  list can only confirm what the author already suspected. The per-user root this census turned up
  (`%LOCALAPPDATA%\Programs\Common\VST3`) is the reason that rule is in the code.
  The recognition test is the class ID, not the file name. A host keys a plug-in on its 16-byte VST3
  class ID, whose last eight bytes are the ASCII of the two four-character codes in
  plugin/CMakeLists.txt. Those codes are read out of that file rather than repeated here, and the
  cache's device rows are counted against them. A bundle that was renamed, copied or rebadged still
  reports itself by ID; a name-only match proves nothing is ours.
  The cache cannot answer how many copies of the bundle the machine holds, and those two questions came
  apart on 2026-11-22: an /ALLUSERS install wrote one bundle into the shared scan root and a byte-identical
  second one into the application's own VST3 folder. No cache row names the second, because no root the host
  reads contains it - so a host-side check stayed green while the machine carried two. The read-only census
  therefore also walks every root this cache has ever named, plus the install destinations, and counts
  bundles by class ID tail. One copy in a scanned root is the placement the product rule asks for; more than
  one is reported as a duplicate whatever the cache says, and zero copies is said out loud rather than left
  as a silence that reads as "not installed".
  Which roots the host reads is not inferred from the cache either: PluginScanner.txt beside it logs every
  scan and names its roots, including a root that found nothing. That corrected a claim this script used to
  make. It read the cache's mtime as proof of whether a scan had happened, and the two disagree here by
  design - the 12.3.2 cache was last written 2026-11-21 22:14:45 while the log records complete scans at
  22:15:58 and 22:34:59. A scan that finds nothing new rewrites the log, not the cache. On this machine the
  log also settles what the duplicate is: the scans read 'C:\Program Files\Common Files\VST3' (global) and
  '%LOCALAPPDATA%\Programs\Common\VST3' (custom), and the application's own VST3 folder is neither. The
  prediction was then tested by an actual scan: at 2026-11-22 05:47:07 the log wrote a 'found:' record for
  this bundle whose own path line names the shared root, and at 16:22:06 Live persisted exactly one module
  row and one device row for our class ID while two copies sat on disk. So the second copy costs disk, and
  a rescan cannot turn it into a second device. Read a record's path, never its position: the scanner is
  asynchronous, so a block can print under the root line of a different one. And a pass that changes
  nothing logs its roots with no 'found:' lines at all, which is why this script reports the record it
  finds rather than an inference from either file's timestamp.
.EXAMPLE
  powershell -File scripts/host_scan_check.ps1
  powershell -File scripts/host_scan_check.ps1 -CacheFile "$env:APPDATA\Ableton\Live 12.3.2\Preferences\PluginScanDb.txt"
  powershell -File scripts/host_scan_check.ps1 -VendorCode Sker -PluginCode Vrac -BundleName VRAC
  # ^ control run, measured 2026-11-21 against the Live 12.3.2 cache on this machine: it reports
  #   1 row carrying 'SkerVrac' while all four needles for our own pair read 0. Run it before trusting
  #   a 0 about us - a test that has only ever printed 0 is not a test. §6 of
  #   docs/next-steps-2026-11.md lists which sibling bundle carries which pair, and one of the rows
  #   that run turns up is the reason the pair outlives the name: two products, VRAC+ and SliceForge,
  #   share one class ID in this cache.
#>
[CmdletBinding()]
param(
  [string]$CacheFile,
  [string]$BundleName = 'SKEER MIDI VAULT',
  [string]$VendorCode,
  [string]$PluginCode
)

$ErrorActionPreference = 'Stop'
$roots = @(
  [pscustomobject]@{ Label = 'shared (where 1.1.1 installs)'; Lit = 'C:\Program Files\Common Files\VST3' },
  [pscustomobject]@{ Label = 'old    (where 1.1.0 installed)'; Lit = 'C:\Program Files\VST3\' }
)

# The two four-character codes are the plug-in's permanent identity: bytes 9-16 of every VST3 class ID
# this bundle publishes are their ASCII (docs/next-steps-2026-11.md §6), and a host recalls a saved
# instance by that ID. They are read out of plugin/CMakeLists.txt rather than repeated here, because a
# second home for a literal is how a change half-lands. -VendorCode / -PluginCode override on purpose:
# the same reader has to be able to find a sibling product's pair, which is how the test gets proven.
if (-not $VendorCode -or -not $PluginCode) {
  $cmake = Join-Path $PSScriptRoot '../plugin/CMakeLists.txt'
  if (-not (Test-Path -LiteralPath $cmake)) {
    Write-Host "PROBLEM - cannot read the plug-in codes: $cmake"; exit 1
  }
  $cm = Get-Content -LiteralPath $cmake -Raw
  if (-not $VendorCode) {
    $m = [regex]::Match($cm, 'PLUGIN_MANUFACTURER_CODE\s+(\S+)')
    if (-not $m.Success) { Write-Host "PROBLEM - no PLUGIN_MANUFACTURER_CODE in $cmake"; exit 1 }
    $VendorCode = $m.Groups[1].Value
  }
  if (-not $PluginCode) {
    $m = [regex]::Match($cm, '\bPLUGIN_CODE\s+(\S+)')
    if (-not $m.Success) { Write-Host "PROBLEM - no PLUGIN_CODE in $cmake"; exit 1 }
    $PluginCode = $m.Groups[1].Value
  }
}
foreach ($pair in @(
  @('PLUGIN_MANUFACTURER_CODE', $VendorCode),
  @('PLUGIN_CODE', $PluginCode)
)) {
  if ($pair[1].Length -ne 4) {
    Write-Host ("PROBLEM - {0} reads '{1}': a VST3 code is exactly four characters." -f $pair[0], $pair[1])
    exit 1
  }
}
$hexV = -join ($VendorCode.ToCharArray() | ForEach-Object { '{0:x2}' -f [int]$_ })
$hexP = -join ($PluginCode.ToCharArray()  | ForEach-Object { '{0:x2}' -f [int]$_ })
$codeAscii = "$VendorCode$PluginCode"
# The identity rule used by both witnesses below: a VST3 class ID's last eight bytes are the two codes,
# so a bundle matches when its 32-hex ID ends with this run. Live prints the ID dash-grouped, which is
# why every reader here strips the dashes before comparing.
$wantTail = "$hexV$hexP"
# Four needles, because the same bytes are written two ways: moduleinfo.json prints the CID as one
# 32-hex run, Live prints it in 8-4-4-4-12 groups, which puts a dash inside the pair. The last two are
# the single codes, printed for context - the manufacturer half is shared with another product here,
# so neither one on its own is an identity match.
$cidNeedles = @(
  "$hexV$hexP",
  "$($hexV.Substring(0,4))-$($hexV.Substring(4))$hexP",
  $hexV,
  $hexP
)

if ($CacheFile) {
  $targets = @(Get-Item -LiteralPath $CacheFile -ErrorAction SilentlyContinue)
  if (-not $targets.Count) {
    Write-Host "PROBLEM - cache file not found: $CacheFile"
    exit 1
  }
} else {
  $pattern = Join-Path $env:APPDATA 'Ableton\Live *\Preferences\PluginScanDb.txt'
  $targets = @(Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue |
                 Sort-Object LastWriteTime -Descending)
}
if (-not $targets.Count) {
  Write-Host "PROBLEM - no PluginScanDb.txt under $env:APPDATA\Ableton"
  Write-Host 'Nothing is measured. Either this machine has never run Live, or Live has changed where it caches scans.'
  exit 1
}

# The scanner log beside a cache is a better witness than the cache's own mtime, and the two disagree
# on this machine by design. Measured 2026-11-22: Live 12.3.2's PluginScanDb.txt was last written
# 2026-11-21 22:14:45, while PluginScanner.txt logs complete scans after that at 22:15:58 and 22:34:59.
# A scan that finds nothing new rewrites the log and leaves the cache alone, so "the cache is old" can
# never mean "no scan has happened". The log also names the roots a scan actually reads, which a cache
# cannot do: a root that contains nothing has no rows, so a cache-derived root list is silently a list
# of roots that found something.
$scanRoots = @{}
$lastScan = $null
$lastScanByCache = @{}
$foundByCache = @{}
foreach ($t in $targets) {
  $log = Join-Path (Split-Path -Parent $t.FullName) 'PluginScanner.txt'
  if (-not (Test-Path -LiteralPath $log)) { continue }
  $thisRoots = @{}
  $thisLast = $null
  $lines = 0
  # 'VST3: found:' opens an indented block carrying the class ID, the vendor string a host files the
  # plug-in under, and the fingerprint of the file it read. Read as records rather than one grep, because
  # the ID is the only field in there that proves *which* plug-in was found.
  $recs = @()
  $rec = $null
  foreach ($ln in @(Get-Content -LiteralPath $log -ErrorAction SilentlyContinue)) {
    if ($ln -match 'VST3: scanning plugins in "(?<p>[^"]+)" \((?<s>global|custom)\)') {
      $lines = $lines + 1
      $p = $Matches['p'] -replace '/', '\'
      if ($ln -match '^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})') {
        $ts = [datetime]$Matches[1]
        if (-not $lastScan -or $ts -gt $lastScan) { $lastScan = $ts }
        if (-not $thisLast -or $ts -gt $thisLast) { $thisLast = $ts }
      }
      if (-not $thisRoots.ContainsKey($p)) { $thisRoots[$p] = $Matches['s'] }
      if (-not $scanRoots.ContainsKey($p)) { $scanRoots[$p] = $true }
      continue
    }
    if ($ln -match '^(?<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\S*: info: VST3: found: (?<n>.+?)\s*$') {
      if ($rec) { $recs = $recs + $rec }
      $rec = [pscustomobject]@{ When = $Matches['ts']; Name = $Matches['n']; Vendor = ''; Kind = ''; Cid = ''; Ver = ''; Sub = ''; Path = ''; Fp = '' }
      continue
    }
    if (-not $rec) { continue }
    if ($ln -match '^\s+vendor: (?<v>.*?)\s*$')            { $rec.Vendor = $Matches['v'] }
    elseif ($ln -match '^\s+subCategories: (?<v>.*?)\s*$') { $rec.Sub = $Matches['v'] }
    elseif ($ln -match '^\s+version: (?<v>.*?)\s*$')       { $rec.Ver = $Matches['v'] }
    elseif ($ln -match '^\s+path: "?(?<v>[^"\r\n]+)')      { $rec.Path = $Matches['v'] }
    elseif ($ln -match 'device-class-id: device:vst3:(?<c>\w+):(?<i>[0-9a-fA-F-]{36})') {
      $rec.Kind = $Matches['c']; $rec.Cid = ($Matches['i'] -replace '-', '').ToLower()
    }
    elseif ($ln -match '^\s+fp: (?<v>\S+)') { $rec.Fp = $Matches['v']; $recs = $recs + $rec; $rec = $null }
  }
  if ($rec) { $recs = $recs + $rec }
  $lastScanByCache[$t.FullName] = $thisLast
  $oursLog = @($recs | Where-Object { $_.Cid.Length -eq 32 -and $_.Cid.EndsWith($wantTail) })
  $foundByCache[$t.FullName] = $oursLog
  Write-Host ''
  Write-Host ("SCANNER LOG - {0}" -f $log)
  if (-not $lines) {
    Write-Host '  no VST3 root lines. Either this log is not the format this reader knows, or this host never scanned.'
    Write-Host '          Reported, not assumed empty: a root that found nothing has no cache rows, so the cache'
    Write-Host '          alone cannot say what this host reads.'
  }
  foreach ($k in ($thisRoots.Keys | Sort-Object)) {
    Write-Host ("  scans read: [{0}] {1}" -f $thisRoots[$k], $k)
  }
  Write-Host ("  last scan by this host : {0}" -f $thisLast)
  Write-Host ("  found records : {0}, of which {1} carry class-ID tail '{2}'" -f $recs.Count, $oursLog.Count, $wantTail)
  foreach ($r in $oursLog) {
    Write-Host ("    {0}  '{1}' v{2}  vendor '{3}'  device:vst3:{4} [{5}]  fp {6}" -f $r.When, $r.Name, $r.Ver, $r.Vendor, $r.Kind, $r.Sub, $r.Fp)
    Write-Host ("      read from {0}" -f $r.Path)
  }
}
if ($lastScan) { Write-Host ("  newest scan across the logs read : {0}" -f $lastScan) }

$seenRoots = @{}
foreach ($t in $targets) {
  $text = Get-Content -LiteralPath $t.FullName
  $rows = @($text).Count
  $count = { param($needle) @(Select-String -Path $t.FullName -Pattern $needle -SimpleMatch).Count }
  $ours = & $count $BundleName
  $shared = & $count $roots[0].Lit
  $old = & $count $roots[1].Lit

  $ageMin = [int]((Get-Date) - $t.LastWriteTime).TotalMinutes
  Write-Host ''
  Write-Host $t.FullName
  Write-Host ("  last written {0}  ({1} min ago)   rows={2}" -f $t.LastWriteTime, $ageMin, $rows)
  Write-Host ("  rows naming the shared VST3 folder : {0}" -f $shared)
  Write-Host ("  rows naming the old VST3 folder    : {0}" -f $old)
  Write-Host ("  rows naming '{0}' : {1}" -f $BundleName, $ours)

  # The class ID lives in the device rows, and only there. If this cache has none, the ID test cannot
  # see anything and would print a 0 that reads as "not installed" - so refuse, as everywhere else here.
  $dev = @($text | Where-Object { $_ -match 'device:vst3:' })
  if (-not $dev.Count) {
    Write-Host 'PROBLEM - this cache has no device:vst3: rows, so the class-ID test has nothing to read.'
    Write-Host '          A zero from here is the reader being blind, not the host being empty. Fix the reader.'
    exit 1
  }
  $cidRows = @($cidNeedles | ForEach-Object {
    $n = $_
    [pscustomobject]@{ Needle = $n; Hits = @($dev | Where-Object { $_ -match [regex]::Escape($n) }).Count }
  })
  Write-Host ("  device rows in cache : {0}   class-ID pair under test : '{1}'" -f $dev.Count, $codeAscii)
  foreach ($c in $cidRows) {
    $what = if ($c.Needle -eq $hexV) { 'manufacturer half alone - splits across the host dash, so 0 by construction' }
            elseif ($c.Needle -eq $hexP) { 'product half alone - other plug-ins may share it' }
            elseif ($c.Needle -like '*-*') { 'both codes, host dash grouping' }
            else { 'both codes, contiguous' }
    Write-Host ("    {0,4} row(s) carry {1}  - {2}" -f $c.Hits, $c.Needle, $what)
  }
  # The Max is not tidiness. Measured 2026-11-21 on the Live 12.3.2 cache with a sibling pair that IS
  # in it (docs/next-steps-2026-11.md §6): the dash-grouped needle found 1 row and the contiguous one
  # found 0, because the host writes a CID as 8-4-4-4-12 and the split lands inside these bytes. A test
  # built on the contiguous form alone reports "not installed" about a plug-in the host has recognised.
  $byId = [Math]::Max($cidRows[0].Hits, $cidRows[1].Hits)

  # A cache with rows but no recognisable path at all is the broken-pattern signature, not an empty host.
  $anyPath = @(Select-String -Path $t.FullName -Pattern '.vst3' -SimpleMatch).Count
  if ($rows -gt 0 -and $anyPath -eq 0) {
    Write-Host 'PROBLEM - the file has rows but no .vst3 path in any of them: this cache is not the format'
    Write-Host '          this script reads, so every count above is meaningless. Fix the reader, not the host.'
    exit 1
  }
  # The census: every distinct VST3 root this cache names, and whether that folder is still there.
  $agg = @{}
  foreach ($line in $text) {
    $pm = [regex]::Match($line, '"([^"]+\.vst3[^"]*)"')
    if (-not $pm.Success) { continue }
    $rm = [regex]::Match($pm.Groups[1].Value, '(?i)^(.*\\VST3)\\')
    if (-not $rm.Success) { continue }
    $r = $rm.Groups[1].Value
    if ($agg.ContainsKey($r)) { $agg[$r] = $agg[$r] + 1 } else { $agg[$r] = 1 }
  }
  $known = @($roots | ForEach-Object { $_.Lit.TrimEnd('\') })
  foreach ($k in $agg.Keys) { if (-not $seenRoots.ContainsKey($k)) { $seenRoots[$k] = $true } }
  Write-Host ("  distinct VST3 roots named in this cache : {0}" -f $agg.Count)
  foreach ($kv in ($agg.GetEnumerator() | Sort-Object -Property Value -Descending)) {
    if (Test-Path -LiteralPath $kv.Key) { $tag = '[on disk now]' } else { $tag = '[absent now]' }
    $named = $false
    foreach ($k in $known) { if ($kv.Key -like ($k + '*')) { $named = $true } }
    if ($named) { $arrow = '' } else { $arrow = '   <-- read by this host, not named by the needles above' }
    Write-Host ("    {0,5} rows  {1}  {2}{3}" -f $kv.Value, $kv.Key, $tag, $arrow)
  }

  if ($shared -eq 0 -and $old -eq 0) {
    Write-Host 'NOTE - neither candidate folder appears. This host has not scanned either one, so a scan of'
    Write-Host '       ours here would prove nothing about placement until the host is pointed at a folder.'
  }

  if ($byId -gt 0) {
    Write-Host ("VERDICT - {0} device row(s) carry the class ID '{1}', so the host has read this plug-in." -f $byId, $codeAscii)
    Write-Host '         That is recognition, not a load: a track still has to instantiate it.'
    if ($ours -eq 0) {
      Write-Host "         No row names '$BundleName', though: the bundle it found is filed under another name"
      Write-Host '         or vendor folder. The ID is the proof; go and look for what is actually there.'
    }
  } elseif ($ours -gt 0) {
    Write-Host "VERDICT - rows name '$BundleName' but none carry the class ID '$codeAscii'."
    Write-Host '         A name match without an ID match is not this plug-in - another file, or a code pair'
    Write-Host '         that changed. Check -VendorCode / -PluginCode against the bundle on disk.'
  } else {
    $seen = @($foundByCache[$t.FullName])
    if ($seen.Count) {
      Write-Host 'VERDICT - no row in this cache, but this host recognised the bundle and wrote it down itself:'
      Write-Host ("         '{0}' v{1} found at {2}, class-ID tail '{3}'." -f $seen[0].Name, $seen[0].Ver, $seen[0].When, $wantTail)
      Write-Host '         The log and the cache have different writers, and here the log runs ahead of the cache.'
      Write-Host '         That proves the scan read us; it does not prove the browser lists us. Different question.'
    } else {
      Write-Host 'VERDICT - neither the name nor the class ID is in this cache. Install, then make the host rescan.'
      $thisScan = $lastScanByCache[$t.FullName]
      if ($thisScan) {
        Write-Host ("         This host's log says it last scanned {0}; this cache was last written {1} ({2} min ago)." -f $thisScan, $t.LastWriteTime, $ageMin)
        Write-Host '         The two can differ without either being wrong - a scan that finds nothing new rewrites'
        Write-Host '         the log and leaves the cache alone. The log is the witness for "has it scanned".'
      } else {
        Write-Host ("         No scanner log beside this cache, so its mtime is all there is: {0} min old." -f $ageMin)
      }
    }
  }
}
# The disk census. A cache row records that a scan once found something; a file on disk is a fact about
# placement, and only the second one answers "one bundle, one place". Identified by class ID tail, read
# with a regex rather than ConvertFrom-Json: JUCE has been measured writing moduleinfo.json with trailing
# commas, and a strict parser drops that bundle silently, which is how a first census missed one entirely.
$census = @{}
foreach ($k in $seenRoots.Keys) { $census[$k] = $true }
# A root the scanner log names outranks one inferred from cache rows: the log is what the scan said it read.
foreach ($k in $scanRoots.Keys) { $census[$k] = $true }
foreach ($k in @('C:\Program Files\SKEER MIDI VAULT\VST3',
                 (Join-Path $env:LOCALAPPDATA 'Programs\SKEER MIDI VAULT\VST3'))) {
  if (-not $census.ContainsKey($k)) { $census[$k] = $false }
}
$modules = 0
$found = @()
foreach ($r in @($census.Keys)) {
  if (-not (Test-Path -LiteralPath $r)) { continue }
  foreach ($mi in @(Get-ChildItem -LiteralPath $r -Recurse -Filter 'moduleinfo.json' -File -ErrorAction SilentlyContinue)) {
    $modules = $modules + 1
    $raw = Get-Content -LiteralPath $mi.FullName -Raw
    foreach ($m in [regex]::Matches($raw, '"CID"\s*:\s*"([0-9A-Fa-f]{32})"')) {
      if ($m.Groups[1].Value.Substring(16).ToLower() -ne $wantTail) { continue }
      $leaf = [regex]::Match($raw, '"Name"\s*:\s*"([^"]*)"').Groups[1].Value
      $ver = [regex]::Match($raw, '"Version"\s*:\s*"([^"]*)"').Groups[1].Value
      $bundle = $mi.FullName -replace '\\Contents\\Resources\\moduleinfo\.json$', ''
      $peDir = Join-Path $bundle 'Contents\x86_64-win'
      $peName = ''
      $peHash = ''
      if (Test-Path -LiteralPath $peDir) {
        $pe = @(Get-ChildItem -LiteralPath $peDir -File -ErrorAction SilentlyContinue | Where-Object { $_.BaseName -eq $leaf })
        if ($pe.Count -eq 0) { $pe = @(Get-ChildItem -LiteralPath $peDir -File -ErrorAction SilentlyContinue) }
        if ($pe.Count -gt 0) {
          $peName = $pe[0].Name
          $peHash = (Get-FileHash -LiteralPath $pe[0].FullName -Algorithm SHA256).Hash
        }
      }
      if (-not ($found | Where-Object { $_.Path -eq $bundle })) {
        $found = $found + [pscustomobject]@{ Path = $bundle; Version = $ver; Scanned = [bool]$census[$r]; Binary = $peName; Hash = $peHash }
      }
      break
    }
  }
}
Write-Host ''
Write-Host ("DISK CENSUS - roots examined: {0}   moduleinfo.json read: {1}   class-ID tail: '{2}'" -f $census.Count, $modules, $wantTail)
if ($modules -eq 0) {
  Write-Host 'PROBLEM - not one moduleinfo.json was readable under the roots examined, so a "no copies" result'
  Write-Host '          from here would be this reader being blind. Fix the reader before believing it.'
  exit 1
}
foreach ($f in ($found | Sort-Object -Property Path)) {
  $where = 'NOT in a root this host reads'
  if ($f.Scanned) { $where = 'scanned by this host' }
  Write-Host ("  {0}  v{1}  [{2}]" -f $f.Path, $f.Version, $where)
  $binLabel = 'binary absent from Contents\x86_64-win'
  if ($f.Binary) { $binLabel = ('{0}  sha256={1}' -f $f.Binary, $f.Hash) }
  Write-Host ("      {0}" -f $binLabel)
}
$refDir = Join-Path $PSScriptRoot '../launch/VST3'
if ((Test-Path -LiteralPath $refDir) -and $found.Count -gt 0) {
  $ref = @(Get-ChildItem -LiteralPath $refDir -Recurse -File -Filter '*.vst3' -ErrorAction SilentlyContinue |
             Where-Object { $_.FullName -like '*\Contents\x86_64-win\*' })
  if ($ref.Count -gt 0) {
    $refHash = (Get-FileHash -LiteralPath $ref[0].FullName -Algorithm SHA256).Hash
    $same = @($found | Where-Object { $_.Hash -eq $refHash }).Count
    Write-Host ("  staged in launch\VST3 : {0}  sha256={1}" -f $ref[0].Name, $refHash)
    Write-Host ("  on-disk copies byte-identical to the staged one : {0} of {1}" -f $same, $found.Count)
  }
}
$scannedCopies = @($found | Where-Object { $_.Scanned }).Count
if ($found.Count -eq 0) {
  Write-Host ("VERDICT - no bundle with class ID tail '{0}' is on disk under these roots: not installed, or" -f $wantTail)
  Write-Host '          installed somewhere this list does not look. A placement answer, not a build defect.'
} elseif ($found.Count -eq 1 -and $scannedCopies -eq 1) {
  Write-Host 'VERDICT - one copy, in a root this host reads. That is the placement the product rule asks for.'
} elseif ($found.Count -eq 1) {
  Write-Host 'VERDICT - one copy, in a folder no root of this host reads, so the host will not offer it until it'
  Write-Host '          is pointed at that folder or the bundle moves to a scanned root.'
} else {
  Write-Host ("VERDICT - {0} copies of one class ID on disk, {1} of them in a root this host reads. The host" -f $found.Count, $scannedCopies)
  Write-Host '          cannot see the rest, which is how a recognition check stays green on a machine carrying'
  Write-Host '          two. One bundle, one place: retire the extra bundle, never a scan path the host owns.'
  exit 1
}
if ($targets.Count -gt 1) {
  Write-Host ''
  Write-Host ("{0} caches read; the newest is first. An older cache is evidence about the host that wrote it, not about today." -f $targets.Count)
}
exit 0
