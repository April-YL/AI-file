param(
    [switch]$Apply
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$targets = New-Object System.Collections.Generic.List[string]

function Add-Target {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        $resolved = (Resolve-Path -LiteralPath $Path).Path
        if (-not ($resolved -eq $repoRoot -or $resolved.StartsWith($repoRoot + [System.IO.Path]::DirectorySeparatorChar))) {
            throw "Refusing to clean outside repo: $resolved"
        }
        if ($resolved -eq $repoRoot) {
            throw "Refusing to clean repo root"
        }
        $targets.Add($resolved)
    }
}

Get-ChildItem -LiteralPath $repoRoot -Force -Directory |
    Where-Object {
        $_.Name -like ".pytest_tmp*" -or
        $_.Name -eq ".tmp" -or
        $_.Name -eq ".pytest_cache" -or
        $_.Name -eq "%SystemDrive%"
    } |
    ForEach-Object { Add-Target $_.FullName }

foreach ($dir in @("scripts", "src", "tests")) {
    $path = Join-Path $repoRoot $dir
    if (Test-Path -LiteralPath $path) {
        Get-ChildItem -LiteralPath $path -Force -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue |
            ForEach-Object { Add-Target $_.FullName }
    }
}

$outputs = Join-Path $repoRoot "outputs"
if (Test-Path -LiteralPath $outputs) {
    Get-ChildItem -LiteralPath $outputs -Force |
        Where-Object { $_.Name -ne ".gitkeep" } |
        ForEach-Object { Add-Target $_.FullName }
}

$uniqueTargets = $targets | Sort-Object -Unique
if (-not $uniqueTargets -or $uniqueTargets.Count -eq 0) {
    Write-Host "No workspace cleanup targets found."
    exit 0
}

if (-not $Apply) {
    Write-Host "Dry run: the following paths would be removed. Re-run with -Apply to delete."
    $uniqueTargets
    exit 0
}

$removed = 0
foreach ($target in $uniqueTargets) {
    try {
        Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction Stop
        $removed += 1
    }
    catch {
        Write-Warning "Failed to remove ${target}: $($_.Exception.Message)"
    }
}
Write-Host "Removed $removed of $($uniqueTargets.Count) workspace cleanup target(s)."