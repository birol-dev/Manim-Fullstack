param(
    [switch]$SkipFrontendBuild,
    [switch]$RefreshDependencies,
    [switch]$Smoke,
    [switch]$UiSmoke,
    [string]$DataDir
)
$ErrorActionPreference = 'Stop'
$desktopRoot = $PSScriptRoot
$prepareArgs = @((Join-Path $desktopRoot 'scripts/prepare.py'))
if ($SkipFrontendBuild) { $prepareArgs += '--skip-frontend' }
if ($RefreshDependencies) { $prepareArgs += '--refresh-deps' }
& python @prepareArgs
if ($LASTEXITCODE -ne 0) { throw 'Desktop preparation failed.' }
$launchArgs = @('-B', (Join-Path $desktopRoot 'launcher.py'), '--app-root', (Split-Path $desktopRoot))
if ($Smoke) { $launchArgs += '--smoke' }
if ($UiSmoke) { $launchArgs += '--ui-smoke' }
if ($DataDir) { $launchArgs += @('--data-dir', $DataDir) }
& (Join-Path $desktopRoot '.runtime/python.exe') @launchArgs
exit $LASTEXITCODE
