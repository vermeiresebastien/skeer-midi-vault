<#
.SYNOPSIS
  Read the version out of a built VST3 bundle's bytes and require it to equal the application's.
.DESCRIPTION
  scripts/check_version_consistency.py proves the seven *declared* literals agree, and for the plug-in
  that is the declaration CMake hands to two different writers: the VST3 SDK's module-info writer, whose
  output is regenerated on every build, and juceaide's Windows version resource, whose custom command
  declares no dependency on the info file that carries the version. The first tracked every bump, the
  second froze at whichever configure first created the file, and 1.1.2 shipped with moduleinfo.json
  reading 1.1.2 beside a binary whose PE FileVersion and ProductVersion still read 1.0.0. A source-side
  gate cannot see that, because nothing in the source was wrong.
  So this reads the artifact. PE fields come through the shell's own version-API wrapper - the same one
  Explorer's Properties page and a host's About box use - and moduleinfo.json is matched on its first
  Version field, the module's, because JUCE writes trailing commas that a strict JSON parser rejects and
  because a class row would agree with a wrong module row anyway.
  The application version is read out of midivault/__init__.py rather than repeated here, which is the
  same rule the plug-in's vendor codes follow in packaging/host_scan_check.ps1's description: a number
  copied into a checker is a second source of truth that can go stale on its own.
  Absence is a failure, never a skip. A missing bundle, a missing version resource, a missing
  moduleinfo.json or an unreadable __init__.py each print which one and exit 1, because the lazy way to
  green this gate is to point it at a folder that has nothing in it.
.EXAMPLE
  powershell -File scripts/check_plugin_version.ps1 -Bundle "launch\VST3\SKEER MIDI VAULT.vst3"
#>
param(
    [Parameter(Mandatory = $true)][string] $Bundle
)

$ErrorActionPreference = "Stop"

function Fail([string] $why) {
    Write-Output ("plugin-version FAIL - " + $why)
    exit 1
}

if (-not (Test-Path -LiteralPath $Bundle -PathType Container)) {
    Fail ("no bundle directory at " + $Bundle)
}

$dll = Get-ChildItem -LiteralPath $Bundle -Recurse -File -Filter "*.vst3" | Select-Object -First 1
if (-not $dll) { Fail ("no VST3 binary inside " + $Bundle) }

$moduleinfoPath = Join-Path (Split-Path $dll.Directory.FullName -Parent) "Resources\moduleinfo.json"
if (-not (Test-Path -LiteralPath $moduleinfoPath)) {
    Fail ("no moduleinfo.json beside " + $dll.FullName)
}

$initPath = Join-Path (Split-Path $PSScriptRoot -Parent) "midivault\__init__.py"
$declared = Select-String -LiteralPath $initPath -Pattern '__version__ = "([^"]+)"' | Select-Object -First 1
if (-not $declared) { Fail ("no __version__ literal in " + $initPath) }
$appVersion = $declared.Matches[0].Groups[1].Value

$moduleinfo = Select-String -LiteralPath $moduleinfoPath -Pattern '"Version":\s*"([^"]+)"' | Select-Object -First 1
if (-not $moduleinfo) { Fail ("no Version field in " + $moduleinfoPath) }
$moduleVersion = $moduleinfo.Matches[0].Groups[1].Value

$info = $dll.VersionInfo
$fileVersion = [string] $info.FileVersion
$productVersion = [string] $info.ProductVersion

$bad = @()
if ($fileVersion -ne $appVersion) { $bad += ("PE FileVersion [" + $fileVersion + "]") }
if ($productVersion -ne $appVersion) { $bad += ("PE ProductVersion [" + $productVersion + "]") }
if ($moduleVersion -ne $appVersion) { $bad += ("moduleinfo Version [" + $moduleVersion + "]") }

if ($bad.Count -gt 0) {
    Fail ("application version is " + $appVersion + " but " + ($bad -join ", ") + " in " + $dll.FullName)
}

Write-Output ("plugin-version PASS - PE FileVersion, PE ProductVersion and moduleinfo Version all " +
    $appVersion + " in " + $dll.FullName)
exit 0
