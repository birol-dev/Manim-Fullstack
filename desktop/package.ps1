param([switch]$SkipFrontendBuild)
$ErrorActionPreference = 'Stop'
$prepareArgs = @((Join-Path $PSScriptRoot 'scripts/prepare.py'))
if ($SkipFrontendBuild) { $prepareArgs += '--skip-frontend' }
& python @prepareArgs
if ($LASTEXITCODE -ne 0) { throw 'Desktop preparation failed.' }
& python (Join-Path $PSScriptRoot 'scripts/package.py')
if ($LASTEXITCODE -ne 0) { throw 'Desktop packaging failed.' }
& python (Join-Path $PSScriptRoot 'scripts/build_installer.py')
exit $LASTEXITCODE
