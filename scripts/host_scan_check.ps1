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
    Write-Host 'VERDICT - neither the name nor the class ID is in this cache. Install, then make the host rescan;'
    Write-Host ("         the file rewrites only on a scan, and it is {0} min old." -f $ageMin)
  }
}
if ($targets.Count -gt 1) {
  Write-Host ''
  Write-Host ("{0} caches read; the newest is first. An older cache is evidence about the host that wrote it, not about today." -f $targets.Count)
}
exit 0
