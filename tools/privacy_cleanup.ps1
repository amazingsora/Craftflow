# Craftflow 公開 repo 隱私清理（一次性）。在專案根目錄以 PowerShell 執行：
#   powershell -ExecutionPolicy Bypass -File tools\privacy_cleanup.ps1
# 會改寫 git 歷史並 force push；執行前會先做完整備份。
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$Noreply = "56026769+amazingsora@users.noreply.github.com"
$Remote  = "git@github.com:amazingsora/Craftflow.git"
$Backup  = "..\Craftflow_backup_$(Get-Date -Format yyyyMMdd_HHmmss).git"
$Purge   = @(".env", "data/logs/", "backend/data/vision_cache.json", "backend/data/expand_cache/",
             "Claude outputs/", "t1.png", ".claude/settings.local.json")
# 個人詞（.env／custom_tags.json／private_terms.txt）的取代規則，放 repo 外避免中途中止時被 add（CN-135）
$Replace = "..\craftflow_oss_replacements.txt"

function Confirm-Step($msg) {
    $a = Read-Host "$msg [y/N]"
    if ($a -ne "y") { Write-Host "已中止"; exit 1 }
}

# 原生指令失敗時 PowerShell 不會自動停（2026-10-11 filter-repo 找不到仍一路 push）→ 每步檢查 exit code
function Run {
    & $args[0] @($args | Select-Object -Skip 1)
    if ($LASTEXITCODE -ne 0) { Write-Host "失敗（exit $LASTEXITCODE）：$($args -join ' ')" -ForegroundColor Red; exit 1 }
}

if (Test-Path ".git\index.lock") { Remove-Item ".git\index.lock" -Force }

# 1. 停止追蹤（檔案留在本機）
Write-Host "== 1/5 停止追蹤隱私檔案 =="
foreach ($p in $Purge) { git rm -r --cached --ignore-unmatch --quiet -- $p }
git config user.email $Noreply
if (git status --porcelain) {
    git status --short
    Confirm-Step "以上為待提交的變更（含你尚未 commit 的工作）。要全部 commit 嗎？"
    Run git add -A
    Run git commit -m "chore: privacy cleanup (untrack logs/caches/outputs, bind localhost, strip PNG metadata)"
} else { Write-Host "工作樹乾淨，略過 commit" }

# 2. 完整備份（含所有分支與舊歷史）
Write-Host "== 2/5 備份到 $Backup =="
Run git clone --mirror . $Backup

# 3. 安裝 git-filter-repo（用 python -m 呼叫，不依賴 Scripts 目錄在 PATH）
Write-Host "== 3/5 安裝 git-filter-repo =="
Run python -m pip install --quiet git-filter-repo
Run python -m git_filter_repo --version

# 4. 改寫歷史：移除隱私檔案、個人詞換成 ***REDACTED***、作者 email 統一為 noreply
Write-Host "== 4/5 改寫歷史 =="
Run python tools\check_oss.py --emit-replace-text $Replace
$emails = git log --all --format="%ae" | Sort-Object -Unique | Where-Object { $_ -ne $Noreply }
$map = $emails | ForEach-Object { "amazingsora <$Noreply> <$_>" }
Set-Content -Path mailmap.txt -Value $map -Encoding UTF8
# 歷史裡有 2GB 的 OllamaSetup.exe：Windows 版 fast-import 處理 >2GB pack 會 "cannot truncate pack"。
# GitHub 單檔上限 100MB，這類 blob 本來就推不上去，直接剝掉
$fr = @("--force", "--invert-paths", "--mailmap", "mailmap.txt", "--replace-text", $Replace, "--strip-blobs-bigger-than", "100M")
foreach ($p in $Purge) { $fr += @("--path", $p) }
Confirm-Step "即將改寫全部分支的歷史（備份已在 $Backup）。繼續？"
# 上次（09-23）的 filter-repo 紀錄與失敗殘留：清掉，這次當全新一輪
Remove-Item .git\filter-repo -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item .git\fast_import_crash_* -Force -ErrorAction SilentlyContinue
python -m git_filter_repo @fr
$frExit = $LASTEXITCODE
Remove-Item mailmap.txt, $Replace -ErrorAction SilentlyContinue
if ($frExit -ne 0) { Write-Host "filter-repo 失敗（exit $frExit），未推送。備份在 $Backup" -ForegroundColor Red; exit 1 }
$left = git log --all -p | Select-String -SimpleMatch "***REDACTED***" | Select-Object -First 1
if (-not $left) { Write-Host "注意：歷史中找不到 ***REDACTED***（若本來就沒有個人詞可忽略）" -ForegroundColor Yellow }

# 5. 推回 GitHub（filter-repo 會移除 origin）
Write-Host "== 5/5 force push =="
if (git remote) { Run git remote set-url origin $Remote } else { Run git remote add origin $Remote }
Confirm-Step "即將 force push 所有分支與 tag 到 $Remote。繼續？"
Run git push origin --force --all
Run git push origin --force --tags

# --all 只推本機有的分支；遠端獨有的分支仍帶舊歷史，需另外刪除
$local  = git for-each-ref --format="%(refname:short)" refs/heads
$remote = git ls-remote --heads origin | ForEach-Object { ($_ -split "refs/heads/")[1] }
$stale  = $remote | Where-Object { $local -notcontains $_ }
if ($stale) {
    Write-Host "遠端仍有本機沒有的分支（帶未清理的舊歷史）：" -ForegroundColor Yellow
    $stale | ForEach-Object { Write-Host "  $_" }
    Write-Host "確認不要後執行：git push origin --delete <分支名>"
} else { Write-Host "遠端分支都已用改寫後的歷史覆蓋" }

Write-Host ""
Write-Host "完成。後續："
Write-Host " - 其他電腦上的舊 clone 請刪掉重新 clone（不要 pull，會把舊歷史推回來）"
Write-Host " - GitHub 上舊 commit 的網址仍可能被快取，需要時到 GitHub Support 申請清除 cached views"
Write-Host " - 確認無誤後再刪除備份 $Backup"
