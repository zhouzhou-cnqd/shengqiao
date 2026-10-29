param(
    [string]$RepoUrl = "https://github.com/zhouzhou-cnqd/声桥.git"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "[1/4] 检查公开内容（数据、音频、权重、私有路径）..."
python .\check_public_release.py
if ($LASTEXITCODE -ne 0) { throw "安全检查未通过，已停止发布。" }

Write-Host "[2/4] 整理 Git 提交..."
if (-not (Test-Path .git)) { git init -b main }
git branch -M main
git add .
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) { git commit -m "Update 声桥 public release" }

Write-Host "[3/4] 连接新仓库..."
$origin = git remote get-url origin 2>$null
if ($LASTEXITCODE -eq 0) {
    git remote set-url origin $RepoUrl
} else {
    git remote add origin $RepoUrl
}

Write-Host "[4/4] 推送 main 分支..."
git push -u origin main
if ($LASTEXITCODE -ne 0) { throw "推送失败，请确认空仓库地址和 GitHub 登录状态。" }

Write-Host "发布完成：$RepoUrl" -ForegroundColor Green
Write-Host "HTML 展示将由 GitHub Pages 工作流自动部署。首次使用时请在仓库 Settings > Pages 中确认 Source 为 GitHub Actions。"

