param(
    [string]$TargetRepoPath = $env:TG_NOTIFICATION_REPO,
    [string]$CommitMessage,
    [switch]$NoCommit,
    [switch]$NoPush,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$sourceRoot = $PSScriptRoot
$defaultTarget = Join-Path (Split-Path $sourceRoot -Parent) 'TG-notification'

if ([string]::IsNullOrWhiteSpace($TargetRepoPath)) {
    $TargetRepoPath = $defaultTarget
}

$resolvedTarget = [System.IO.Path]::GetFullPath($TargetRepoPath)

if (-not (Test-Path -LiteralPath $resolvedTarget -PathType Container)) {
    throw "Target site repo path was not found: $resolvedTarget"
}

$gitDir = Join-Path $resolvedTarget '.git'
if (-not (Test-Path -LiteralPath $gitDir)) {
    throw "Folder does not look like a git repository: $resolvedTarget"
}

$filesToCopy = @(
    'index.html',
    'frontend.js',
    'manifest.json',
    'serviceworker.js',
    'telegram-icon.svg'
)

$trackedFiles = $filesToCopy + 'version.json'

Write-Host "Syncing PWA files to $resolvedTarget"

foreach ($relativePath in $filesToCopy) {
    $sourcePath = Join-Path $sourceRoot $relativePath
    $targetPath = Join-Path $resolvedTarget $relativePath

    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "Source file was not found: $sourcePath"
    }

    if ($DryRun) {
        Write-Host "[DRY RUN] $relativePath"
        continue
    }

    Copy-Item -LiteralPath $sourcePath -Destination $targetPath -Force
    Write-Host "Updated $relativePath"
}

if ($DryRun) {
    Write-Host 'Dry run completed. No files were copied.'
    exit 0
}

$contentStatus = git -C $resolvedTarget status --short -- @filesToCopy
if (-not $contentStatus) {
    Write-Host 'No changes to commit.'
    exit 0
}

$sourceCommit = (git -C $sourceRoot rev-parse --short HEAD 2>$null)
if (-not $sourceCommit) {
    $sourceCommit = 'no-git'
}

$versionStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$versionTime = (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss UTC')
$versionData = [ordered]@{
    version = "$versionStamp-$sourceCommit"
    updated_at = $versionTime
}
$versionJson = $versionData | ConvertTo-Json
$versionTargetPath = Join-Path $resolvedTarget 'version.json'
[System.IO.File]::WriteAllText($versionTargetPath, $versionJson + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))

$statusOutput = git -C $resolvedTarget status --short -- @trackedFiles

Write-Host ''
Write-Host 'Changes:'
$statusOutput | ForEach-Object { Write-Host $_ }

if ($NoCommit) {
    Write-Host ''
    Write-Host 'Files were copied. Commit and push were skipped because -NoCommit was used.'
    exit 0
}

git -C $resolvedTarget add -- $trackedFiles

$postAddStatus = git -C $resolvedTarget diff --cached --name-only
if (-not $postAddStatus) {
    Write-Host 'No staged changes remain after git add.'
    exit 0
}

if ([string]::IsNullOrWhiteSpace($CommitMessage)) {
    $CommitMessage = 'Update PWA files from tg2iOS'
}

git -C $resolvedTarget commit -m $CommitMessage

if ($NoPush) {
    Write-Host 'Commit created. Push skipped because -NoPush was used.'
    exit 0
}

git -C $resolvedTarget push
Write-Host 'PWA sync completed.'
