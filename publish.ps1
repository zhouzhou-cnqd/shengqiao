param(
    [string]$RepoUrl = "https://github.com/zhouzhou-cnqd/shengqiao.git"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot
$GitSafe = @("-c", "safe.directory=$ProjectRoot")

Write-Host "[1/4] Running public release safety check..."
python .\check_public_release.py
if ($LASTEXITCODE -ne 0) { throw "Safety check failed. Publishing stopped." }

Write-Host "[2/4] Preparing Git commit..."
if (-not (Test-Path .git)) { git init -b main }
git @GitSafe branch -M main
git @GitSafe add .
git @GitSafe diff --cached --quiet
if ($LASTEXITCODE -ne 0) { git @GitSafe commit -m "Update public release" }

Write-Host "[3/4] Connecting repository..."
$originExists = (git @GitSafe remote) -contains "origin"
if ($originExists) {
    git @GitSafe remote set-url origin $RepoUrl
} else {
    git @GitSafe remote add origin $RepoUrl
}

Write-Host "[4/4] Pushing main branch..."
git @GitSafe push -u origin main
if ($LASTEXITCODE -ne 0) { throw "Push failed. Check the repository URL and GitHub login." }

Write-Host "Published: $RepoUrl" -ForegroundColor Green
Write-Host "GitHub Pages will deploy the HTML showcase. Confirm Settings > Pages > Source is GitHub Actions."

