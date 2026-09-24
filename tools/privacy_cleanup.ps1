# Craftflow 公開 repo 隱私清理（一次性）。在專案根目錄以 PowerShell 執行：
#   powershell -ExecutionPolicy Bypass -File tools\privacy_cleanup.ps1
# 會改寫 git 歷史並 force push；執行前會先做完整備份。
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$Noreply = "56026769+amazingsora@users.noreply.github.com"
$Remote  = "git@github.com:amazingsora/Craftflow.git"
$Backup  = "..\Craftflow_backup_$(Get-Date -Format yyyyMMdd_HHmmss).git"
$Purge   = @(".env", "data/logs/", "backend/data/vision_cache.json", "backend/data/expand_cache/",
             "Claude outputs/", "t1.png")

function Confirm-Step($msg) {
    $a = Read-Host "$msg [y/N]"
    if ($a -ne "y") { Write-Host "已中止"; exit 1 }
}

if (Test-Path ".git\index.lock") { Remove-Item ".git\index.lock" -Force }

# 1. 停止追蹤（檔案留在本機）
Write-Host "== 1/5 停止追蹤隱私檔案 =="
foreach ($p in $Purge) { git rm -r --cached --ignore-unmatch --quiet -- $p }
git config user.email $Noreply
git status --short
Confirm-Step "以上為待提交的變更（含你尚未 commit 的工作）。要全部 commit 嗎？"
git add -A
git commit -m "chore: privacy cleanup (untrack logs/caches/outputs, bind localhost, strip PNG metadata)"

# 2. 完整備份（含所有分支與舊歷史）
Write-Host "== 2/5 備份到 $Backup =="
git clone --mirror . $Backup

# 3. 安裝 git-filter-repo
Write-Host "== 3/5 安裝 git-filter-repo =="
python -m pip install --quiet git-filter-repo

# 4. 改寫歷史：移除隱私檔案、作者 email 統一為 noreply
Write-Host "== 4/5 改寫歷史 =="
$emails = git log --all --format="%ae" | Sort-Object -Unique | Where-Object { $_ -ne $Noreply }
$map = $emails | ForEach-Object { "amazingsora <$Noreply> <$_>" }
Set-Content -Path mailmap.txt -Value $map -Encoding UTF8
$fr = @("filter-repo", "--force", "--invert-paths", "--mailmap", "mailmap.txt")
foreach ($p in $Purge) { $fr += @("--path", $p) }
Confirm-Step "即將改寫全部分支的歷史（備份已在 $Backup）。繼續？"
& git @fr
Remove-Item mailmap.txt

# 5. 推回 GitHub（filter-repo 會移除 origin）
Write-Host "== 5/5 force push =="
git remote add origin $Remote
Confirm-Step "即將 force push 所有分支與 tag 到 $Remote。繼續？"
git push origin --force --all
git push origin --force --tags

Write-Host ""
Write-Host "完成。後續："
Write-Host " - 其他電腦上的舊 clone 請刪掉重新 clone（不要 pull，會把舊歷史推回來）"
Write-Host " - GitHub 上舊 commit 的網址仍可能被快取，需要時到 GitHub Support 申請清除 cached views"
Write-Host " - 確認無誤後再刪除備份 $Backup"
