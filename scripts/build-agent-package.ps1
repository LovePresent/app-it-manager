#requires -Version 5.1
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$sources = Join-Path $root 'agent_windows'
$destination = Join-Path $root 'backend\agent_package'
$compiler = Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { $compiler = Join-Path $env:SystemRoot 'Microsoft.NET\Framework\v4.0.30319\csc.exe' }
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Windows .NET Framework compiler is required.' }
$null = New-Item -ItemType Directory -Force -Path $destination
$stage = Join-Path $destination ('build-' + [Guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $stage
try {
    & $compiler /nologo /target:winexe /platform:anycpu /langversion:5 /optimize+ /codepage:65001 /utf8output /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Core.dll /reference:System.Web.Extensions.dll ("/win32manifest:" + (Join-Path $sources 'app.manifest')) ("/out:" + (Join-Path $stage 'SetupTemplate.exe')) (Join-Path $sources 'Setup.cs')
    if ($LASTEXITCODE -ne 0) { throw 'Setup compilation failed.' }
    & $compiler /nologo /target:winexe /platform:anycpu /langversion:5 /optimize+ /codepage:65001 /utf8output /reference:System.ServiceProcess.dll /reference:System.Core.dll /reference:System.Web.Extensions.dll ("/out:" + (Join-Path $stage 'SecurityPresenceService.exe')) (Join-Path $sources 'AgentService.cs')
    if ($LASTEXITCODE -ne 0) { throw 'Service compilation failed.' }
    foreach ($name in @('agent.ps1','install.template.ps1','uninstall.ps1')) {
        Copy-Item -LiteralPath (Join-Path $sources $name) -Destination (Join-Path $stage $name)
    }
    $hashes = [ordered]@{}
    foreach ($name in @('SetupTemplate.exe','SecurityPresenceService.exe','agent.ps1','install.template.ps1','uninstall.ps1')) {
        $hashes[$name] = (Get-FileHash -LiteralPath (Join-Path $stage $name) -Algorithm SHA256).Hash.ToLowerInvariant()
        Copy-Item -LiteralPath (Join-Path $stage $name) -Destination (Join-Path $destination $name) -Force
    }
    $manifest = [ordered]@{ version='0.5.0'; sha256=$hashes } | ConvertTo-Json -Depth 4
    [IO.File]::WriteAllText((Join-Path $destination 'manifest.json'),$manifest,(New-Object Text.UTF8Encoding($false)))
    Write-Output ('Generic, credential-free agent package ready: ' + $destination)
} finally {
    $resolved = [IO.Path]::GetFullPath($stage)
    if ([IO.Path]::GetDirectoryName($resolved) -ne [IO.Path]::GetFullPath($destination) -or -not [IO.Path]::GetFileName($resolved).StartsWith('build-')) { throw 'Unsafe build cleanup path.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
