# Build the standalone SKEER MIDI VAULT application and Windows installer.
# Run from the repository root:
#   .\packaging\build_installer.ps1
param(
    [switch]$SkipWebBuild,
    [switch]$SkipAppBuild
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
$DistApp = Join-Path $Root "dist\SKEER MIDI VAULT"
$DistInstaller = Join-Path $Root "dist-installer"
$Version = "1.0.0"

Write-Host "SKEER MIDI VAULT packaging - $Version"
New-Item -ItemType Directory -Force -Path $DistInstaller | Out-Null

# Never rebuild over a running copy. The tree kill also removes leftover
# multiprocessing workers from a previously interrupted test.
& cmd.exe /d /c "taskkill /IM ""SKEER MIDI VAULT.exe"" /T /F >nul 2>&1"
Start-Sleep -Milliseconds 400

if (-not $SkipWebBuild) {
    Write-Host "Building interface..."
    npm --prefix web run build
    if ($LASTEXITCODE -ne 0) { throw "Interface build failed." }
}

if (-not $SkipAppBuild) {
    Write-Host "Cleaning previous application bundle..."
    if (Test-Path -LiteralPath $DistApp) {
        Remove-Item -LiteralPath $DistApp -Recurse -Force
    }
    Write-Host "Building standalone Python application..."
    $web = Join-Path $Root "web\dist"
    $icon = Join-Path $Root "build\app.ico"
    $versionFile = Join-Path $Root "build\version_info.txt"
    python -m PyInstaller `
        --noconfirm --clean --console --hide-console hide-early --onedir `
        --name "SKEER MIDI VAULT" `
        --icon $icon `
        --version-file $versionFile `
        --add-data "$web;web/dist" `
        --hidden-import pystray._win32 `
        --hidden-import PIL.Image `
        --collect-submodules midivault `
        --distpath (Join-Path $Root "dist") `
        --workpath (Join-Path $Root "build\work") `
        --specpath (Join-Path $Root "build") `
        desktop.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
}

if (-not (Test-Path (Join-Path $DistApp "SKEER MIDI VAULT.exe"))) {
    throw "Application executable is missing. Build it before compiling the installer."
}

# Find Inno Setup's command-line compiler in common locations, the registry, or
# the INNO_SETUP_ISCC environment variable.
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
    if ($installed) {
        $candidates += (Join-Path $installed.InstallLocation "ISCC.exe")
    }
    $iscc = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
}
if (-not $iscc) {
    throw "Inno Setup 6 compiler (ISCC.exe) was not found. Install Inno Setup 6 or set INNO_SETUP_ISCC."
}

Write-Host "Compiling Windows installer with $iscc"
& $iscc (Join-Path $Root "packaging\skeer-midi-vault.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }

Write-Host "Creating portable ZIP..."
$portable = Join-Path $DistInstaller "SKEER-MIDI-VAULT-Portable-$Version.zip"
if (Test-Path -LiteralPath $portable) { Remove-Item -LiteralPath $portable -Force }
Compress-Archive -LiteralPath (Join-Path $DistApp "SKEER MIDI VAULT.exe"), (Join-Path $DistApp "_internal") -DestinationPath $portable -CompressionLevel Optimal

Write-Host "Writing SHA-256 checksums..."
$releaseFiles = Get-ChildItem -LiteralPath $DistInstaller -File |
    Where-Object { $_.Name -match "Setup-$Version\.exe$|Portable-$Version\.zip$" } |
    Sort-Object Name
$lines = foreach ($file in $releaseFiles) {
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $($file.Name)"
}
$lines | Set-Content -LiteralPath (Join-Path $DistInstaller "SHA256SUMS.txt") -Encoding ascii

Write-Host ""
Write-Host "Release files:"
$releaseFiles | ForEach-Object {
    Write-Host ("  {0}  ({1:N1} MB)" -f $_.FullName, ($_.Length / 1MB))
}
Write-Host ("  SHA256SUMS.txt")
Write-Host ""
Write-Host "Installer is unsigned. See packaging/README.md for code-signing guidance."
