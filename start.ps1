# SKEER MIDI VAULT - one-command local launch (Windows).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.12+ is required. Install it from python.org and try again."
}

$needsBuild = -not (Test-Path "web/dist/index.html")
if (-not $needsBuild) {
    $distTime = (Get-Item "web/dist/index.html").LastWriteTimeUtc
    $newestSource = Get-ChildItem "web/src", "web/index.html", "web/package.json", "web/vite.config.ts", "web/tsconfig.json" -File -Recurse |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if ($newestSource -and $newestSource.LastWriteTimeUtc -gt $distTime) {
        $needsBuild = $true
    }
}

if ($needsBuild) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "Node.js 20+ (with npm) is required to build the interface. Install it from nodejs.org, or use a delivered web/dist bundle."
    }
    if (-not (Test-Path "web/node_modules")) {
        Write-Host "Installing interface dependencies (first build)..."
        Push-Location web
        npm ci --no-audit --no-fund
        Pop-Location
    }
    Write-Host "Building the interface..."
    Push-Location web
    npm run build
    Pop-Location
}

Write-Host "Launching SKEER MIDI VAULT..."
python -m midivault.server --open @args
