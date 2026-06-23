param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "python"
}

$baseTemp = Join-Path ([System.IO.Path]::GetTempPath()) "fa-qc-agent-pytest"
if (Test-Path -LiteralPath $baseTemp) {
    Remove-Item -LiteralPath $baseTemp -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $baseTemp | Out-Null

$env:PYTHONDONTWRITEBYTECODE = "1"

if (-not $PytestArgs -or $PytestArgs.Count -eq 0) {
    $PytestArgs = @("tests")
}

& $python -m pytest @PytestArgs --basetemp $baseTemp -p no:cacheprovider
exit $LASTEXITCODE
