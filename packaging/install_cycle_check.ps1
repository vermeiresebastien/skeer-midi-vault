# Install the built Setup, run what got installed, uninstall it, and prove nothing was left behind.
#
# tests\test_packaged_smoke.py drives the bundle in launch/, and that is not the artifact a user
# runs. The Setup relocates the tree, registers an uninstaller and writes shortcuts, and any of
# that can be wrong while the bundle beside it works perfectly. This is the only check that reads
# the bytes a double-click actually produces.
#
# It is destructive by nature, so it is constrained:
#
#   * it installs into its own folder under %LOCALAPPDATA%\SKEER MIDI VAULT cycle\, never the
#     default {autopf} location, so an existing install is not overwritten;
#   * it refuses to run while a SKEER MIDI VAULT entry is registered in Add/Remove Programs,
#     because Inno keys that entry by AppId: uninstalling the test copy would take the existing
#     install's entry with it. -Existing says you accept that;
#   * it refuses to run while the desktop app is up, and does not close it for you;
#   * the deliverable is the user's library, so the shared all-users VST3 folder is censused
#     before and after - a per-user install must not have touched it;
#   * every directory, shortcut, registry key and library folder is compared against the state
#     captured before, so "left nothing behind" means back to how it was, not "probably gone".
#
#   powershell -File packaging\install_cycle_check.ps1
#   powershell -File packaging\install_cycle_check.ps1 -KeepInstall   # leave it installed to poke at
#   powershell -File packaging\install_cycle_check.ps1 -FilesOnly -Dir D:\somewhere\empty
#   powershell -File packaging\install_cycle_check.ps1 -AllUsers      # elevated prompt only
#   powershell -File packaging\install_cycle_check.ps1 -WithShortcuts # assert the icons too
#
# By default the two shortcut tasks are declined, so the run needs no write in the user's real
# Start Menu or on the desktop and the shortcuts row grades that absence. -WithShortcuts is the
# customer-facing leg: it lets both tasks run, requires the two .lnk files at the paths the [Icons]
# section actually declares, and the uninstall comparison then proves they were removed again.
#
# -AllUsers runs the machine-wide leg: Setup gets /ALLUSERS (the script allows the override at
# packaging\skeer-midi-vault.iss:36), the shared-folder phase then requires the bundle to appear in
# C:\Program Files\Common Files\VST3 and requires that nothing else in that folder moved, and the
# uninstall phase already requires the folder back exactly as it was found. It refuses in preflight
# rather than half-installing when the terminal is not elevated, and it refuses alongside -FilesOnly
# because grading a copy this shell is not allowed to make is not evidence of anything.
#
# -FilesOnly is for a shell whose child processes are refused the writes an installer must make -
# the uninstall key in HKCU, a folder in %LOCALAPPDATA%. It grades the [Files] section from the
# Setup log, marks the register/launch/uninstall phases SKIP, and exits 2: never 0. The full cycle
# is only ever reported by a run that actually completed it.
#
# Evidence: one log per phase plus the before/after census in build\work\install-cycle-<utc>\.
# Exit 0 only if every phase passed.

#Requires -Version 5.1
[CmdletBinding()]
param(
    [switch] $KeepInstall,
    [switch] $Existing,
    [switch] $FilesOnly,
    [switch] $AllUsers,
    [switch] $WithShortcuts,
    [string] $Dir
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Repo
$AppName = 'SKEER MIDI VAULT'
$ExeName = 'SKEER MIDI VAULT.exe'
$MutexName = 'Local\SkeerMidiVaultDesktopV1'

$versionText = [System.IO.File]::ReadAllText((Join-Path $Repo 'midivault\__init__.py'))
$Version = [regex]::Match($versionText, '(?m)^__version__ = "([^"]+)"\s*$').Groups[1].Value
if (-not $Version) { throw 'midivault\__init__.py does not state __version__ in the expected form' }

$Evidence = Join-Path $Repo ('build\work\install-cycle-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force -Path $Evidence | Out-Null

$CycleRoot = Join-Path $env:LOCALAPPDATA 'SKEER MIDI VAULT cycle'
$InstallDir = Join-Path $CycleRoot $Version
if ($Dir) {
    # -Dir is for a shell that is refused its own %LOCALAPPDATA% by policy: the install still goes
    # somewhere nothing else lives, and the root removal below is bounded to that folder.
    if (-not [System.IO.Path]::IsPathRooted($Dir)) {
        throw "-Dir must be an absolute path, got $Dir"
    }
    $InstallDir = $Dir
    $CycleRoot = $Dir
}
$Setup = Join-Path $Repo ("launch\SKEER-MIDI-VAULT-Setup-$Version.exe")
$BundleExe = Join-Path $Repo "launch\$AppName\$ExeName"
# The [Icons] section declares {autoprograms}\SKEER AUDIO\{AppName} and {autodesktop}\{AppName},
# so the group folder is the publisher, not the app, and both roots move with the install mode:
# {autoprograms} is the user's Start Menu for a per-user Setup and ProgramData's for /ALLUSERS.
if ($AllUsers) {
    $StartRoot = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs'
    $Desktop = [Environment]::GetFolderPath('CommonDesktopDirectory')
} else {
    $StartRoot = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
    $Desktop = [Environment]::GetFolderPath('Desktop')
}
$StartLnk = Join-Path $StartRoot ('SKEER AUDIO\' + $AppName + '.lnk')
$DesktopLnk = Join-Path $Desktop ($AppName + '.lnk')
$UserLib = Join-Path $env:LOCALAPPDATA 'Skeer\MIDI Vault'
$SystemVst3 = Join-Path ${env:ProgramFiles} 'Common Files\VST3'

$rows = New-Object System.Collections.Generic.List[object]

function Add-Row([string]$Phase, [string]$State, [string]$Detail) {
    $rows.Add([pscustomobject]@{ Phase = $Phase; State = $State; Detail = $Detail }) | Out-Null
    $mark = if ($State -eq 'PASS') { 'ok  ' } elseif ($State -eq 'SKIP') { 'SKIP' } else { 'FAIL' }
    Write-Host ("[$mark] $Phase - $Detail")
}

function Failed-Count {
    return @($rows | Where-Object { $_.State -eq 'FAIL' }).Count
}

function End-Cycle {
    $failed = Failed-Count
    $skipped = @($rows | Where-Object { $_.State -eq 'SKIP' }).Count
    Write-Host ''
    Write-Host '  phase            state   detail'
    foreach ($row in $rows) {
        Write-Host ('  ' + $row.Phase.PadRight(15) + $row.State.PadRight(7) + $row.Detail)
    }
    Write-Host ''
    Write-Host "evidence: $Evidence"
    if ($failed) {
        Write-Host "CYCLE FAILED - $failed phase(s) failed, $skipped skipped, of $($rows.Count)"
        exit 1
    }
    if ($skipped) {
        Write-Host "CYCLE INCOMPLETE - $skipped phase(s) skipped, of $($rows.Count)"
        exit 2
    }
    Write-Host ('CYCLE OK - ' + $rows.Count +
                ' phases passed: preflight, install, payload, provenance, plug-in, shortcuts, ' +
                'shared folder, installed run, uninstall')
    exit 0
}

function Hash([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

# Folder identity as name, size and timestamp per file. This is the cheap form and it is the
# right one for the shared plug-in folder: the claim being tested is "the installer wrote
# nothing here", and a file that gained bytes or a new name cannot hide behind a hash. Content
# identity, where that is the claim, is tested with SHA-256 on the specific files below.
function Census([string]$Root) {
    $map = @{}
    if (-not (Test-Path -LiteralPath $Root)) {
        $map['<absent>'] = $Root
        return $map
    }
    foreach ($file in @(Get-ChildItem -LiteralPath $Root -File -Recurse -ErrorAction SilentlyContinue)) {
        $relative = $file.FullName.Substring($Root.Length).TrimStart('\')
        $map[$relative] = "$($file.Length)|$($file.LastWriteTimeUtc.Ticks)"
    }
    return $map
}

function Census-Diff([hashtable]$Before, [hashtable]$After) {
    $diff = @()
    foreach ($key in $After.Keys) {
        if (-not $Before.ContainsKey($key)) { $diff += "added: $key" }
        elseif ($Before[$key] -ne $After[$key]) { $diff += "changed: $key" }
    }
    foreach ($key in $Before.Keys) {
        if (-not $After.ContainsKey($key)) { $diff += "removed: $key" }
    }
    return $diff
}

function UninstallEntries {
    $roots = @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
               'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
               'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')
    $found = @()
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        $found += @(Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue |
            Get-ItemProperty -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -like "$AppName*" } |
            Select-Object DisplayName, DisplayVersion, InstallLocation, UninstallString)
    }
    return $found
}

function Wait-For([scriptblock]$Test, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Test) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return [bool](& $Test)
}

# Native commands write to stderr as part of normal speech, and PowerShell turns a redirected
# stderr line into an error record when the preference is Stop. This project's smoke test prints
# one such line on shutdown, so a Stop-preference wrapper would abort the phase over a message
# that meant nothing. Run the child with the preference the child expects.
function Invoke-Child([string]$LogFile, [scriptblock]$Run) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Run *> $LogFile
        return $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
}

# Start-Process goes through ShellExecute, and ShellExecute consults the attachment manager,
# which on this machine raised a modal "Open File - Security Warning" for an unsigned Setup. A
# headless check cannot see that dialog, let alone answer it, so the cycle hung on it with no
# output and no exit code. CreateProcess does not consult the attachment manager, so the
# installer gets the same arguments and the wait gets a real ExitCode. The dialog a user sees
# when double-clicking an unsigned download is a signing matter (see -Sign), not something this
# script should reproduce: it tests the installer, not the shell.
function Invoke-Installer([string]$Path, [string[]]$Arguments) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Path
    $psi.Arguments = ($Arguments -join ' ')
    # SetupLdr extracts to GetTempPath() before it does anything else, and a child of this shell
    # is refused that: the Setup log said 'unable to create the directory
    # %TEMP%\is-XXXX.tmp - Error 5' and it died without writing a line of its own log. Point the
    # child at a temp inside the evidence folder, which it can create. The extraction location is
    # not part of what is being tested; the installed tree is.
    $childTemp = Join-Path $Evidence 'tmp'
    New-Item -ItemType Directory -Force -Path $childTemp | Out-Null
    $psi.EnvironmentVariables['TMP'] = $childTemp
    $psi.EnvironmentVariables['TEMP'] = $childTemp
    $psi.UseShellExecute = $false
    $psi.WorkingDirectory = $Repo
    $proc = [System.Diagnostics.Process]::Start($psi)
    $proc.WaitForExit()
    return $proc.ExitCode
}

# When Setup fails, the exit code alone is not evidence of anything: 1 and 4 both come out of a
# rollback that was caused by the machine, not by the installer. The Setup log names the cause,
# so quote it back instead of guessing at it.
function Setup-Cause([string]$LogPath) {
    if (-not (Test-Path -LiteralPath $LogPath)) { return 'Setup exited without writing a log' }
    $lines = @(Get-Content -LiteralPath $LogPath -ErrorAction SilentlyContinue)
    $pattern = 'Fatal exception|Error creating registry key|unable to create the directory|' +
               'Not enough privileges|corrupted|Log closed'
    $hit = $lines | Where-Object { $_ -match $pattern -and $_ -notmatch 'Log closed' } | Select-Object -First 1
    if (-not $hit) { return 'no named cause in ' + (Split-Path $LogPath -Leaf) }
    $i = [array]::IndexOf($lines, $hit)
    # Setup narrates one exception over an indented block, and the row that tells a refused shell
    # from a broken installer - "Error 5: Access is denied." - sits two rows under the line the
    # pattern caught, with a blank between. So walk on while the rows belong to this record: a new
    # timestamped row is the next event, not part of the cause.
    $context = @($lines[$i])
    for ($j = $i + 1; $j -lt $lines.Count -and $context.Count -lt 4; $j++) {
        if ($lines[$j] -match '^\s*\d{4}-\d{2}-\d{2} ') { break }
        if ($lines[$j] -match '\S') { $context += ($lines[$j] -replace '^\s+', '') }
    }
    $context = ($context -join ' ') -replace '\s+', ' '
    if ($context.Length -gt 260) { $context = $context.Substring(0, 260) + '...' }
    return $context.Trim()
}

# Setup's log is a narration: a 'Dest filename' line, then either 'Successfully installed the
# file.' or a refusal. Pairing them is what turns the log into a list of delivered paths, which is
# the only payload evidence available after a rollback has deleted the tree from disk.
function Installed-Dests([string]$LogPath) {
    $dests = New-Object System.Collections.Generic.List[string]
    if (-not (Test-Path -LiteralPath $LogPath)) { return $dests }
    $pending = $null
    foreach ($line in @(Get-Content -LiteralPath $LogPath -ErrorAction SilentlyContinue)) {
        if ($line -match '-- File entry --') { $pending = $null }
        elseif ($line -match 'Dest filename: (.+?)\s*$') { $pending = $Matches[1] }
        elseif ($line -match 'Successfully installed the file' -and $pending) {
            $dests.Add($pending); $pending = $null
        }
    }
    return $dests
}

# An install is not an install until it has registered itself, and that write happens after every
# file has been copied - so a shell whose child processes cannot write there produces a rollback
# that looks like a broken installer. Find that out from a child process, before spending two
# minutes unpacking 230 MB. reg.exe is a different image from Setup, so this proves the account
# can; only the run below proves that Setup itself can.
function Child-Can-Register {
    $probe = 'HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\SKEER Cycle Probe'
    $code = Invoke-Installer "$env:SystemRoot\System32\reg.exe" `
        @('add', ('"' + $probe + '"'), '/v', 'Probe', '/t', 'REG_SZ', '/d', '1', '/f')
    if ($code -ne 0) { return "refused (reg.exe exit $code)" }
    [void](Invoke-Installer "$env:SystemRoot\System32\reg.exe" @('delete', ('"' + $probe + '"'), '/f'))
    return 'allowed'
}

Write-Host "install cycle $Version - evidence $Evidence"
Write-Host "installs into $InstallDir, not the default location"

# ---------------------------------------------------------------------------
# 1. Refuse before touching anything.
# ---------------------------------------------------------------------------
if (-not (Test-Path -LiteralPath $Setup)) {
    Add-Row 'preflight' 'FAIL' "$Setup does not exist - run packaging\build_installer.ps1 first"
} else {
    $manifestRows = @(@(Get-Content -LiteralPath (Join-Path $Repo 'launch\SHA256SUMS.txt') `
        -ErrorAction SilentlyContinue) | Where-Object { $_ -like "*SKEER-MIDI-VAULT-Setup-$Version.exe" })
    $setupHash = Hash $Setup
    $setupBytes = (Get-Item -LiteralPath $Setup).Length
    if ($manifestRows.Count -ne 1) {
        Add-Row 'preflight' 'FAIL' "the manifest names $($manifestRows.Count) rows for the $Version Setup"
    } elseif ((@($manifestRows[0] -split '\s+'))[0].ToLowerInvariant() -ne $setupHash) {
        Add-Row 'preflight' 'FAIL' "the Setup on disk ($setupHash) is not the one SHA256SUMS.txt describes"
    } else {
        Add-Row 'preflight' 'PASS' "Setup $setupBytes bytes, hash matches the manifest"
    }

    $running = @(Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq 'SKEER MIDI VAULT' })
    $mutex = $null
    try { $mutex = [System.Threading.Mutex]::OpenExisting($MutexName) } catch { $mutex = $null }
    if ($running.Count -or $mutex) {
        if ($mutex) { $mutex.Close() }
        Add-Row 'preflight' 'FAIL' ("$AppName is running (process(es): $($running.Count), " +
            'mutex held: True) - close it from its tray icon or Settings; this check will not ' +
            'close your application for you')
    } else {
        Add-Row 'preflight' 'PASS' 'no running instance and no mutex holder'
    }

    $beforeEntries = @(UninstallEntries)
    if ($beforeEntries.Count -and -not $Existing) {
        Add-Row 'preflight' 'FAIL' ('Add/Remove Programs already lists ' +
            (($beforeEntries | ForEach-Object { $_.DisplayName }) -join ', ') +
            ' - the test uninstalls by AppId and would take that entry with it. Uninstall it ' +
            'first, or pass -Existing to accept that.')
    } elseif ($beforeEntries.Count) {
        Add-Row 'preflight' 'PASS' 'an existing registration is present and -Existing was passed'
    } else {
        Add-Row 'preflight' 'PASS' 'nothing registered under this AppId yet'
    }

    $register = Child-Can-Register
    if ($register -eq 'allowed') {
        Add-Row 'preflight' 'PASS' 'a child process of this shell may write HKCU\...\Uninstall'
    } else {
        Add-Row 'preflight' 'FAIL' ("a child process of this shell cannot register an uninstall " +
            "entry ($register) - Setup would copy every file and then roll back, which is not " +
            'evidence about the installer. Run this script from a normal user terminal instead.')
    }
}

if ($AllUsers) {
    # Elevation is checked here, not discovered halfway through an install that already copied
    # 198 files: a machine-wide Setup refused its VST3 folder would leave a registered install
    # with no plug-in in it, which is the worst artifact this check could produce.
    $principal = New-Object Security.Principal.WindowsPrincipal(
        [Security.Principal.WindowsIdentity]::GetCurrent())
    if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Add-Row 'preflight' 'PASS' ('-AllUsers: this terminal is elevated, so the machine-wide ' +
            'leg may run and the shared VST3 copy will be graded')
    } else {
        Add-Row 'preflight' 'FAIL' ('-AllUsers needs an elevated terminal - this one is not admin, ' +
            "so Setup would be refused $SystemVst3 after it had already written elsewhere. Run this " +
            'check from an elevated prompt; the per-user leg needs no switch.')
    }
    if ($FilesOnly) {
        Add-Row 'preflight' 'FAIL' ('-AllUsers and -FilesOnly contradict each other: one asks for ' +
            'the shared machine-wide copy, the other grades a copy made without writing outside a ' +
            'folder it was handed.')
    }
}

if ((Failed-Count) -gt 0) {
    Write-Host ''
    Write-Host 'CYCLE NOT RUN - preflight refused; nothing was installed'
    exit 1
}

# ---------------------------------------------------------------------------
# 2. State before, so "left nothing behind" is a comparison rather than a hope.
# ---------------------------------------------------------------------------
$before = [ordered]@{
    install_dir    = (Test-Path -LiteralPath $InstallDir)
    desktop_lnk    = (Test-Path -LiteralPath $DesktopLnk)
    start_lnk      = (Test-Path -LiteralPath $StartLnk)
    user_lib       = (Test-Path -LiteralPath $UserLib)
    uninstall_rows = $beforeEntries.Count
}
$vst3Before = Census $SystemVst3
$before | ConvertTo-Json | Out-File -FilePath (Join-Path $Evidence 'before.json') -Encoding UTF8
@{ root = $SystemVst3; files = $vst3Before } | ConvertTo-Json -Depth 4 |
    Out-File -FilePath (Join-Path $Evidence 'census-before.json') -Encoding UTF8
Write-Host ('before: install dir ' + $before.install_dir + ', desktop shortcut ' +
            $before.desktop_lnk + ', start menu ' + $before.start_lnk + ', user library ' +
            $before.user_lib + ', shared VST3 entries ' + $vst3Before.Count)

# ---------------------------------------------------------------------------
# 3. Install, silently, into the cycle folder.
#
# /DIR and /LOG are quoted inside the argument, not by it: these paths contain spaces, and how
# PowerShell 5.1 rebuilds a command line from an argument array is not something an installer
# should be trusted to guess. The assertion below is that the tree landed exactly at $InstallDir,
# so a mis-parsed path cannot pass.
# ---------------------------------------------------------------------------
$setupLog = Join-Path $Evidence 'setup-install.log'
$installArgs = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                 ('/DIR="' + $InstallDir + '"'), ('/LOG="' + $setupLog + '"'))
if (-not $WithShortcuts) { $installArgs = @('/MERGETASKS=!startmenuicon,!desktopicon') + $installArgs }
# The two shortcut tasks are declined unless -WithShortcuts says otherwise, because this is a
# throwaway install that the script uninstalls again: a Start Menu entry and a desktop icon would be
# written into the user's real shell, point at a folder this run is about to delete, and the
# uninstaller's own "left nothing behind" comparison would then be grading shortcuts it had to clean
# up after a test that never needed them. It also happens to remove the two out-of-workspace writes
# that a restricted shell refuses Setup -- measured
# 2026-11-19 on the shipped Setup, the payload copied 198/198 into a -Dir inside the repo and Setup
# then died at Start Menu (Error 5, exit 4) before it ever reached the uninstall key. The [Icons]
# entries stay declared in packaging\skeer-midi-vault.iss:98-99, and a wizard run still makes its own
# choice about them; a silent install of a throwaway copy simply declines them.
# /ALLUSERS is legal because the script sets PrivilegesRequiredOverridesAllowed=commandline; the
# uninstaller inherits the install mode from its own registration, so it gets no switch.
if ($AllUsers) { $installArgs = @('/ALLUSERS') + $installArgs }
$setupExit = Invoke-Installer $Setup $installArgs
$installedExe = Join-Path $InstallDir $ExeName
$cause = if ($setupExit -ne 0) { Setup-Cause $setupLog } else { '' }
if ($setupExit -ne 0 -and -not $FilesOnly) {
    Add-Row 'install' 'FAIL' ("Setup exited $setupExit after copying " +
        "$(@(Installed-Dests $setupLog).Count) file(s) - $cause (log: $setupLog)")
    Write-Host ''
    # release_check's `installed` row quotes this headline and nothing else, so the cause belongs
    # here: "Setup did not install" on its own reads like a broken installer, and the far more
    # likely reason - this shell refusing Setup a folder - is a privilege note one line up.
    Write-Host "CYCLE FAILED - Setup did not install: $cause; evidence in $Evidence"
    Write-Host ('If that cause names a registry key, the Start Menu or "Access is denied", the ' +
                'shell running this check is the problem and not the installer: re-run it from a ' +
                'normal user terminal, or re-run with -FilesOnly to grade the payload copies only.')
    exit 1
} elseif (-not (Test-Path -LiteralPath $installedExe)) {
    if ($FilesOnly) {
        # Expected here: Setup rolls the tree back when it cannot finish registering, and the
        # destinations are graded from the log below rather than from a folder that is gone.
        Add-Row 'install' 'SKIP' "Setup exited $setupExit and rolled back; $cause"
    } else {
        Add-Row 'install' 'FAIL' "Setup exited $setupExit but there is no $ExeName in $InstallDir"
    }
} else {
    Add-Row 'install' 'PASS' ("Setup exit 0; $ExeName present, Setup log " +
        "$((Get-Item -LiteralPath $setupLog -ErrorAction SilentlyContinue).Length) bytes")
}

if ($FilesOnly) {
    # Grade the [Files] section from the Setup log, then stop. The log names every destination
    # Setup copied successfully, so a shell that cannot register an uninstall entry can still say
    # whether the payload relocates intact - and cannot claim anything beyond that.
    $dests = @(Installed-Dests $setupLog)
    $required = @($ExeName, '_internal\buildinfo\BUILDINFO.json', '_internal\web\dist\index.html',
                  'VST3\SKEER MIDI VAULT.vst3\Contents\x86_64-win\SKEER MIDI VAULT.vst3',
                  'VST3\SKEER MIDI VAULT.vst3\Contents\Resources\moduleinfo.json')
    $missing = @($required | Where-Object {
        $want = (Join-Path $InstallDir $_).ToLowerInvariant()
        -not @($dests | Where-Object { $_.ToLowerInvariant() -eq $want }).Count })

    # 199 destinations is only interesting against the payload they were supposed to be. launch/ is
    # the source of truth, so compare the two path sets: a [Files] line that stopped recursing, a
    # /DPluginStaged that was not passed, or a stray leftover in the bundle all show up here and
    # nowhere else. Inno's own two uninstaller files are the payload's not-launch/ exception.
    $expected = New-Object System.Collections.Generic.List[string]
    foreach ($pair in @(@{ root = (Join-Path $Repo "launch\$AppName"); prefix = '' },
                        @{ root = (Join-Path $Repo 'launch\VST3'); prefix = 'VST3\' })) {
        if (-not (Test-Path -LiteralPath $pair.root)) { continue }
        foreach ($f in @(Get-ChildItem -LiteralPath $pair.root -File -Recurse)) {
            $expected.Add(($pair.prefix + $f.FullName.Substring($pair.root.Length).TrimStart('\')).ToLowerInvariant())
        }
    }
    $outsideCmp = [System.StringComparison]::OrdinalIgnoreCase
    $outside = @($dests | Where-Object { -not $_.StartsWith($InstallDir, $outsideCmp) })
    $delivered = @($dests | Where-Object { $_.StartsWith($InstallDir, $outsideCmp) } |
        ForEach-Object { $_.Substring($InstallDir.Length).TrimStart('\').ToLowerInvariant() } |
        Where-Object { $_ -notmatch '^unins000\.(exe|dat)$' })
    $notDelivered = @($expected | Where-Object { $delivered -notcontains $_ })
    $extraDelivered = @($delivered | Where-Object { $expected -notcontains $_ })

    $refusal = ($cause -match 'registry|privile|Access is denied')
    $headline = $dests.Count.ToString() + ' file(s) installed, including the app, the stamp, the' +
        ' interface and the VST3 bundle'
    if ($expected.Count -lt 100) {
        Add-Row 'files' 'FAIL' ("launch/ holds only $($expected.Count) payload file(s) - nothing to " +
            'compare the install against; run packaging\build_installer.ps1 first')
    } elseif ($outside.Count) {
        Add-Row 'files' 'FAIL' ('Setup wrote ' + $outside.Count.ToString() +
            ' file(s) outside the requested directory, e.g. ' + (($outside | Select-Object -First 2) -join ', '))
    } elseif ($notDelivered.Count) {
        Add-Row 'files' 'FAIL' ($notDelivered.Count.ToString() + ' payload file(s) never installed, e.g. ' +
            (($notDelivered | Select-Object -First 4) -join ', '))
    } elseif ($extraDelivered.Count) {
        Add-Row 'files' 'FAIL' ('Setup installed ' + $extraDelivered.Count.ToString() +
            ' path(s) that launch/ does not hold, e.g. ' + (($extraDelivered | Select-Object -First 4) -join ', '))
    } elseif ($missing.Count) {
        Add-Row 'files' 'FAIL' ('no successful install line for: ' + ($missing -join ', '))
    } elseif ($dests.Count -lt 50) {
        Add-Row 'files' 'FAIL' ('the Setup log records only ' + $dests.Count.ToString() +
            ' installed file(s) for a payload of ' + $expected.Count + ' - ' + $cause)
    } elseif ($setupExit -eq 0) {
        Add-Row 'files' 'PASS' ($headline + " - all $($expected.Count) payload file(s), nothing extra")
    } elseif ($refusal) {
        Add-Row 'files' 'PASS' ($headline + " - all $($expected.Count) payload file(s), nothing extra," +
            ' and Setup could not finish registering')
        Add-Row 'register' 'SKIP' "this shell: $cause"
    } else {
        Add-Row 'files' 'FAIL' "Setup exited $setupExit for a reason that is not a privilege " +
            "refusal - $cause"
    }
    Add-Row 'cycle' 'SKIP' ('-FilesOnly: the Add/Remove Programs entry, the first launch of the ' +
        'installed executable and the uninstall comparison were not run. From a normal user ' +
        'terminal: powershell -File packaging\install_cycle_check.ps1')
    End-Cycle
}

if ((Failed-Count) -gt 0) {
    Write-Host ''
    Write-Host "CYCLE FAILED - Setup did not install; evidence in $Evidence"
    exit 1
}

# ---------------------------------------------------------------------------
# 4. What landed, and whether it is the payload launch/ holds.
# ---------------------------------------------------------------------------
$installedHash = Hash $installedExe
$bundleHash = Hash $BundleExe
if ($installedHash -eq $bundleHash) {
    Add-Row 'payload' 'PASS' "installed $ExeName is the same bytes as launch/"
} else {
    Add-Row 'payload' 'FAIL' "installed exe $installedHash differs from the bundle $bundleHash"
}

$stampIn = Get-Item -LiteralPath (Join-Path $InstallDir '_internal\buildinfo\BUILDINFO.json') `
    -ErrorAction SilentlyContinue
$stampBuilt = Get-Item -LiteralPath (Join-Path $Repo 'build\BUILDINFO.json') -ErrorAction SilentlyContinue
if (-not $stampIn) {
    Add-Row 'provenance' 'FAIL' 'the install carries no _internal\buildinfo\BUILDINFO.json'
} elseif (-not $stampBuilt) {
    Add-Row 'provenance' 'FAIL' 'build\BUILDINFO.json is gone; nothing to compare the install against'
} else {
    $inStamp = ConvertFrom-Json ([System.IO.File]::ReadAllText($stampIn.FullName))
    $builtStamp = ConvertFrom-Json ([System.IO.File]::ReadAllText($stampBuilt.FullName))
    if (-not "$($inStamp.commit)") {
        Add-Row 'provenance' 'FAIL' 'the installed stamp names no commit'
    } elseif ($inStamp.commit -ne $builtStamp.commit) {
        Add-Row 'provenance' 'FAIL' ("the install names $($inStamp.commit) but this build was " +
            "stamped $($builtStamp.commit)")
    } elseif ($inStamp.web_dist -ne $builtStamp.web_dist) {
        Add-Row 'provenance' 'FAIL' 'the installed interface digest differs from the stamp'
    } else {
        Add-Row 'provenance' 'PASS' ('installed stamp names commit ' +
            "$($inStamp.commit.Substring(0,12)) and the same interface digest")
    }
}

$pluginBinary = Join-Path $InstallDir `
    'VST3\SKEER MIDI VAULT.vst3\Contents\x86_64-win\SKEER MIDI VAULT.vst3'
$pluginInfo = Join-Path $InstallDir `
    'VST3\SKEER MIDI VAULT.vst3\Contents\Resources\moduleinfo.json'
if (-not (Test-Path -LiteralPath $pluginBinary)) {
    Add-Row 'plugin' 'FAIL' "no VST3 binary in the install at $pluginBinary"
} elseif (-not (Test-Path -LiteralPath $pluginInfo)) {
    Add-Row 'plugin' 'FAIL' 'the installed bundle has no moduleinfo.json'
} else {
    $stated = [regex]::Match([System.IO.File]::ReadAllText($pluginInfo),
        '"Version":\s*"([^"]+)"').Groups[1].Value
    $statedSize = (Get-Item -LiteralPath $pluginBinary).Length
    $stagedSize = (Get-Item -LiteralPath (Join-Path $Repo `
        'launch\VST3\SKEER MIDI VAULT.vst3\Contents\x86_64-win\SKEER MIDI VAULT.vst3') `
        -ErrorAction SilentlyContinue).Length
    if ($stated -ne $Version) {
        Add-Row 'plugin' 'FAIL' "the installed plug-in reports $stated, the release is $Version"
    } elseif ($statedSize -ne $stagedSize) {
        Add-Row 'plugin' 'FAIL' "installed plug-in is $statedSize bytes, staged is $stagedSize"
    } else {
        Add-Row 'plugin' 'PASS' "VST3 $stated at $statedSize bytes, as staged"
    }
}

# The shortcuts row grades what this run asked Setup to do, and nothing else: the default route
# declines both tasks, so a shortcut appearing is the defect there. -WithShortcuts runs them and
# requires both .lnk files at the declared paths - which is also the only route that can tell a
# correct expected path from a wrong one, because absence is what both produce.
$startNow = Test-Path -LiteralPath $StartLnk
$desktopNow = Test-Path -LiteralPath $DesktopLnk
Write-Host ('       shortcuts after install: start menu ' + $startNow + ', desktop ' + $desktopNow)
if ($WithShortcuts) {
    $absent = @()
    if (-not $startNow) { $absent += "start menu $StartLnk" }
    if (-not $desktopNow -and -not $before.desktop_lnk) { $absent += "desktop $DesktopLnk" }
    if ($absent.Count) {
        Add-Row 'shortcuts' 'FAIL' ('the shortcut tasks were not declined, but no ' +
            ($absent -join ' and no '))
    } else {
        Add-Row 'shortcuts' 'PASS' "start menu shortcut at $StartLnk, desktop shortcut at $DesktopLnk"
    }
} else {
    if ($startNow -or $desktopNow) {
        Add-Row 'shortcuts' 'FAIL' ('/MERGETASKS declined both tasks yet a shortcut exists: ' +
            "start menu $startNow, desktop $desktopNow")
    } else {
        Add-Row 'shortcuts' 'PASS' 'no Start Menu or desktop shortcut, as the declined tasks asked'
    }
}

# A per-user install must leave the shared all-users plug-in folder alone, and the installer says
# so in its own log: the claim is checked in the log and then proved against the folder itself.
if (-not (Test-Path -LiteralPath $setupLog)) {
    Add-Row 'shared-folder' 'FAIL' 'no Setup log, so the plug-in placement claim cannot be read'
} else {
    $setupText = [System.IO.File]::ReadAllText($setupLog)
    if ($AllUsers) {
        $vst3After = Census $SystemVst3
        $diff = @(Census-Diff $vst3Before $vst3After)
        # Census-Diff labels every entry with its verb ("added: <relative path>"), so the verb is
        # part of the match: without it nothing classifies as ours and this leg can never pass.
        $ours = @($diff | Where-Object { $_ -match '^added: SKEER MIDI VAULT\.vst3[\\/]' })
        $foreign = @($diff | Where-Object { $_ -notmatch '^added: SKEER MIDI VAULT\.vst3[\\/]' })
        if ($setupText -notmatch 'VST3: installing into ') {
            Add-Row 'shared-folder' 'FAIL' ('the Setup log carries no "VST3: installing into" line, ' +
                'so Setup did not take the machine-wide branch - the /ALLUSERS leg did not run')
        } elseif ($ours.Count -eq 0) {
            Add-Row 'shared-folder' 'FAIL' ("the log claims a machine-wide copy but $SystemVst3 has " +
                'no bundle of ours in it')
        } elseif ($foreign.Count) {
            Add-Row 'shared-folder' 'FAIL' ('the install moved ' + $foreign.Count +
                ' entr(ies) outside our bundle in the shared folder: ' + (($foreign |
                Select-Object -First 4) -join '; '))
        } else {
            Add-Row 'shared-folder' 'PASS' ($ours.Count.ToString() + ' file(s) placed under ' +
                "$SystemVst3, every one inside our own bundle, and nothing else in that folder moved")
        }
    } elseif ($setupText -notmatch 'per-user install; the all-users plug-in folder was not touched') {
        Add-Row 'shared-folder' 'FAIL' 'the Setup log does not carry the per-user VST3 line'
    } else {
        $vst3After = Census $SystemVst3
        $diff = @(Census-Diff $vst3Before $vst3After)
        if ($diff.Count) {
            Add-Row 'shared-folder' 'FAIL' ('Setup said it did not touch ' + $SystemVst3 +
                ' and the folder disagrees: ' + ($diff -join '; '))
        } else {
            Add-Row 'shared-folder' 'PASS' ("Setup logged the per-user placement and " +
                "$($vst3After.Count) shared VST3 entries are unchanged")
        }
    }
}

# ---------------------------------------------------------------------------
# 5. Run what the user now has, with the same smoke test the bundle passes.
# ---------------------------------------------------------------------------
$env:SKEER_PACKAGED_EXE = $installedExe
$env:SKEER_SMOKE_DATA = Join-Path $Evidence 'smoke'
try {
    $smokeCode = Invoke-Child (Join-Path $Evidence 'smoke.log') { python tests\test_packaged_smoke.py }
} finally {
    Remove-Item Env:\SKEER_PACKAGED_EXE -ErrorAction SilentlyContinue
    Remove-Item Env:\SKEER_SMOKE_DATA -ErrorAction SilentlyContinue
}
$smokeText = [System.IO.File]::ReadAllText((Join-Path $Evidence 'smoke.log'))
if ($smokeCode -eq 0 -and $smokeText -match 'PASS packaged smoke test') {
    Add-Row 'installed-run' 'PASS' 'the installed executable passed the packaged smoke test'
} else {
    Add-Row 'installed-run' 'FAIL' "smoke exit $smokeCode - see $(Join-Path $Evidence 'smoke.log')"
}

# ---------------------------------------------------------------------------
# 6. Uninstall and prove the machine is back as it was.
# ---------------------------------------------------------------------------
if ($KeepInstall) {
    Add-Row 'uninstall' 'SKIP' "-KeepInstall: left installed at $InstallDir"
} else {
    $entries = @(UninstallEntries)
    if ($entries.Count -ne 1) {
        Add-Row 'uninstall' 'FAIL' "expected exactly one Add/Remove Programs entry, found $($entries.Count)"
    } else {
        $uninsPath = $entries[0].UninstallString.Replace('"', '')
        if (-not (Test-Path -LiteralPath $uninsPath)) {
            Add-Row 'uninstall' 'FAIL' "the registered uninstaller is not at $uninsPath"
        } else {
            $uninsLog = Join-Path $Evidence 'setup-uninstall.log'
            [void](Invoke-Installer $uninsPath @('/VERYSILENT', '/SUPPRESSMSGBOXES',
                '/NORESTART', ('/LOG="' + $uninsLog + '"')))
            # Inno copies the uninstaller into a temporary folder and the process it started can
            # return before the deletion finishes, so the wait is on the state, not the handle.
            $gone = Wait-For { -not (Test-Path -LiteralPath $InstallDir) } 180
            if ($gone) {
                Add-Row 'uninstall' 'PASS' "the application folder $InstallDir is gone"
            } else {
                Add-Row 'uninstall' 'FAIL' "$InstallDir still exists 180s after the uninstaller ran"
            }
            $registered = @(UninstallEntries).Count
            if ($registered -ne $before.uninstall_rows) {
                Add-Row 'uninstall' 'FAIL' ($registered.ToString() +
                    " Add/Remove Programs entries name $AppName; before the cycle there were " +
                    $before.uninstall_rows)
            } else {
                Add-Row 'uninstall' 'PASS' "Add/Remove Programs back to $($before.uninstall_rows) entry(ies)"
            }
            foreach ($pair in @(
                    @{ name = 'desktop shortcut'; now = $desktopNow; was = $before.desktop_lnk;
                       path = $DesktopLnk },
                    @{ name = 'start menu shortcut'; now = $startNow; was = $before.start_lnk;
                       path = $StartLnk })) {
                $after = Test-Path -LiteralPath $pair.path
                if ($after -eq $pair.was) {
                    Add-Row 'uninstall' 'PASS' ($pair.name + ' back to ' + $pair.was)
                } else {
                    Add-Row 'uninstall' 'FAIL' ($pair.name + " is $after after the uninstall; " +
                        "before the cycle it was $($pair.was)")
                }
            }
            $libNow = Test-Path -LiteralPath $UserLib
            if ($libNow -eq $before.user_lib) {
                Add-Row 'uninstall' 'PASS' ("user library at $UserLib is " +
                    "$(if ($libNow) { 'still there, untouched' } else { 'still absent, as before' })")
            } else {
                Add-Row 'uninstall' 'FAIL' "the uninstall changed whether $UserLib exists"
            }
            $finalDiff = @(Census-Diff $vst3Before (Census $SystemVst3))
            if ($finalDiff.Count) {
                Add-Row 'uninstall' 'FAIL' ('shared VST3 folder differs after uninstall: ' +
                    ($finalDiff -join '; '))
            } else {
                Add-Row 'uninstall' 'PASS' 'shared VST3 folder still unchanged'
            }
            if (Test-Path -LiteralPath $CycleRoot) {
                $leftover = @(Get-ChildItem -LiteralPath $CycleRoot -Recurse -Force -ErrorAction SilentlyContinue)
                if ($leftover.Count) {
                    Add-Row 'uninstall' 'FAIL' ($leftover.Count.ToString() +
                        ' item(s) left under ' + $CycleRoot + ': ' +
                        (($leftover | ForEach-Object { $_.Name }) -join ', '))
                } else {
                    Remove-Item -LiteralPath $CycleRoot -Recurse -Force -ErrorAction SilentlyContinue
                    Add-Row 'uninstall' 'PASS' "the empty cycle root $CycleRoot was removed"
                }
            }
        }
    }
}

# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------
End-Cycle
