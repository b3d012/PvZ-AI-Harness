# One-time repository history cleanup.
# Run from the repository root after installing git-filter-repo.
# WARNING: rewrites commit SHAs and force-pushes all local branches/tags.

$ErrorActionPreference = "Stop"

$GamePath = "Plants Vs Zombies Game of the Year Edition"

if (-not (Test-Path ".git")) {
    throw "Run this script from the PvZ-DeepLearning repository root."
}

if (-not (Get-Command git-filter-repo -ErrorAction SilentlyContinue)) {
    throw "git-filter-repo is required. Install it with: pip install git-filter-repo"
}

Write-Host "Rewriting history to remove: $GamePath" -ForegroundColor Yellow

git filter-repo --force --path "$GamePath" --invert-paths

Write-Host "Verifying that the path is absent from rewritten history..." -ForegroundColor Cyan
$remaining = git log --all --format="%H" -- "$GamePath"
if ($remaining) {
    throw "Verification failed: the game path is still present in rewritten history."
}

Write-Host "History is clean locally." -ForegroundColor Green
Write-Host "Force-pushing rewritten refs to origin..." -ForegroundColor Yellow

git remote add origin https://github.com/b3d012/PvZ-DeepLearning.git 2>$null
if ($LASTEXITCODE -ne 0) {
    git remote set-url origin https://github.com/b3d012/PvZ-DeepLearning.git
}

git push --force --all origin
git push --force --tags origin

Write-Host "Done. Anyone with an old clone must re-clone or hard-reset to the rewritten history." -ForegroundColor Green
