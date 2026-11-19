# One exit code for "this is releasable".
#
# Every stage below is something this repository already knows how to check; what was missing is
# a command that owns the answer. `build_installer.ps1` exits 0 when it produced a deliverable,
# which is a different claim: it does not run the test suite, does not build the interface,
# builds one JUCE tree because the second needs its own build directory, and cannot tell you
# whether the licence page still holds a `<<<FILL:` placeholder or whether the checksums match
# the bytes sitting next to them.
#
# READY requires every selected stage to have run and passed. A stage that could not run - no
# second JUCE checkout, no sha256sum, no elevation for the install cycle - is INCOMPLETE, never
# a pass, and that is why skipped stages keep their own row instead of being left out of the
# list. Exit 0 is READY, 1 is a failed stage, 2 is a skipped one: a code a script can branch on
# and a human can read.
#
#   powershell -File scripts\release_check.ps1                    # everything
#   powershell -File scripts\release_check.ps1 -Stages gate,licence
#   powershell -File scripts\release_check.ps1 -Fast              # the cheap gates
#
# Evidence is one log per stage in build\work\release-check-<utc>\, and the folder is printed at
# the end: a verdict nobody can inspect is just a claim.
#
#Requires -Version 5.1
[CmdletBinding()]
param(
    [string[]] $Stages,
    [switch] $Fast,
    [string] $Evidence
)

$ErrorActionPreference = 'Continue'
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Repo

$all = @('gate', 'suite', 'web', 'plugin', 'plugin808', 'installer', 'stamp',
         'smoke', 'checksums', 'licence', 'installed')

if (-not $Stages) {
    $Stages = if ($Fast) { @('gate', 'suite', 'licence', 'checksums') } else { $all }
}

# -File gives a [string[]] parameter one element per space-separated argument, so the documented
# `-Stages gate,licence` arrives as the single string "gate,licence" and every name in it reads
# as unknown. Split it here, which also keeps `-Stages gate -Stages licence` working.
$Stages = @($Stages | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } |
    Where-Object { $_ })

# An empty selection would run no stages, and "nothing failed" would print READY. Refuse instead.
if (-not $Stages.Count) {
    Write-Host 'no stages selected (an empty -Stages list would pass by checking nothing)'
    Write-Host ("known stages:     " + ($all -join ', '))
    exit 1
}

$unknown = @($Stages | Where-Object { $all -notcontains $_ })
if ($unknown.Count) {
    Write-Host ("unknown stage(s): " + ($unknown -join ', '))
    Write-Host ("known stages:     " + ($all -join ', '))
    exit 1
}

$stampDir = if ($Evidence) { $Evidence } else {
    Join-Path $Repo ('build\work\release-check-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss'))
}
New-Item -ItemType Directory -Force -Path $stampDir | Out-Null
$results = New-Object System.Collections.Generic.List[object]

function Add-Result([string]$Name, [string]$State, [string]$Detail) {
    $results.Add([pscustomobject]@{ Stage = $Name; State = $State; Detail = $Detail }) | Out-Null
    $mark = if ($State -eq 'PASS') { 'ok  ' } elseif ($State -eq 'SKIP') { 'SKIP' } else { 'FAIL' }
    Write-Host ("[$mark] $Name - $Detail")
}

# Runs a command with the whole output going to the stage log, and hands back the exit code the
# command itself reported. Redirected rather than piped: `| Select-String` would overwrite
# $LASTEXITCODE with the cmdlet's own success, which is how a red suite reads as green.
function Invoke-Step([string]$LogFile, [string]$File, [string[]]$Arguments) {
    & $File @Arguments *> $LogFile
    return $LASTEXITCODE
}

function Read-Log([string]$LogFile) {
    if (-not (Test-Path -LiteralPath $LogFile)) { return '' }
    return [System.IO.File]::ReadAllText($LogFile)
}

function Have-Tool([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# Twelve hex characters is enough to tell one digest from another and short enough to read in a
# table. Calling .Substring on a missing key would throw and take the whole stage with it.
function Short($Value) {
    $text = "$Value".Trim()
    if (-not $text) { return 'nothing' }
    if ($text.Length -le 12) { return $text }
    return $text.Substring(0, 12)
}

$versionText = [System.IO.File]::ReadAllText((Join-Path $Repo 'midivault\__init__.py'))
$releaseVersion = [regex]::Match($versionText, '(?m)^__version__ = "([^"]+)"\s*$').Groups[1].Value
if (-not $releaseVersion) {
    Write-Host 'NOT READY - midivault\__init__.py does not state __version__ in the expected form'
    exit 1
}

Write-Host ("release check " + [DateTime]::UtcNow.ToString('s') + 'Z, release ' +
            $releaseVersion + ', evidence ' + $stampDir)
Write-Host ("stages: " + ($Stages -join ', '))

# ---------------------------------------------------------------------------
# gates that cost seconds
# ---------------------------------------------------------------------------
if ($Stages -contains 'gate') {
    if (-not (Have-Tool 'python')) {
        Add-Result 'gate' 'SKIP' 'python is not on PATH'
    } else {
        $log = Join-Path $stampDir 'gate.log'
        $code = Invoke-Step $log 'python' @('scripts\check_version_consistency.py')
        $text = Read-Log $log
        # The checker's own last line is the verdict, in both directions: the coverage summary
        # when it agrees, and which literal broke when it does not. Carrying it into the row is
        # what makes a red gate readable without opening a log.
        $lines = @($text -split "\r?\n" | Where-Object { $_.Trim() })
        $says = if ($lines.Count) { $lines[-1] } else { 'the checker printed nothing' }
        $summary = [regex]::Match($text,
            '(?m)^(\d+ files, \d+ values, one version [.\d]+)').Groups[1].Value
        if ($code -eq 0 -and $summary) {
            Add-Result 'gate' 'PASS' $summary
        } else {
            Add-Result 'gate' 'FAIL' ("exit $code, says '$says' - see $log")
        }
    }
}

if ($Stages -contains 'suite') {
    if (-not (Have-Tool 'python')) {
        Add-Result 'suite' 'SKIP' 'python is not on PATH'
    } else {
        $log = Join-Path $stampDir 'suite.log'
        $code = Invoke-Step $log 'python' @('-m', 'unittest', 'discover', '-s', 'tests')
        $text = Read-Log $log
        $ran = [regex]::Match($text, 'Ran (\d+) tests').Groups[1].Value
        $outcome = if ($text -match '\bOK\b') { 'OK' } else {
            [regex]::Match($text, 'FAILED \([^)]*\)').Groups[0].Value
        }
        if ($code -eq 0 -and $ran -and $outcome -eq 'OK') {
            Add-Result 'suite' 'PASS' ("$ran tests, OK")
        } else {
            Add-Result 'suite' 'FAIL' ("exit $code, ran='$ran', outcome='$outcome' - see $log")
        }
    }
}

if ($Stages -contains 'licence') {
    $file = Join-Path $Repo 'packaging\EULA.txt'
    $text = [System.IO.File]::ReadAllText($file)
    $placeholders = @([regex]::Matches($text, '<<<FILL:[^>]*>>>') | ForEach-Object { $_.Value })
    $licenceVersion = [regex]::Match($text, '(?m)^\s*This version is ([.\d]+)\.\s*$').Groups[1].Value
    if ($placeholders.Count) {
        Add-Result 'licence' 'FAIL' ($placeholders.Count.ToString() +
            ' unfilled field(s): ' + ($placeholders -join ' '))
    } elseif ($licenceVersion -ne $releaseVersion) {
        Add-Result 'licence' 'FAIL' ("the licence page states '$licenceVersion', " +
            "the release is $releaseVersion")
    } else {
        Add-Result 'licence' 'PASS' "no placeholders, licence page states $licenceVersion"
    }
}

# Costs seconds, but its call site sits after the installer stage on purpose: build_installer.ps1
# rewrites SHA256SUMS.txt, so running this with the other fast gates only ever certifies the
# previous build's artifacts while the verdict below reports READY on bytes nobody has hashed.
function Test-Checksums {
    $manifest = Join-Path $Repo 'launch\SHA256SUMS.txt'
    if (-not (Test-Path -LiteralPath $manifest)) {
        Add-Result 'checksums' 'FAIL' "launch\SHA256SUMS.txt does not exist"
    } else {
        $launch = Join-Path $Repo 'launch'
        $text = [System.IO.File]::ReadAllText($manifest)
        $rows = @($text -split "\r?\n" | Where-Object { $_ -match '\S' })
        $problems = @()

        $listed = @()
        foreach ($row in $rows) {
            $parts = @($row -split '\s+', 2)
            if ($parts.Count -lt 2) { $problems += "malformed row: $row"; continue }
            $name = $parts[1].Trim()
            $listed += $name
            $target = Join-Path $launch ($name.TrimStart('*'))
            if (-not (Test-Path -LiteralPath $target)) { $problems += "missing file: $name"; continue }
            $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($actual -ne $parts[0].Trim().ToLowerInvariant()) { $problems += "hash differs: $name" }
        }

        # Both directions: a manifest naming something that is not this release's files, and a
        # release file present but not covered. The failure this project already had was a
        # manifest with no rows in it and exit code 0.
        $expected = @("SKEER-MIDI-VAULT-Setup-$releaseVersion.exe",
                      "SKEER-MIDI-VAULT-Portable-$releaseVersion.zip")
        $problems += @($listed | Where-Object { $expected -notcontains $_.TrimStart('*') } |
            ForEach-Object { "named but not a $releaseVersion release file: $_" })
        $onDisk = @(Get-ChildItem -LiteralPath $launch -File | Where-Object {
            $_.Name -match ('^SKEER-MIDI-VAULT-(Setup|Portable)-' +
                [regex]::Escape($releaseVersion) + '\.(exe|zip)$') })
        $problems += @($onDisk | Where-Object { $listed -notcontains $_.Name } |
            ForEach-Object { "release file missing from the manifest: $($_.Name)" })

        if ($text -match "`r") { $problems += 'CRLF in the manifest' }
        if (-not $rows.Count) { $problems += 'empty manifest' }

        # The publisher's own tool, run as an independent implementation rather than a copy of
        # the check above. It is not installed everywhere, so its absence is said out loud.
        $interop = 'sha256sum not available'
        $exe = $null
        if (Have-Tool 'sha256sum') { $exe = 'sha256sum' }
        else {
            foreach ($candidate in @('C:\Program Files\Git\usr\bin\sha256sum.exe',
                                     'C:\Program Files\Git\coreutils\bin\sha256sum.exe')) {
                if (Test-Path -LiteralPath $candidate) { $exe = $candidate; break }
            }
        }
        if ($exe) {
            $log = Join-Path $stampDir 'checksums.log'
            # coreutils resolves each row against the current directory, not against the manifest,
            # so this must run inside launch/. Run it from the repo root and it reports "No such
            # file or directory" against a flawless release - a permanently red row, which reads
            # exactly like a caught defect and never lets the verdict reach READY.
            Push-Location -LiteralPath $launch
            try { $code = Invoke-Step $log $exe @('-c', 'SHA256SUMS.txt') }
            finally { Pop-Location }
            $interop = if ($code -eq 0) { 'sha256sum -c exit 0' } else { "sha256sum -c exit $code" }
            if ($code -ne 0) { $problems += "sha256sum -c reported $code" }
        }

        $detail = ("{0} row(s), {1} release file(s) in launch/, {2}" -f
            $rows.Count, $onDisk.Count, $interop)
        if ($problems.Count) {
            Add-Result 'checksums' 'FAIL' ($detail + ' - ' + ($problems -join '; '))
        } else {
            Add-Result 'checksums' 'PASS' $detail
        }
    }
}

# ---------------------------------------------------------------------------
# the expensive stages
# ---------------------------------------------------------------------------
if ($Stages -contains 'web') {
    if (-not (Have-Tool 'npm')) {
        Add-Result 'web' 'SKIP' 'npm is not on PATH'
    } else {
        $log = Join-Path $stampDir 'web.log'
        $code = Invoke-Step $log 'npm' @('--prefix', 'web', 'run', 'build')
        $text = Read-Log $log
        $vite = if ($text -match 'built in') { ', vite reported a build' } else { ', vite said nothing' }
        if ($code -eq 0) {
            Add-Result 'web' 'PASS' ("tsc --noEmit and vite build, exit 0" + $vite)
        } else {
            Add-Result 'web' 'FAIL' ("exit $code - see $log")
        }
    }
}

function Plugin-Stage([string]$Name, [string]$BuildDir, [string]$Juce) {
    if (-not (Test-Path -LiteralPath $Juce)) {
        Add-Result $Name 'SKIP' "no JUCE tree at $Juce"
        return
    }
    if (-not (Have-Tool 'cmake')) {
        Add-Result $Name 'SKIP' 'cmake is not on PATH'
        return
    }
    # Not "$Name.log": inside a double-quoted string PowerShell reads `.log` as a property
    # access on the string, which yields nothing, and the stage would try to redirect its log
    # onto the evidence directory itself.
    $log = Join-Path $stampDir ($Name + '.log')
    $code = Invoke-Step $log 'powershell' @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        'plugin\build.ps1', '-BuildDir', $BuildDir, '-Juce', $Juce)
    $text = Read-Log $log
    # ctest drops the failure clause when nothing failed: a green run prints
    # "100% tests passed out of 6", a red one "67% tests passed, 2 tests failed out of 6".
    # Matching only the second form makes this stage permanently red, which looks exactly like
    # a caught defect and never lets the verdict reach READY.
    $ctest = [regex]::Match($text,
        '(\d+(?:\.\d+)?)% tests passed(?:,\s*(\d+) tests failed)?\s+out of\s+(\d+)')
    # Only "no summary at all" gets the -1 sentinel. A missing failure clause IS zero failures,
    # and defaulting it to -1 makes a green suite permanently red - which is indistinguishable
    # from a real failure when you are reading the verdict, and unreachable from a fix.
    $failed = if (-not $ctest.Success) { -1 }
              elseif ($ctest.Groups[2].Success) { [int]$ctest.Groups[2].Value }
              else { 0 }
    $total = if ($ctest.Success) { [int]$ctest.Groups[3].Value } else { 0 }
    if ($code -eq 0 -and $failed -eq 0 -and $total -ge 6) {
        Add-Result $Name 'PASS' ("ctest $total/$total passed in $BuildDir")
    } else {
        $said = if ($ctest.Success) { $ctest.Value } else { 'nothing that looks like a ctest summary' }
        Add-Result $Name 'FAIL' ("exit $code, ctest said '$said' - see $log")
    }
}

if ($Stages -contains 'plugin') {
    Plugin-Stage 'plugin' 'build' 'D:/Projects/skeer-audio/skulpt/external/JUCE'
}
if ($Stages -contains 'plugin808') {
    Plugin-Stage 'plugin808' 'build/tag-808' 'D:/Projects/skeer-audio/pulsekit/build/_deps/juce-src'
}

if ($Stages -contains 'installer') {
    $log = Join-Path $stampDir 'installer.log'
    $code = Invoke-Step $log 'powershell' @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        'packaging\build_installer.ps1')
    $setup = Join-Path $Repo "launch\SKEER-MIDI-VAULT-Setup-$releaseVersion.exe"
    $zip = Join-Path $Repo "launch\SKEER-MIDI-VAULT-Portable-$releaseVersion.zip"
    if ($code -eq 0 -and (Test-Path -LiteralPath $setup) -and (Test-Path -LiteralPath $zip)) {
        Add-Result 'installer' 'PASS' ("Setup {0} bytes, ZIP {1} bytes" -f
            (Get-Item -LiteralPath $setup).Length, (Get-Item -LiteralPath $zip).Length)
    } else {
        Add-Result 'installer' 'FAIL' ("exit $code, Setup $(Test-Path -LiteralPath $setup), " +
            "ZIP $(Test-Path -LiteralPath $zip) - see $log")
    }
}

# The one call site. With -Fast or -Stages the installer block above is skipped and this still
# runs, against whatever launch/ holds - the same thing the old position checked.
if ($Stages -contains 'checksums') { Test-Checksums }

if ($Stages -contains 'stamp') {
    $file = Join-Path $Repo 'build\BUILDINFO.json'
    $headLog = Join-Path $stampDir 'head.log'
    $info = $null
    $unreadable = $false
    if (Test-Path -LiteralPath $file) {
        try { $info = ConvertFrom-Json ([System.IO.File]::ReadAllText($file)) -ErrorAction Stop }
        catch { $unreadable = $true }
    }

    if (-not (Test-Path -LiteralPath $file)) {
        Add-Result 'stamp' 'FAIL' 'build\BUILDINFO.json is missing - run the installer stage'
    } elseif ($unreadable) {
        Add-Result 'stamp' 'FAIL' ("build\BUILDINFO.json is not readable JSON, so the bundle's " +
            'provenance cannot be checked: ' + $file)
    } elseif (-not "$($info.commit)") {
        # A well-formed file with no commit key would otherwise be quoted back as "the build
        # names  but HEAD is ..." - a true statement nobody can act on.
        Add-Result 'stamp' 'FAIL' "build\BUILDINFO.json names no commit: $file"
    } elseif (-not (Have-Tool 'git')) {
        Add-Result 'stamp' 'SKIP' 'git is not on PATH, so the stamp cannot be re-derived'
    } else {
        $headCode = Invoke-Step $headLog 'git' @('rev-parse', 'HEAD')
        $head = (Read-Log $headLog).Trim()
        if ($headCode -ne 0) {
            Add-Result 'stamp' 'FAIL' "git rev-parse HEAD exited $headCode"
        } elseif ("$($info.commit)".Trim() -ne $head) {
            Add-Result 'stamp' 'FAIL' ('the build names ' + $info.commit + ' but HEAD is ' +
                $head + ' - the artifact is not this commit')
        } elseif ($info.dirty) {
            Add-Result 'stamp' 'FAIL' ('the build was made from a dirty tree: ' +
                (Short $info.status_digest) + ' status, ' + (Short $info.untracked_digest) + ' untracked')
        } else {
            Add-Result 'stamp' 'PASS' ('commit ' + (Short $info.commit) + ', clean, web/dist ' +
                (Short $info.web_dist))
        }
    }
}

if ($Stages -contains 'smoke') {
    if (-not (Have-Tool 'python')) {
        Add-Result 'smoke' 'SKIP' 'python is not on PATH'
    } else {
        $log = Join-Path $stampDir 'smoke.log'
        $code = Invoke-Step $log 'python' @('tests\test_packaged_smoke.py')
        $text = Read-Log $log
        $built = [regex]::Match($text, 'built from (\S+) (dirty|clean)')
        if ($code -eq 0 -and $text -match 'PASS packaged smoke test') {
            Add-Result 'smoke' 'PASS' ("exit 0, bundle built from " +
                "$(if ($built.Groups[1].Value) { $built.Groups[1].Value } else { 'an unstamped commit' })")
        } else {
            Add-Result 'smoke' 'FAIL' ("exit $code - see $log")
        }
    }
}

if ($Stages -contains 'installed') {
    $cycle = Join-Path $Repo 'packaging\install_cycle_check.ps1'
    if (-not (Test-Path -LiteralPath $cycle)) {
        Add-Result 'installed' 'SKIP' 'packaging\install_cycle_check.ps1 does not exist yet'
    } else {
        $log = Join-Path $stampDir 'installed.log'
        $code = Invoke-Step $log 'powershell' @('-NoProfile', '-ExecutionPolicy', 'Bypass',
            '-File', 'packaging\install_cycle_check.ps1')
        # The cycle script's own headline names the phase and the cause; "exit 2" does not, and this
        # is the row a person reads at 1am. 2 means it proved what it could and stopped, which is
        # INCOMPLETE for the verdict, never a pass.
        $headline = ''
        if (Test-Path -LiteralPath $log) {
            $headline = @(@(Get-Content -LiteralPath $log -ErrorAction SilentlyContinue) |
                Where-Object { $_ -match '^CYCLE ' }) | Select-Object -Last 1
        }
        if ($headline) { $headline = ($headline -replace '^CYCLE (FAILED|INCOMPLETE|OK) -? ?', '') }
        else { $headline = 'the cycle script printed no CYCLE line' }
        if ($code -eq 0) {
            Add-Result 'installed' 'PASS' 'install, launch, installed smoke, uninstall logged'
        } elseif ($code -eq 2) {
            Add-Result 'installed' 'SKIP' ("partial: $headline - full cycle needs a normal user " +
                "terminal; see $log")
        } else {
            Add-Result 'installed' 'FAIL' "$headline (exit $code, log $log)"
        }
    }
}

# ---------------------------------------------------------------------------
# verdict
# ---------------------------------------------------------------------------
$failed = @($results | Where-Object { $_.State -eq 'FAIL' })
$skipped = @($results | Where-Object { $_.State -eq 'SKIP' })
$passed = @($results | Where-Object { $_.State -eq 'PASS' })

Write-Host ''
Write-Host '  stage           state   detail'
foreach ($row in $results) {
    Write-Host ('  ' + $row.Stage.PadRight(14) + $row.State.PadRight(8) + $row.Detail)
}

$verdict = if ($failed.Count) { 'NOT READY' } elseif ($skipped.Count) { 'INCOMPLETE' } else { 'READY' }
Write-Host ''
Write-Host ("$verdict - " + ($passed.Count.ToString() + ' passed, ') +
            ($failed.Count.ToString() + ' failed, ') + ($skipped.Count.ToString() + ' skipped, ') +
            "of $($results.Count) stages, release $releaseVersion")
Write-Host "  evidence: $stampDir"
foreach ($row in $skipped) { Write-Host ('  not verified: ' + $row.Stage + ' - ' + $row.Detail) }

if ($failed.Count) { exit 1 }
if ($skipped.Count) { exit 2 }
exit 0
