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
.EXAMPLE
  powershell -File scripts/host_scan_check.ps1
  powershell -File scripts/host_scan_check.ps1 -CacheFile "$env:APPDATA\Ableton\Live 12.3.2\Preferences\PluginScanDb.txt"
#>
[CmdletBinding()]
param(
  [string]$CacheFile,
  [string]$BundleName = 'SKEER MIDI VAULT'
)

$ErrorActionPreference = 'Stop'
$roots = @(
  [pscustomobject]@{ Label = 'shared (where 1.1.1 installs)'; Lit = 'C:\Program Files\Common Files\VST3' },
  [pscustomobject]@{ Label = 'old    (where 1.1.0 installed)'; Lit = 'C:\Program Files\VST3\' }
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

  Write-Host ''
  Write-Host $t.FullName
  Write-Host ("  last written {0}   rows={1}" -f $t.LastWriteTime, $rows)
  Write-Host ("  rows naming the shared VST3 folder : {0}" -f $shared)
  Write-Host ("  rows naming the old VST3 folder    : {0}" -f $old)
  Write-Host ("  rows naming '{0}' : {1}" -f $BundleName, $ours)

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

  if ($ours -gt 0) {
    Write-Host 'VERDICT - the scan has seen our bundle. That is recognition, not a load: a track still has to instantiate it.'
  } else {
    Write-Host 'VERDICT - our bundle is not in this cache. Install, then make the host rescan; this file rewrites only on a scan.'
  }
}
if ($targets.Count -gt 1) {
  Write-Host ''
  Write-Host ("{0} caches read; the newest is first. An older cache is evidence about the host that wrote it, not about today." -f $targets.Count)
}
exit 0
