param()

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$violations = New-Object System.Collections.Generic.List[string]

function Add-Violation {
    param([string]$Message)
    $violations.Add($Message)
}

Get-ChildItem -LiteralPath $repoRoot -Force -Directory |
    Where-Object { $_.Name -like ".pytest_tmp*" -or $_.Name -eq ".tmp" -or $_.Name -eq "%SystemDrive%" } |
    ForEach-Object { Add-Violation "Temporary directory in repo root: $($_.FullName)" }

$pytestCache = Join-Path $repoRoot ".pytest_cache"
if (Test-Path -LiteralPath $pytestCache) {
    try {
        Get-ChildItem -LiteralPath $pytestCache -Force -ErrorAction Stop | Out-Null
        Add-Violation "Pytest cache in repo root: $pytestCache"
    }
    catch [System.UnauthorizedAccessException] {
        Write-Warning "Ignoring inaccessible legacy pytest cache: $pytestCache"
    }
}

foreach ($dir in @("scripts", "src", "tests")) {
    $path = Join-Path $repoRoot $dir
    if (Test-Path -LiteralPath $path) {
        Get-ChildItem -LiteralPath $path -Force -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue |
            ForEach-Object { Add-Violation "Python bytecode cache in tracked area: $($_.FullName)" }
    }
}

$outputs = Join-Path $repoRoot "outputs"
if (Test-Path -LiteralPath $outputs) {
    Get-ChildItem -LiteralPath $outputs -Force |
        Where-Object { $_.Name -ne ".gitkeep" } |
        ForEach-Object { Add-Violation "Runtime output in outputs/: $($_.FullName)" }
}

if ($violations.Count -gt 0) {
    Write-Host "Workspace hygiene check failed:" -ForegroundColor Red
    $violations | ForEach-Object { Write-Host "- $_" }
    Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\scripts\clean_workspace.ps1 -Apply"
    exit 1
}

Write-Host "Workspace hygiene check passed."
exit 0