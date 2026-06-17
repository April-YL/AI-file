# 清理工作区本地临时文件（不删源码、fixture、资料库、.env）
# 用法：.\scripts\clean_workspace.ps1
# 若 Cursor 占用导致「拒绝访问」，请先关闭 Cursor 或在系统 PowerShell 中运行。

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot

function Remove-IfExists {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $true }
    try {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        return $true
    } catch {
        Write-Warning "无法删除: $Path — $($_.Exception.Message)"
        return $false
    }
}

$removed = 0
$failed = 0

# pytest 临时目录（统一 .pytest_tmp + 历史遗留的 .pytest_tmp_*）
Get-ChildItem -LiteralPath $Root -Force |
    Where-Object { $_.Name -eq '.pytest_tmp' -or $_.Name -like '.pytest_tmp_*' -or $_.Name -eq '.tmp' } |
    ForEach-Object {
        if (Remove-IfExists $_.FullName) { $removed++ } else { $failed++ }
    }

# pytest 缓存
if (Remove-IfExists (Join-Path $Root '.pytest_cache')) { $removed++ }

# artifacts 临时（保留 case_* 回归产物）
$artifactRoot = Join-Path $Root 'artifacts'
if (Test-Path -LiteralPath $artifactRoot) {
    Get-ChildItem -LiteralPath $artifactRoot -Force |
        Where-Object { $_.Name -notlike 'case_*' } |
        ForEach-Object {
            if (Remove-IfExists $_.FullName) { $removed++ } else { $failed++ }
        }
}

# scripts 一次性诊断脚本
Get-ChildItem -LiteralPath (Join-Path $Root 'scripts') -Filter '_*.py' -File -ErrorAction SilentlyContinue |
    ForEach-Object {
        if (Remove-IfExists $_.FullName) { $removed++ } else { $failed++ }
    }

# 根目录常见垃圾
@(
    'qc_report.json', '_summary_check_gtech.txt', '.tmp_qc_out', '.tmp_qc_out_qc_review.html'
) | ForEach-Object {
    $p = Join-Path $Root $_
    if (Remove-IfExists $p) { $removed++ }
}

# Excel 锁文件（根目录与 outputs）
Get-ChildItem -LiteralPath $Root -Recurse -Filter '~$*' -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\固定资产质检agent\\' } |
    ForEach-Object {
        if (Remove-IfExists $_.FullName) { $removed++ } else { $failed++ }
    }

Write-Host "清理完成：成功 $removed 项，失败 $failed 项。"
if ($failed -gt 0) {
    Write-Host "提示：失败项多为 Cursor/Excel 占用。请关闭相关程序后重试，或重启后再运行本脚本。"
}
