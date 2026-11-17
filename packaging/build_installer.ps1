# Build the standalone SKEER MIDI VAULT application, stage the VST3 plug-in, and compile
# the Windows installer and portable ZIP into launch/.
#
#   .\packaging\build_installer.ps1                 # everything, unsigned
#   .\packaging\build_installer.ps1 -Sign           # same, Authenticode-signed if configured
#   .\packaging\build_installer.ps1 -SkipPlugin     # app only, no VST3 in the deliverables
#   .\packaging\build_installer.ps1 -SkipWebBuild   # reuse web/dist as it stands
#   .\packaging\build_installer.ps1 -SkipAppBuild   # re-pack the bundle already in launch/
#
# This script needs no C++ compiler: it stages whatever plugin\build.ps1 produced and refuses
# to ship it if it disagrees with the release version. Build the plug-in first, or -SkipPlugin.
#
# Order is load-bearing in two places. The app executable is signed before Inno packs it,
# because the installer embeds those exact bytes and would break the signature by repacking an
# unsigned copy. The checksums are written last, after the Setup is signed, because a hash of a
# file that is about to change is worse than no hash.
param(
    [switch]$SkipWebBuild,
    [switch]$SkipAppBuild,
    [switch]$SkipPlugin,
    [switch]$Sign
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
$Launch = Join-Path $Root "launch"
$DistApp = Join-Path $Launch "SKEER MIDI VAULT"
$StagedPlugin = Join-Path $Launch "VST3"
$PluginBundle = Join-Path $Root `
    "plugin\build\SkeerMidiVaultPlugin_artefacts\Release\VST3\SKEER MIDI VAULT.vst3"

function Say([string]$Message) { Write-Host $Message }
function Fail([string]$Message) { throw $Message }

# ---------------------------------------------------------------------------
# 1. Pre-flight. Everything that can be known up front is known here, so a doomed build fails
#    before it has deleted anything or closed the application the user is running.
# ---------------------------------------------------------------------------
Say "SKEER MIDI VAULT packaging - pre-flight"
$missing = @()

foreach ($tool in @("git", "python", "node", "npm")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { $missing += "$tool (not on PATH)" }
}

$pythonOk = $false
try {
    & python -c "import PyInstaller" *> $null
    $pythonOk = ($LASTEXITCODE -eq 0)
}
catch { $pythonOk = $false }
if (-not $pythonOk) { $missing += "PyInstaller (python -m pip install -r packaging\requirements-build.txt)" }

# Inno Setup's compiler: environment variable, the usual install folders, the vendored copy,
# or the uninstall registry. Nothing here downloads it - packaging\README.md says what a fresh
# machine needs installed.
$iscc = $env:INNO_SETUP_ISCC
if (-not $iscc) {
    $candidates = @(
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        (Join-Path $Root "build\tools\official-innosetup\app\ISCC.exe"),
        (Join-Path $Root "build\tools\InnoSetup6\ISCC.exe")
    )
    $uninstallRoots = @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    $installed = Get-ItemProperty -Path $uninstallRoots -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -like "Inno Setup*" -and $_.InstallLocation } |
        Select-Object -First 1
    if ($installed) { $candidates += (Join-Path $installed.InstallLocation "ISCC.exe") }
    $iscc = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
}
if (-not $iscc) { $missing += "Inno Setup 6 (ISCC.exe) - install it or set INNO_SETUP_ISCC" }

$signtool = $null
if ($Sign) {
    $signtoolCandidates = @(
        (Get-Command signtool -ErrorAction SilentlyContinue | Select-Object -First 1).Source,
        "${env:ProgramFiles(x86)}\Windows Kits\10\bin\x64\signtool.exe",
        "$env:ProgramFiles\Windows Kits\10\bin\x64\signtool.exe"
    )
    $signtool = $signtoolCandidates |
        Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if (-not $signtool) { $missing += "signtool.exe (Windows SDK) - required by -Sign" }
    if (-not $env:SKEER_SIGN_THUMBPRINT -and -not $env:SKEER_SIGN_PFX) {
        $missing += "a signing certificate (SKEER_SIGN_THUMBPRINT or SKEER_SIGN_PFX) - required by -Sign"
    }
}

if (-not $SkipWebBuild -and -not (Test-Path (Join-Path $Root "web\node_modules"))) {
    # This script never runs npm ci; a clean checkout needs that once first.
    $missing += "web\node_modules (npm --prefix web ci)"
}

if ($missing) {
    foreach ($item in $missing) { Say "  MISSING: $item" }
    Fail ("Pre-flight failed with " + $missing.Count +
          " unmet requirement(s). Nothing was deleted and no running app was closed.")
}

$toolLine = "  tools: git, python+PyInstaller, node, npm, ISCC"
if ($Sign) { $toolLine += ", signtool" }
Say $toolLine

# ---------------------------------------------------------------------------
# 2. One version, read from the one file the interface can see. This used to be a literal here,
#    which is how a partial bump produced a ZIP named for the old version, an installer named
#    for the new one, and an EMPTY SHA256SUMS.txt with exit code 0: the release glob matched
#    nothing, and nothing checked that it had.
# ---------------------------------------------------------------------------
$versionText = [System.IO.File]::ReadAllText((Join-Path $Root "midivault\__init__.py"))
$Version = [regex]::Match($versionText, '(?m)^__version__ = "([^"]+)"\s*$').Groups[1].Value
if (-not $Version) { Fail "midivault\__init__.py does not state __version__ in the expected form." }

# The installer's own literals are checked rather than trusted, because ISCC compiles happily
# a Setup exe whose filename and file properties disagree with the payload inside it.
$issPath = Join-Path $Root "packaging\skeer-midi-vault.iss"
$issText = [System.IO.File]::ReadAllText($issPath)
$appVersionPattern = '(?m)^#define AppVersion "' + [regex]::Escape($Version) + '"\s*$'
$versionInfoPattern = '(?m)^VersionInfoVersion=' + [regex]::Escape($Version) + '(\.0)*\s*$'
if (-not [regex]::IsMatch($issText, $appVersionPattern)) {
    Fail ("packaging\skeer-midi-vault.iss does not define AppVersion `"$Version`".")
}
if (-not [regex]::IsMatch($issText, $versionInfoPattern)) {
    Fail ("packaging\skeer-midi-vault.iss does not set VersionInfoVersion to $Version.")
}
Say "  version: $Version (from midivault\__init__.py, cross-checked against the installer script)"

# ---------------------------------------------------------------------------
# 3. Only now may anything be destroyed. The tree kill also removes leftover multiprocessing
#    workers from a previously interrupted test.
# ---------------------------------------------------------------------------
& cmd.exe /d /c "taskkill /IM ""SKEER MIDI VAULT.exe"" /T /F >nul 2>&1"
Start-Sleep -Milliseconds 400

New-Item -ItemType Directory -Force -Path $Launch | Out-Null

if (-not $SkipWebBuild) {
    Say "Building interface..."
    npm --prefix web run build
    if ($LASTEXITCODE -ne 0) { Fail "Interface build failed." }
}

$webDir = Join-Path $Root "web\dist"
if (-not (Test-Path -LiteralPath $webDir)) { Fail "web\dist is missing; build the interface first." }

Say "Stamping provenance..."
$stamp = Join-Path $Root "build\BUILDINFO.json"
& python scripts\build_stamp.py --out $stamp
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $stamp)) {
    Fail "No provenance stamp. A release artifact that cannot name its commit is not a release."
}

if (-not $SkipAppBuild) {
    Say "Cleaning previous application bundle..."
    if (Test-Path -LiteralPath $DistApp) { Remove-Item -LiteralPath $DistApp -Recurse -Force }
    Say "Building standalone Python application..."
    $icon = Join-Path $Root "build\app.ico"
    $versionFile = Join-Path $Root "build\version_info.txt"
    python -m PyInstaller `
        --noconfirm --clean --console --hide-console hide-early --onedir `
        --name "SKEER MIDI VAULT" `
        --icon $icon `
        --version-file $versionFile `
        --add-data "$webDir;web/dist" `
        --add-data "$stamp;buildinfo" `
        --hidden-import pystray._win32 `
        --hidden-import PIL.Image `
        --collect-submodules midivault `
        --distpath $Launch `
        --workpath (Join-Path $Root "build\work") `
        --specpath (Join-Path $Root "build") `
        desktop.py
    if ($LASTEXITCODE -ne 0) { Fail "PyInstaller build failed." }
}

$appExe = Join-Path $DistApp "SKEER MIDI VAULT.exe"
if (-not (Test-Path -LiteralPath $appExe)) {
    Fail "Application executable is missing. Build it before compiling the installer."
}
if (-not (Test-Path -LiteralPath (Join-Path $DistApp "_internal\buildinfo\BUILDINFO.json"))) {
    Fail "The bundle shipped without its provenance stamp - check the --add-data buildinfo line."
}

# ---------------------------------------------------------------------------
# 4. The plug-in is a deliverable, so it is staged - and checked - here. moduleinfo.json is the
#    number a host lists the plug-in by; shipping an app at 1.1.0 beside a plug-in still saying
#    1.0.0 is two products claiming one release.
# ---------------------------------------------------------------------------
$pluginStaged = $false
if (-not $SkipPlugin) {
    if (-not (Test-Path -LiteralPath $PluginBundle)) {
        Fail "VST3 bundle not found at $PluginBundle - run plugin\build.ps1, or pass -SkipPlugin."
    }
    $moduleInfo = Join-Path $PluginBundle "Contents\Resources\moduleinfo.json"
    if (-not (Test-Path -LiteralPath $moduleInfo)) { Fail "moduleinfo.json is missing from the bundle." }
    $bundleVersion = [regex]::Match(
        [System.IO.File]::ReadAllText($moduleInfo), '"Version":\s*"([^"]+)"').Groups[1].Value
    if ($bundleVersion -ne $Version) {
        Fail "Plug-in moduleinfo.json says $bundleVersion but the release is $Version - rebuild it."
    }
    $pluginBinary = Get-ChildItem -LiteralPath (Join-Path $PluginBundle "Contents\x86_64-win") -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Length -gt 0 }
    if (-not $pluginBinary) { Fail "The staged VST3 bundle has no binary under Contents\x86_64-win." }
    Say "Staging VST3 $bundleVersion into launch\VST3 ..."
    if (Test-Path -LiteralPath $StagedPlugin) { Remove-Item -LiteralPath $StagedPlugin -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $StagedPlugin | Out-Null
    # Only the .vst3 directory: the artefacts folder also holds .lib and .exp link leftovers.
    Copy-Item -LiteralPath $PluginBundle -Destination (Join-Path $StagedPlugin "SKEER MIDI VAULT.vst3") `
        -Recurse -Force
    $pluginStaged = $true
}

# ---------------------------------------------------------------------------
# 5. Signing, before Inno sees the payload. Inert unless -Sign.
# ---------------------------------------------------------------------------
function Invoke-Sign([string]$Target) {
    if (-not $Sign) { return }
    Say "  signing $(Split-Path $Target -Leaf)"
    $timestamp = $env:SKEER_SIGN_TS_URL
    if (-not $timestamp) { $timestamp = "http://timestamp.digicert.com" }
    $arguments = @("sign", "/fd", "SHA256", "/tr", $timestamp, "/td", "SHA256")
    if ($env:SKEER_SIGN_THUMBPRINT) { $arguments += @("/sha1", $env:SKEER_SIGN_THUMBPRINT) }
    else { $arguments += @("/f", $env:SKEER_SIGN_PFX) }
    if ($env:SKEER_SIGN_PASSWORD) { $arguments += @("/p", $env:SKEER_SIGN_PASSWORD) }
    $arguments += @("/d", "SKEER MIDI VAULT")
    $arguments += $Target
    & $signtool @arguments
    if ($LASTEXITCODE -ne 0) { Fail "signtool failed on $Target" }
    & $signtool verify /pa /q $Target
    if ($LASTEXITCODE -ne 0) { Fail "signtool could not verify its own signature on $Target" }
}

Invoke-Sign $appExe

# ---------------------------------------------------------------------------
# 6. Clear superseded deliverables now - once everything they depend on exists - so a failed
#    build cannot leave launch/ emptied, and a successful one cannot leave two versions.
# ---------------------------------------------------------------------------
$supersededPredicate = { $_.Name -match '^SKEER-MIDI-VAULT-(Setup|Portable)-.*\.(exe|zip)$' -or
                         $_.Name -eq 'SHA256SUMS.txt' }
$superseded = @(Get-ChildItem -LiteralPath $Launch -File -ErrorAction SilentlyContinue |
    Where-Object $supersededPredicate)
if ($superseded) {
    $superseded | Remove-Item -Force -ErrorAction SilentlyContinue
    # Silently leaving one behind is how the previous release ends up shipped beside this one,
    # under names a reader cannot tell apart. A file that will not delete is held by something:
    # usually a running Setup or an antivirus scan on it, and the build is the wrong place to
    # guess which.
    $left = @(Get-ChildItem -LiteralPath $Launch -File -ErrorAction SilentlyContinue |
        Where-Object $supersededPredicate)
    if ($left.Count) {
        Fail ("Could not remove " + (($left | ForEach-Object { $_.Name }) -join ", ") +
              " from launch/. Close the installer and retry; a superseded deliverable that " +
              "survives the build is a second release under the same naming scheme.")
    }
}

Say "Compiling Windows installer with $iscc"
# /DPluginStaged is the switch the installer script reads to decide whether there is a VST3 to
# install at all. It is passed only when one was really staged, so -SkipPlugin produces an
# installer with no plug-in rather than an ISCC error about a missing Source directory.
$isccArgs = @($issPath)
if ($pluginStaged) { $isccArgs += "/DPluginStaged=1" }
& $iscc @isccArgs
if ($LASTEXITCODE -ne 0) { Fail "Inno Setup compilation failed." }

$setupExe = Join-Path $Launch "SKEER-MIDI-VAULT-Setup-$Version.exe"
if (-not (Test-Path -LiteralPath $setupExe)) { Fail "Inno produced no $setupExe." }

Say "Creating portable ZIP in launch/..."
$zipItems = @($appExe, (Join-Path $DistApp "_internal"))
if ($pluginStaged) { $zipItems += $StagedPlugin }
$portable = Join-Path $Launch "SKEER-MIDI-VAULT-Portable-$Version.zip"
Compress-Archive -LiteralPath $zipItems -DestinationPath $portable -CompressionLevel Optimal
if (-not (Test-Path -LiteralPath $portable)) { Fail "The portable ZIP was not created." }

Invoke-Sign $setupExe

# ---------------------------------------------------------------------------
# 7. Checksums last, LF-only. Set-Content writes CRLF on this platform, which makes the
#    standard verifier on any Unix-like checkout report "No such file or directory" against a
#    perfectly good release and exit 1.
# ---------------------------------------------------------------------------
Say "Writing SHA-256 checksums..."
$releasePattern = '^SKEER-MIDI-VAULT-(Setup|Portable)-' + [regex]::Escape($Version) + '\.(exe|zip)$'
$releaseFiles = @(Get-ChildItem -LiteralPath $Launch -File |
    Where-Object { $_.Name -match $releasePattern } | Sort-Object Name)
if ($releaseFiles.Count -ne 2) {
    Fail ("Expected 2 release files for $Version, found " + $releaseFiles.Count + ": " +
          (($releaseFiles | ForEach-Object { $_.Name }) -join ", "))
}
$lines = foreach ($file in $releaseFiles) {
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $($file.Name)"
}
[System.IO.File]::WriteAllText((Join-Path $Launch "SHA256SUMS.txt"), (($lines -join "`n") + "`n"),
    (New-Object System.Text.UTF8Encoding($false)))

Say ""
Say "Release files in launch/:"
foreach ($file in $releaseFiles) {
    Say ("  {0}  ({1:N1} MB)" -f $file.Name, ($file.Length / 1MB))
}
Say "  SHA256SUMS.txt (LF-terminated; verify with: sha256sum -c SHA256SUMS.txt)"
if ($pluginStaged) { Say "  VST3/ (also packed by the installer and inside the portable ZIP)" }
Say ""
if ($Sign) { Say "Signed and timestamped; verify with: signtool verify /pa <file>" }
else { Say "Installer is unsigned. See packaging\README.md for code-signing guidance." }
