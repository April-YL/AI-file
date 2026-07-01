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

$env:PYTHONDONTWRITEBYTECODE = "1"

if (-not $PytestArgs -or $PyTestArgs.Count -eq 0) {
    $PytestArgs = @("tests")
}

$hygieneScript = Join-Path $PSScriptRoot "check_workspace_hygiene.ps1"
$before = @(& powershell -ExecutionPolicy Bypass -File $hygieneScript -ListOnly)
$beforeSet = @{}
foreach ($item in $before) {
    if ($item) { $beforeSet[$item] = $true }
}
if ($beforeSet.Count -gt 0) {
    Write-Warning "Workspace has pre-existing hygiene issue(s); run will only fail on newly created issues."
}

# Let pytest use its own randomized system temp directory. A fixed --basetemp
# can be locked by Windows/Defender/Codex helpers between runs and block tests.
& $python -m pytest @PytestArgs -p no:cacheprovider
$pytestExit = $LASTEXITCODE
if ($pytestExit -ne 0) {
    exit $pytestExit
}

$after = @(& powershell -ExecutionPolicy Bypass -File $hygieneScript -ListOnly)
$newIssues = New-Object System.Collections.Generic.List[string]
foreach ($item in $after) {
    if ($item -and -not $beforeSet.ContainsKey($item)) {
        $newIssues.Add($item)
    }
}

if ($newIssues.Count -gt 0) {
    Write-Host "Workspace hygiene check failed: test run created new issue(s)." -ForegroundColor Red
    $newIssues | Sort-Object -Unique | ForEach-Object { Write-Host "- $_" }
    Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\scripts\clean_workspace.ps1 -Apply"
    exit 1
}

if ($beforeSet.Count -gt 0) {
    Write-Warning "Workspace hygiene check passed for this run, but pre-existing issue(s) remain."
}
else {
    Write-Host "Workspace hygiene check passed."
}
exit 0