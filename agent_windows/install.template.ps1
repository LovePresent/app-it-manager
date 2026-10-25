#requires -Version 5.1
[CmdletBinding()]
param([string]$SetupExecutablePath)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$taskName = 'SecurityPresenceAgent'
$installPath = Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'SecurityPresenceAgent'
$powershellPath = Join-Path ([Environment]::SystemDirectory) 'WindowsPowerShell\v1.0\powershell.exe'
# Only Windows' built-in modules are needed for privileged installation.
# Do not auto-import ScheduledTasks from a user-writable module directory.
$env:PSModulePath = Join-Path ([IO.Path]::GetDirectoryName($powershellPath)) 'Modules'
$markerName = '.security-presence-managed'
$markerValue = 'SecurityPresenceAgent/1'
$createdInstallDirectory = $false
$uninstallKeyPath = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\SecurityPresenceAgent'
$installedSetupPath = Join-Path $installPath 'SecurityPresenceSetup.exe'
$servicePath = Join-Path $installPath 'SecurityPresenceService.exe'
$scPath = Join-Path ([Environment]::GetFolderPath('Windows')) 'System32\sc.exe'
$serviceCreated = $false
$serviceWasStopped = $false
$serviceStartupChanged = $false
$serviceStartAttempted = $false
$previousService = $null
$previousServiceSddl = $null
$previousServiceWasRunning = $false
$fileBackups = @{}
$changedFiles = New-Object 'Collections.Generic.List[string]'
$previousTaskXml = $null
$previousTaskWasRunning = $false
$taskWasStopped = $false
$taskWasRegistered = $false
$registryWasChanged = $false
$registryBackup = $null
$machineRegistry = $null
$setupBytes = $null
$operationMutex = $null
$ownsOperationMutex = $false
$installPhase = 'validate_configuration'
$installationExitCode = 1
$statusShortcutPath = Join-Path ([Environment]::GetFolderPath('CommonPrograms')) 'App-IT-Manager 연결 상태.lnk'
$shortcutChanged = $false
$shortcutBackup = $null

function Set-InstallerPhase {
    param([string]$Phase)
    $script:installPhase = $Phase
    Write-Host ('SECURITY_PRESENCE_PHASE:' + $Phase)
}

function Test-IntegratedAgentPrefix {
    param([string]$Prefix)
    return ($Prefix -cin @('/api/v1/agent', '/manage/it/api/v1/agent'))
}

function Assert-InstallerEndpoint {
    param($Config)
    $mode = 'production'
    if ($Config.PSObject.Properties['deploymentMode']) { $mode = [string]$Config.deploymentMode }
    if ($mode -cnotin @('production', 'development')) { throw 'The deployment mode is invalid.' }
    $uri = [Uri]([string]$Config.serverUrl)
    if (-not $uri.IsAbsoluteUri -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -ne '/') { throw 'The server must be an origin without a path, query, or credentials.' }
    $address = $null
    $hostname = $uri.DnsSafeHost.TrimEnd('.').ToLowerInvariant()
    $local = $uri.IsLoopback -or $hostname -eq 'localhost' -or $hostname.EndsWith('.localhost')
    if ([Net.IPAddress]::TryParse($uri.DnsSafeHost.Trim('[', ']'), [ref]$address)) {
        if ($address.IsIPv4MappedToIPv6) { $address = $address.MapToIPv4() }
        $local = $local -or [Net.IPAddress]::IsLoopback($address) -or $address.Equals([Net.IPAddress]::Any) -or $address.Equals([Net.IPAddress]::IPv6Any)
    }
    if ($mode -ceq 'production' -and ($uri.Scheme -cne 'https' -or $local)) { throw 'Production installation requires a non-loopback HTTPS server.' }
    if ($uri.Scheme -cne 'https' -and -not ($mode -ceq 'development' -and $uri.Scheme -ceq 'http' -and $uri.IsLoopback)) { throw 'The server transport is invalid.' }
    $prefix = if ($Config.PSObject.Properties['apiPrefix']) { [string]$Config.apiPrefix } else { '/api' }
    if (-not (Test-IntegratedAgentPrefix $prefix) -and -not ($mode -ceq 'development' -and $prefix -ceq '/api')) { throw 'The API prefix is invalid for this deployment.' }
    if (-not $Config.PSObject.Properties['expectedServerId'] -or [string]$Config.expectedServerId -cnotmatch '^[a-f0-9]{64}$') { throw 'The installer has no valid server identity.' }
    return $uri
}

function Test-InstallerReadinessResponse {
    param($Response, [string]$ExpectedServerId)
    $version = $null
    $supportedVersion = $null -ne $Response -and $Response.PSObject.Properties['latestAgentVersion'] -and
        $Response.latestAgentVersion -is [string] -and [Version]::TryParse([string]$Response.latestAgentVersion, [ref]$version) -and
        $version -ge [Version]'0.5.0'
    $instant = [DateTimeOffset]::MinValue
    $serverTimeValid = $null -ne $Response -and $Response.PSObject.Properties['serverTime'] -and
        $Response.serverTime -is [string] -and $Response.serverTime -match '(?:Z|[+-]\d{2}:\d{2})$' -and
        [DateTimeOffset]::TryParse([string]$Response.serverTime, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::None, [ref]$instant)
    return ($null -ne $Response -and $Response.PSObject.Properties['product'] -and $Response.product -ceq 'app-it-manager-agent' -and
        $Response.PSObject.Properties['protocol'] -and $Response.protocol -is [int] -and $Response.protocol -eq 1 -and
        $Response.PSObject.Properties['registrationReady'] -and $Response.registrationReady -is [bool] -and $Response.registrationReady -and
        $ExpectedServerId -cmatch '^[a-f0-9]{64}$' -and $Response.PSObject.Properties['serverId'] -and $Response.serverId -ceq $ExpectedServerId -and
        $supportedVersion -and $serverTimeValid)
}

function Get-StatusLauncherArguments {
    $command = '$p = Start-Process -FilePath ''' + $installedSetupPath.Replace("'", "''") +
        ''' -Verb RunAs -WindowStyle Normal -ArgumentList ''--status'' -Wait -PassThru; exit $p.ExitCode'
    return '-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand ' + [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
}

function Assert-StatusShortcutDestination {
    Assert-NoReparsePath $statusShortcutPath
    $directory = [IO.Path]::GetDirectoryName($statusShortcutPath)
    $acl = Get-Acl -LiteralPath $directory
    $trusted = @('S-1-5-18', 'S-1-5-32-544')
    $writeRights = [Security.AccessControl.FileSystemRights]::Write -bor [Security.AccessControl.FileSystemRights]::Delete -bor
        [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor [Security.AccessControl.FileSystemRights]::ChangePermissions -bor [Security.AccessControl.FileSystemRights]::TakeOwnership
    foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
        if ($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Value -notin $trusted -and
            -not ($rule.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -and ($rule.FileSystemRights -band $writeRights)) {
            throw 'The shared Start Menu location is writable by an untrusted account.'
        }
    }
    if (Test-Path -LiteralPath $statusShortcutPath) {
        if (-not (Test-Path -LiteralPath $statusShortcutPath -PathType Leaf)) { throw 'A directory occupies the connection-status shortcut path.' }
        $fileAcl = Get-Acl -LiteralPath $statusShortcutPath
        if ($fileAcl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $trusted) { throw 'The existing shortcut has an unexpected owner.' }
        foreach ($rule in $fileAcl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
            if ($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Value -notin $trusted -and ($rule.FileSystemRights -band $writeRights)) {
                throw 'The existing shortcut is writable by an untrusted account.'
            }
        }
        $shell = New-Object -ComObject WScript.Shell
        $link = $null
        try {
            $link = $shell.CreateShortcut($statusShortcutPath)
            if ($link.TargetPath -ine $powershellPath -or $link.Arguments -cne (Get-StatusLauncherArguments) -or
                $link.Description -cne 'App-IT-Manager connection status (SecurityPresenceAgent/1)') { throw 'An unrelated shortcut already uses the connection-status name.' }
        } finally {
            if ($null -ne $link) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link) }
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)
        }
    }
}

function Write-AgentStatusShortcut {
    Assert-StatusShortcutDestination
    $temporary = Join-Path $installPath ('.status-link-' + [Guid]::NewGuid().ToString('N') + '.lnk')
    $shell = $null; $link = $null
    try {
        if (Test-Path -LiteralPath $temporary) { throw 'A temporary shortcut already exists.' }
        $shell = New-Object -ComObject WScript.Shell
        $link = $shell.CreateShortcut($temporary)
        $link.TargetPath = $powershellPath
        $link.Arguments = Get-StatusLauncherArguments
        $link.Description = 'App-IT-Manager connection status (SecurityPresenceAgent/1)'
        $link.WindowStyle = 7
        $link.WorkingDirectory = [IO.Path]::GetDirectoryName($powershellPath)
        $link.Save()
        if (Test-Path -LiteralPath $statusShortcutPath -PathType Leaf) {
            $script:shortcutBackup = @{ Bytes = [IO.File]::ReadAllBytes($statusShortcutPath); Acl = Get-Acl -LiteralPath $statusShortcutPath }
        } else {
            $empty = [IO.File]::Open($statusShortcutPath, 'CreateNew', 'Write', 'None'); $empty.Dispose()
        }
        $script:shortcutChanged = $true
        $acl = New-Object Security.AccessControl.FileSecurity
        $acl.SetAccessRuleProtection($true, $false)
        $admins = New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')
        $acl.SetOwner($admins)
        foreach ($sidText in @('S-1-5-18', 'S-1-5-32-544')) {
            $sid = New-Object Security.Principal.SecurityIdentifier($sidText)
            $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'Allow')))
        }
        $users = New-Object Security.Principal.SecurityIdentifier('S-1-5-32-545')
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($users, 'ReadAndExecute', 'Allow')))
        Set-Acl -LiteralPath $statusShortcutPath -AclObject $acl
        [IO.File]::WriteAllBytes($statusShortcutPath, [IO.File]::ReadAllBytes($temporary))
    } finally {
        if ($null -ne $link) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link) }
        if ($null -ne $shell) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) }
        Assert-NoReparsePath $temporary
        if (Test-Path -LiteralPath $temporary -PathType Leaf) { Remove-Item -LiteralPath $temporary -Force }
    }
}

function Assert-InstallerServerReady {
    param($Config)
    $uri = Assert-InstallerEndpoint $Config
    $prefix = if ($Config.PSObject.Properties['apiPrefix']) { [string]$Config.apiPrefix } else { '/api' }
    $request = $null; $response = $null; $stream = $null; $buffer = $null
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        $request = [Net.HttpWebRequest]::Create($uri.AbsoluteUri.TrimEnd('/') + $prefix + '/ready')
        $request.Method = 'GET'; $request.Accept = 'application/json'; $request.AllowAutoRedirect = $false
        $request.Timeout = 8000; $request.ReadWriteTimeout = 8000
        $response = $request.GetResponse()
        if ([int]$response.StatusCode -ge 300 -and [int]$response.StatusCode -lt 400) { $script:installationExitCode = 26; throw 'Readiness redirection refused.' }
        if ([int]$response.StatusCode -ne 200 -or $response.ContentType.Split(';')[0].Trim().ToLowerInvariant() -ne 'application/json' -or $response.ContentLength -gt 16384) { $script:installationExitCode = 27; throw 'Readiness response invalid.' }
        $stream = $response.GetResponseStream()
        $buffer = New-Object IO.MemoryStream
        $chunk = New-Object byte[] 1024
        while (($count = $stream.Read($chunk, 0, $chunk.Length)) -gt 0) {
            if ($buffer.Length + $count -gt 16384) { $script:installationExitCode = 27; throw 'Readiness response too large.' }
            $buffer.Write($chunk, 0, $count)
        }
        try { $body = [Text.Encoding]::UTF8.GetString($buffer.ToArray()) | ConvertFrom-Json }
        catch { $script:installationExitCode = 27; throw 'Readiness response is not valid JSON.' }
        if ($null -eq $body -or -not $body.PSObject.Properties['product'] -or $body.product -cne 'app-it-manager-agent') { $script:installationExitCode = 27; throw 'Readiness product mismatch.' }
        if ($body.PSObject.Properties['serverId'] -and $body.serverId -cne [string]$Config.expectedServerId) { $script:installationExitCode = 29; throw 'Readiness server identity mismatch.' }
        if ($body.PSObject.Properties['registrationReady'] -and $body.registrationReady -is [bool] -and -not $body.registrationReady) { $script:installationExitCode = 24; throw 'The server is not ready for registration.' }
        if (-not (Test-InstallerReadinessResponse $body ([string]$Config.expectedServerId))) { $script:installationExitCode = 27; throw 'The endpoint does not provide the expected server identity and agent protocol.' }
    } catch {
        if ($script:installationExitCode -eq 1) {
            $failure = $_.Exception.GetBaseException()
            $script:installationExitCode = 23
            if ($failure -is [Net.WebException]) {
                if ($failure.Status -in @([Net.WebExceptionStatus]::NameResolutionFailure, [Net.WebExceptionStatus]::ProxyNameResolutionFailure)) { $script:installationExitCode = 21 }
                elseif ($failure.Status -in @([Net.WebExceptionStatus]::TrustFailure, [Net.WebExceptionStatus]::SecureChannelFailure)) { $script:installationExitCode = 22 }
                elseif ($null -ne $failure.Response) {
                    $http = [int]$failure.Response.StatusCode
                    if ($http -eq 404) { $script:installationExitCode = 25 }
                    elseif ($http -in @(401, 403)) { $script:installationExitCode = 28 }
                    else { $script:installationExitCode = 24 }
                    $failure.Response.Dispose()
                }
            }
        }
        throw 'The server readiness check failed. No installation changes were started.'
    } finally {
        if ($null -ne $stream) { $stream.Dispose() }
        if ($null -ne $buffer) { $buffer.Dispose() }
        if ($null -ne $response) { $response.Dispose() }
        if ($null -ne $request) { $request.Abort() }
    }
}

function Assert-NoReparsePath {
    param([string]$Path)
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'A symbolic link or junction was found in the install path.' }
        }
        $parent = [IO.Directory]::GetParent($current)
        if ($null -eq $parent) { break }
        $current = $parent.FullName
    }
}

function Assert-PrivateDirectory {
    param([string]$Path)
    $acl = Get-Acl -LiteralPath $Path
    $trusted = @('S-1-5-18', 'S-1-5-32-544')
    $owner = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if ($owner -notin $trusted) { throw 'The existing install directory has an unexpected owner.' }
    foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
        if ($rule.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and $rule.IdentityReference.Value -notin $trusted) {
            throw 'The existing install directory is accessible to other users. Choose a clean installation.'
        }
    }
}

function Write-PrivateFile {
    param([string]$Path, [byte[]]$Bytes)
    if (-not $script:changedFiles.Contains($Path)) { $script:changedFiles.Add($Path) }
    # New empty files first inherit the private directory ACL; set an explicit
    # private ACL and owner before writing any script or credential bytes.
    if (-not (Test-Path -LiteralPath $Path)) {
        $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $stream.Dispose()
    }
    $fileAcl = New-Object Security.AccessControl.FileSecurity
    $fileAcl.SetAccessRuleProtection($true, $false)
    $systemSid = New-Object Security.Principal.SecurityIdentifier('S-1-5-18')
    $adminsSid = New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')
    $fileAcl.SetOwner($adminsSid)
    foreach ($sid in @($systemSid, $adminsSid)) {
        $rule = New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'Allow')
        $fileAcl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $Path -AclObject $fileAcl
    [IO.File]::WriteAllBytes($Path, $Bytes)
}

function Assert-OwnedUninstallKey {
    param([Microsoft.Win32.RegistryKey]$Key)
    if ($null -eq $Key) { return }
    if ($Key.GetValue('SecurityPresenceManaged', '') -ne $markerValue -or
        $Key.GetValue('InstallLocation', '') -ne $installPath -or $Key.SubKeyCount -ne 0) {
        throw 'A different application already uses the Windows Apps registration. Nothing was replaced.'
    }
}

function Get-AgentServiceSddl {
    # SYSTEM/Admin full control; authenticated users may only query config,
    # status and the security descriptor. No start/stop/delete/config changes.
    return 'D:P(A;;0xF01FF;;;SY)(A;;0xF01FF;;;BA)(A;;0x20005;;;AU)'
}

function Invoke-AgentSc {
    param([string[]]$Arguments)
    $output = & $scPath @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Windows service configuration failed.' }
    return $output
}

function Stop-OwnedAgentService {
    $controller = Get-Service -Name $taskName -ErrorAction Stop
    try {
        if ($controller.Status -ne 'Stopped') {
            Stop-Service -Name $taskName -ErrorAction Stop
            $controller.WaitForStatus([ServiceProcess.ServiceControllerStatus]::Stopped, [TimeSpan]::FromSeconds(25))
        }
    } finally { $controller.Dispose() }
}

function Test-AutomaticInstallConfiguration {
    param($Config)
    foreach ($name in @('deviceId', 'deviceToken', 'enrollmentToken')) {
        if ($Config.PSObject.Properties[$name] -and -not [string]::IsNullOrEmpty([string]$Config.$name)) { return $false }
    }
    return ($Config.PSObject.Properties['registrationMode'] -and $Config.registrationMode -ceq 'automatic' -and
        $Config.PSObject.Properties['apiPrefix'] -and (Test-IntegratedAgentPrefix ([string]$Config.apiPrefix)) -and
        $Config.PSObject.Properties['ticketId'] -and [string]$Config.ticketId -match '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$' -and
        [string]$Config.ticketId -ne '00000000-0000-0000-0000-000000000000' -and
        $Config.PSObject.Properties['registrationToken'] -and [string]$Config.registrationToken -match '^[A-Za-z0-9_-]{43}$')
}

function Merge-AgentReinstallConfiguration {
    param($Incoming, $Existing)
    $merged = $Incoming | ConvertTo-Json -Depth 8 | ConvertFrom-Json
    $incomingMode = if ($Incoming.PSObject.Properties['deploymentMode']) { [string]$Incoming.deploymentMode } else { 'production' }
    $incomingServerId = if ($Incoming.PSObject.Properties['expectedServerId']) { [string]$Incoming.expectedServerId } else { '' }
    $incomingPrefix = '/api'; $existingPrefix = '/api'
    if ($Incoming.PSObject.Properties['apiPrefix']) { $incomingPrefix = [string]$Incoming.apiPrefix }
    if ($Existing.PSObject.Properties['apiPrefix']) { $existingPrefix = [string]$Existing.apiPrefix }
    $sameServer = ([Uri]$Existing.serverUrl).AbsoluteUri.TrimEnd('/') -ceq ([Uri]$Incoming.serverUrl).AbsoluteUri.TrimEnd('/') -and $incomingPrefix -ceq $existingPrefix
    $hasIdentity = $Existing.PSObject.Properties['deviceId'] -and [string]$Existing.deviceId -match '^[A-Za-z0-9_-]{1,100}$'
    $hasToken = $Existing.PSObject.Properties['deviceToken'] -and [string]$Existing.deviceToken -match '^[A-Za-z0-9_-]{32,256}$'
    $priorIdentity = $hasIdentity -or $hasToken -or ($Existing.PSObject.Properties['inventoryDeviceId'] -and $Existing.inventoryDeviceId) -or
        ($Existing.PSObject.Properties['hadPriorIdentity'] -and $Existing.hadPriorIdentity -eq $true)
    if (Test-AutomaticInstallConfiguration $Incoming) {
        if ($Existing.PSObject.Properties['expectedServerId'] -and $incomingServerId -and
            [string]$Existing.expectedServerId -cne $incomingServerId) { throw 'The existing registration belongs to a different server identity. Administrator repair is required.' }
        if ($priorIdentity -and -not $sameServer) { throw 'Remove the previously registered installation with administrator approval before switching registration servers.' }
        if ($priorIdentity -and $sameServer) {
            if (-not $hasIdentity -or (-not $hasToken -and -not $Existing.PSObject.Properties['enrollmentToken'])) { throw 'The existing registration requires an administrator repair installer.' }
            $merged = $Existing | ConvertTo-Json -Depth 8 | ConvertFrom-Json
            $merged.serverUrl = [string]$Incoming.serverUrl
            $merged.heartbeatIntervalSeconds = 15
            $merged | Add-Member -NotePropertyName apiPrefix -NotePropertyValue $incomingPrefix -Force
            $merged | Add-Member -NotePropertyName deploymentMode -NotePropertyValue $incomingMode -Force
            if ($incomingServerId) { $merged | Add-Member -NotePropertyName expectedServerId -NotePropertyValue $incomingServerId -Force }
            $merged | Add-Member -NotePropertyName hadPriorIdentity -NotePropertyValue $true -Force
            $merged | Add-Member -NotePropertyName registrationCreated -NotePropertyValue $false -Force
            foreach ($name in @('registrationToken', 'ticketId', 'clientNonce', 'registrationHardware')) { $merged.PSObject.Properties.Remove($name) }
            return $merged
        }
        if ($sameServer -and (Test-AutomaticInstallConfiguration $Existing) -and $Existing.PSObject.Properties['clientNonce']) {
            if ([string]$Existing.clientNonce -notmatch '^[A-Za-z0-9_-]{43}$') { throw 'The saved registration nonce is invalid.' }
            # The server may already have committed this request even when its
            # response was lost. Keep the entire claim, including its ticket,
            # when a newer EXE is used; a new nonce could strand that identity.
            $merged = $Existing | ConvertTo-Json -Depth 8 | ConvertFrom-Json
            $merged.serverUrl = [string]$Incoming.serverUrl
            $merged.heartbeatIntervalSeconds = 15
            $merged | Add-Member -NotePropertyName deploymentMode -NotePropertyValue $incomingMode -Force
            if ($incomingServerId) { $merged | Add-Member -NotePropertyName expectedServerId -NotePropertyValue $incomingServerId -Force }
        }
        return $merged
    }
    if ($sameServer -and $hasIdentity -and $hasToken -and $Incoming.deviceId -ceq $Existing.deviceId) {
        $merged | Add-Member -NotePropertyName deviceToken -NotePropertyValue ([string]$Existing.deviceToken) -Force
        foreach ($name in @('inventoryDeviceId', 'serialNumber', 'hadPriorIdentity')) {
            if ($Existing.PSObject.Properties[$name]) { $merged | Add-Member -NotePropertyName $name -NotePropertyValue $Existing.$name -Force }
        }
    }
    return $merged
}

try {
    $configBytes = [Convert]::FromBase64String('__CONFIG_BASE64__')
    $agentBytes = [Convert]::FromBase64String('__AGENT_BASE64__')
    $uninstallBytes = [Convert]::FromBase64String('__UNINSTALL_BASE64__')
    $serviceBytes = [Convert]::FromBase64String('__SERVICE_BASE64__')
    if ($serviceBytes.Length -lt 512 -or $serviceBytes[0] -ne 77 -or $serviceBytes[1] -ne 90) { throw 'The Windows service payload is invalid.' }
    $config = [Text.Encoding]::UTF8.GetString($configBytes) | ConvertFrom-Json
    $serverUri = Assert-InstallerEndpoint $config
    if (-not $config.PSObject.Properties['deploymentMode']) { $config | Add-Member -NotePropertyName deploymentMode -NotePropertyValue 'production' }
    $apiPrefix = '/api'
    if ($config.PSObject.Properties['apiPrefix']) { $apiPrefix = [string]$config.apiPrefix }
    if ($apiPrefix -cnotin @('/api', '/api/v1/agent', '/manage/it/api/v1/agent')) { throw 'Unsupported agent API prefix.' }
    $hasDeviceToken = $config.PSObject.Properties['deviceToken'] -and [string]$config.deviceToken -match '^[A-Za-z0-9_-]{32,256}$'
    $hasEnrollment = $config.PSObject.Properties['enrollmentToken'] -and [string]$config.enrollmentToken -match '^[A-Za-z0-9_-]{24,256}$'
    $automaticRegistration = Test-AutomaticInstallConfiguration $config
    if ($config.PSObject.Properties['registrationMode'] -and $config.registrationMode -ceq 'automatic' -and
        ($config.PSObject.Properties['ticketId'] -or $config.PSObject.Properties['registrationToken']) -and -not $automaticRegistration) { throw 'The automatic registration configuration is invalid or mixed with an issued identity.' }
    $hasIdentity = $config.PSObject.Properties['deviceId'] -and [string]$config.deviceId -match '^[A-Za-z0-9_-]{1,100}$'
    $validatedInterval = 0
    if ((-not $automaticRegistration -and (-not $hasIdentity -or (-not $hasDeviceToken -and -not $hasEnrollment))) -or
        -not [int]::TryParse([string]$config.heartbeatIntervalSeconds, [ref]$validatedInterval) -or $validatedInterval -ne 15) { throw 'The installer configuration is invalid.' }
    Set-InstallerPhase 'server_preflight'
    Assert-InstallerServerReady $config
    $configBytes = [Text.Encoding]::UTF8.GetBytes(($config | ConvertTo-Json -Compress -Depth 8))
    Set-InstallerPhase 'validate_existing'

    Write-Host ('Install directory: ' + $installPath)
    Write-Host ('Windows service: ' + $taskName + ' (LocalSystem, automatic startup; ordinary users may query status only)')
    Write-Host ('Server: ' + $serverUri.GetLeftPart([UriPartial]::Authority))
    Write-Host 'Reports presence every 15 seconds: device ID, computer name, Windows version, Windows boot time and agent version.'
    Write-Host 'Also reports network adapter names, physical-adapter flags, MAC addresses, IPv4 addresses/subnet masks and IPv6 addresses.'
    Write-Host 'Allows remote restart and shutdown when requested through the dashboard. Open applications can prevent shutdown; force-close is not used.'
    Write-Host 'Can relay approved Wake-on-LAN packets only to a broadcast address on its own network. Administrators can stop or remove the service.'
    if (Test-IntegratedAgentPrefix $apiPrefix) { Write-Host 'Removal also requires a one-time approval code issued by an App IT Manager administrator.' }
    Write-Host 'Does not collect files, screen content, browsing history or keystrokes.'
    if ($automaticRegistration) { Write-Host 'Registers this PC automatically using its hardware UUID and BIOS serial number. A never-registered installation can be removed by a Windows administrator.' }

    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host 'Administrator approval is needed to install the Windows presence agent.'
        if (-not $PSCommandPath) { throw 'Save this installer as a .ps1 file before running it.' }
        # Pass only the script path to UAC. Credentials remain inside the installer file.
        $arguments = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '"'
        if ($SetupExecutablePath) {
            if ($SetupExecutablePath.IndexOf('"') -ge 0) { throw 'The setup executable path is invalid.' }
            $arguments += ' -SetupExecutablePath "' + $SetupExecutablePath + '"'
        }
        $elevated = Start-Process -FilePath $powershellPath -Verb RunAs -WindowStyle Hidden -ArgumentList $arguments -PassThru -Wait
        if ($elevated.ExitCode -ne 0) {
            throw ('The elevated installer failed (exit code ' + $elevated.ExitCode + '). Run this saved installer from an Administrator PowerShell window to see the error.')
        }
        Write-Host 'Installation complete. The presence agent has been started.'
        Write-Host ('To remove, run as administrator: & "' + (Join-Path $installPath 'uninstall.ps1') + '"')
        Write-Host 'This downloaded installer contains this device credential. Delete your downloaded copy after installation.'
        exit 0
    }

    $mutexSecurity = New-Object Security.AccessControl.MutexSecurity
    $mutexSecurity.SetAccessRuleProtection($true, $false)
    foreach ($sidText in @('S-1-5-18', 'S-1-5-32-544')) {
        $mutexSid = New-Object Security.Principal.SecurityIdentifier($sidText)
        $mutexRule = New-Object Security.AccessControl.MutexAccessRule($mutexSid, 'FullControl', 'Allow')
        $mutexSecurity.AddAccessRule($mutexRule)
    }
    $createdMutex = $false
    $operationMutex = New-Object Threading.Mutex($false, 'Global\SecurityPresenceAgentMaintenance', [ref]$createdMutex, $mutexSecurity)
    try { $ownsOperationMutex = $operationMutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $ownsOperationMutex = $true }
    if (-not $ownsOperationMutex) { throw 'Another Security Presence installation or removal is already running. Try again after it finishes.' }
    Assert-StatusShortcutDestination

    if ($SetupExecutablePath) {
        $SetupExecutablePath = [IO.Path]::GetFullPath($SetupExecutablePath)
        Assert-NoReparsePath $SetupExecutablePath
        if ([IO.Path]::GetExtension($SetupExecutablePath) -ne '.exe' -or
            -not (Test-Path -LiteralPath $SetupExecutablePath -PathType Leaf)) {
            throw 'The native setup executable was not found.'
        }
        # Lock the source against writes/replacement during validation and read.
        $setupStream = [IO.File]::Open($SetupExecutablePath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        try {
            if ($setupStream.Length -lt 256 -or $setupStream.Length -gt 33554432) { throw 'The setup executable has an invalid size.' }
            $setupReader = New-Object IO.BinaryReader($setupStream)
            if ($setupReader.ReadUInt16() -ne 0x5A4D) { throw 'The setup file is not a Windows executable.' }
            $setupStream.Position = 60
            $peOffset = $setupReader.ReadInt32()
            if ($peOffset -lt 64 -or $peOffset -gt ($setupStream.Length - 4)) { throw 'The setup executable header is invalid.' }
            $setupStream.Position = $peOffset
            if ($setupReader.ReadUInt32() -ne 0x00004550) { throw 'The setup executable header is invalid.' }
            $setupVersion = [Diagnostics.FileVersionInfo]::GetVersionInfo($SetupExecutablePath)
            if ($setupVersion.ProductName -ne 'Security Presence Agent' -or $setupVersion.CompanyName -ne 'Security Presence') {
                throw 'The setup executable does not identify this application.'
            }
            $setupStream.Position = 0
            $setupBytes = $setupReader.ReadBytes([int]$setupStream.Length)
            if ($setupBytes.Length -ne $setupStream.Length) { throw 'The setup executable could not be read completely.' }
        } finally {
            $setupStream.Dispose()
        }
    }

    # Reject a task-name conflict before creating any installation files.
    $existingTask = Get-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction SilentlyContinue
    if ($existingTask) {
        $expectedArgument = '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + (Join-Path $installPath 'agent.ps1') + '"'
        if (@($existingTask.Actions).Count -ne 1 -or $existingTask.Actions[0].Execute -ne $powershellPath -or $existingTask.Actions[0].Arguments -ne $expectedArgument) {
            throw 'A different scheduled task already uses this name. Nothing was replaced.'
        }
        $previousTaskXml = Export-ScheduledTask -TaskName $taskName -TaskPath '\'
        $previousTaskWasRunning = $existingTask.State -eq 'Running'
    }

    $previousService = Get-CimInstance -ClassName Win32_Service -Filter "Name='SecurityPresenceAgent'" -ErrorAction Stop
    if ($null -ne $previousService) {
        if ($previousService.PathName.Trim() -ne ('"' + $servicePath + '"') -or $previousService.StartName -ne 'LocalSystem') {
            throw 'A different Windows service already uses this name. Nothing was replaced.'
        }
        $previousServiceWasRunning = $previousService.State -eq 'Running'
        $securityLines = @(Invoke-AgentSc @('sdshow', $taskName) | Where-Object { [string]$_ -match '^[OGDS]:' })
        if ($securityLines.Count -ne 1) { throw 'The existing service security descriptor could not be backed up.' }
        $previousServiceSddl = [string]$securityLines[0]
    }

    $registryView = [Microsoft.Win32.RegistryView]::Default
    if ([Environment]::Is64BitOperatingSystem) { $registryView = [Microsoft.Win32.RegistryView]::Registry64 }
    $machineRegistry = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine, $registryView)
    $previousUninstallKey = $machineRegistry.OpenSubKey($uninstallKeyPath, $true)
    try {
        Assert-OwnedUninstallKey $previousUninstallKey
        if ($null -ne $previousUninstallKey) {
            $registryBackup = @{}
            foreach ($name in $previousUninstallKey.GetValueNames()) {
                $registryBackup[$name] = @{
                    Value = $previousUninstallKey.GetValue($name, $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
                    Kind = $previousUninstallKey.GetValueKind($name)
                }
            }
        }
    } finally {
        if ($null -ne $previousUninstallKey) { $previousUninstallKey.Dispose() }
    }

    Set-InstallerPhase 'protect_files'
    Assert-NoReparsePath $installPath
    if (Test-Path -LiteralPath $installPath) {
        if (-not (Get-Item -LiteralPath $installPath -Force).PSIsContainer) { throw 'The installation path is not a directory.' }
        Assert-PrivateDirectory $installPath
        $markerPath = Join-Path $installPath $markerName
        Assert-NoReparsePath $markerPath
        if (-not (Test-Path -LiteralPath $markerPath) -or (Get-Content -LiteralPath $markerPath -Raw).Trim() -ne $markerValue) {
            throw 'The destination already exists and is not a managed presence-agent installation.'
        }
    } else {
        # Create the directory with its private ACL atomically, before writing secrets.
        $directoryAcl = New-Object Security.AccessControl.DirectorySecurity
        $directoryAcl.SetAccessRuleProtection($true, $false)
        $systemSid = New-Object Security.Principal.SecurityIdentifier('S-1-5-18')
        $adminsSid = New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')
        $directoryAcl.SetOwner($adminsSid)
        foreach ($sid in @($systemSid, $adminsSid)) {
            $rule = New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'ContainerInherit, ObjectInherit', 'None', 'Allow')
            $directoryAcl.AddAccessRule($rule)
        }
        $null = [IO.Directory]::CreateDirectory($installPath, $directoryAcl)
        $createdInstallDirectory = $true
        Assert-NoReparsePath $installPath
        Assert-PrivateDirectory $installPath
        # Mark a newly created, verified private directory immediately so an
        # interrupted installation can be retried without claiming other data.
        Write-PrivateFile (Join-Path $installPath $markerName) ([Text.Encoding]::UTF8.GetBytes($markerValue))
    }

    $managedFiles = @('agent.ps1', 'config.json', 'uninstall.ps1', 'SecurityPresenceSetup.exe', 'SecurityPresenceService.exe', $markerName)
    foreach ($fileName in $managedFiles) {
        $filePath = Join-Path $installPath $fileName
        Assert-NoReparsePath $filePath
        if (Test-Path -LiteralPath $filePath) {
            if ((Get-Item -LiteralPath $filePath -Force).PSIsContainer) { throw 'An unexpected directory occupies an agent file path.' }
            Assert-PrivateDirectory $filePath
            if (-not $createdInstallDirectory) {
                $fileBackups[$filePath] = @{
                    Bytes = [IO.File]::ReadAllBytes($filePath)
                    Acl = Get-Acl -LiteralPath $filePath
                }
            }
        }
    }
    # The command journal prevents replay across restart and reinstallation.
    # Validate any existing files but never reset or replace their contents.
    foreach ($fileName in @('command-history.json', 'command-history.json.tmp')) {
        $preservedPath = Join-Path $installPath $fileName
        Assert-NoReparsePath $preservedPath
        if (Test-Path -LiteralPath $preservedPath) {
            if ((Get-Item -LiteralPath $preservedPath -Force).PSIsContainer) { throw 'An unexpected directory occupies a command history path.' }
            Assert-PrivateDirectory $preservedPath
        }
    }
    if ($null -ne $setupBytes -and $SetupExecutablePath -ne $installedSetupPath -and
        (Test-Path -LiteralPath $installedSetupPath -PathType Leaf)) {
        try {
            # Fail before stopping the agent if another setup window still has
            # the installed executable mapped and prevents a safe replacement.
            $setupProbe = [IO.File]::Open($installedSetupPath, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
            $setupProbe.Dispose()
        } catch {
            throw 'Close other Security Presence setup windows, then run this installer again.'
        }
    }

    Set-InstallerPhase 'stop_previous'
    if ($existingTask) {
        Stop-ScheduledTask -TaskName $taskName -TaskPath '\'
        $taskWasStopped = $true
        $stopDeadline = [DateTime]::UtcNow.AddSeconds(15)
        do {
            $stoppingTask = Get-ScheduledTask -TaskName $taskName -TaskPath '\'
            if ($stoppingTask.State -ne 'Running' -and $stoppingTask.State -ne 'Queued') { break }
            if ([DateTime]::UtcNow -ge $stopDeadline) { throw 'The previous agent did not stop in time. Run the installer again after it stops.' }
            Start-Sleep -Milliseconds 200
        } while ($true)
    }
    if ($null -ne $previousService) {
        # Disabling also blocks any SCM recovery restart already queued before
        # this update. Preserve the original mode even if stopping then fails.
        Set-Service -Name $taskName -StartupType Disabled
        $serviceStartupChanged = $true
        Stop-OwnedAgentService
        $serviceWasStopped = $true
        $deadline = [DateTime]::UtcNow.AddSeconds(10)
        do {
            try { $probe = [IO.File]::Open($servicePath, 'Open', 'ReadWrite', 'None'); $probe.Dispose(); break }
            catch { if ([DateTime]::UtcNow -ge $deadline) { throw 'The previous service executable is still in use.' }; Start-Sleep -Milliseconds 200 }
        } while ($true)
    }
    # Capture the final config after the old process stops: enrollment may have
    # atomically saved a token while this installer was validating the files.
    $existingConfigPath = Join-Path $installPath 'config.json'
    Set-InstallerPhase 'preserve_configuration'
    if (Test-Path -LiteralPath $existingConfigPath -PathType Leaf) {
        $fileBackups[$existingConfigPath] = @{ Bytes = [IO.File]::ReadAllBytes($existingConfigPath); Acl = Get-Acl -LiteralPath $existingConfigPath }
        try {
            $existingConfig = [Text.Encoding]::UTF8.GetString($fileBackups[$existingConfigPath].Bytes) | ConvertFrom-Json
            $config = Merge-AgentReinstallConfiguration -Incoming $config -Existing $existingConfig
            $configBytes = [Text.Encoding]::UTF8.GetBytes(($config | ConvertTo-Json -Compress -Depth 8))
        } catch { throw 'The existing configuration could not be safely preserved.' }
    }

    foreach ($runtimeName in @('runtime-status.json', 'runtime-status.json.tmp')) {
        $runtimePath = Join-Path $installPath $runtimeName
        Assert-NoReparsePath $runtimePath
        if (Test-Path -LiteralPath $runtimePath) {
            if (-not (Test-Path -LiteralPath $runtimePath -PathType Leaf)) { throw 'A runtime status path is not a file.' }
            Assert-PrivateDirectory $runtimePath
            if ((Get-Item -LiteralPath $runtimePath).Length -gt 16384) { throw 'The previous runtime status file is too large.' }
            $fileBackups[$runtimePath] = @{ Bytes = [IO.File]::ReadAllBytes($runtimePath); Acl = Get-Acl -LiteralPath $runtimePath }
            if (-not $changedFiles.Contains($runtimePath)) { $changedFiles.Add($runtimePath) }
            Remove-Item -LiteralPath $runtimePath -Force
        }
    }
    Set-InstallerPhase 'write_files'
    Write-PrivateFile (Join-Path $installPath $markerName) ([Text.Encoding]::UTF8.GetBytes($markerValue))
    Write-PrivateFile (Join-Path $installPath 'agent.ps1') $agentBytes
    Write-PrivateFile (Join-Path $installPath 'config.json') $configBytes
    Write-PrivateFile (Join-Path $installPath 'uninstall.ps1') $uninstallBytes
    Write-PrivateFile $servicePath $serviceBytes
    if ($null -ne $setupBytes -and $SetupExecutablePath -ne $installedSetupPath) {
        Write-PrivateFile $installedSetupPath $setupBytes
    }

    Set-InstallerPhase 'configure_service'
    if ($null -eq $previousService) {
        $null = New-Service -Name $taskName -BinaryPathName ('"' + $servicePath + '"') -DisplayName 'Security Presence Agent' -StartupType Automatic -Description 'Reports PC presence and network inventory; executes administrator-approved power/WOL requests. Administrators can stop or uninstall.'
        $serviceCreated = $true
    } else { Set-Service -Name $taskName -StartupType Automatic }
    $null = Invoke-AgentSc @('sdset', $taskName, (Get-AgentServiceSddl))
    if ($serviceCreated) {
        $recoveryProcess = Start-Process -FilePath $servicePath -ArgumentList '--configure-recovery' -WindowStyle Hidden -PassThru -Wait
        if ($recoveryProcess.ExitCode -ne 0) { throw 'Windows service recovery configuration failed.' }
    } else {
        $diagnosticsProcess = Start-Process -FilePath $servicePath -ArgumentList '--configure-diagnostics' -WindowStyle Hidden -PassThru -Wait
        if ($diagnosticsProcess.ExitCode -ne 0) { throw 'Windows event-log diagnostics configuration failed.' }
    }

    Set-InstallerPhase 'register_application'
    $registryWasChanged = $true
    $uninstallKey = $machineRegistry.CreateSubKey($uninstallKeyPath)
    try {
        $uninstallKey.SetValue('SecurityPresenceManaged', $markerValue, [Microsoft.Win32.RegistryValueKind]::String)
        $uninstallKey.SetValue('DisplayName', 'Security Presence Agent', [Microsoft.Win32.RegistryValueKind]::String)
        $uninstallKey.SetValue('DisplayVersion', '0.5.0', [Microsoft.Win32.RegistryValueKind]::String)
        $uninstallKey.SetValue('Publisher', 'Security Presence', [Microsoft.Win32.RegistryValueKind]::String)
        $uninstallKey.SetValue('InstallLocation', $installPath, [Microsoft.Win32.RegistryValueKind]::String)
        $uninstallKey.SetValue('InstallDate', (Get-Date).ToString('yyyyMMdd'), [Microsoft.Win32.RegistryValueKind]::String)
        if (Test-Path -LiteralPath $installedSetupPath -PathType Leaf) {
            # Settings initially runs without elevation and cannot read the
            # credential-bearing private EXE. An accessible system PowerShell
            # launcher requests UAC first, then opens the interactive GUI.
            $innerTarget = $installedSetupPath
            $innerArguments = '--uninstall'
            $innerWindowStyle = 'Normal'
            $displayIcon = '"' + $installedSetupPath + '",0'
        } else {
            $innerTarget = $powershellPath
            $innerArguments = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $installPath 'uninstall.ps1') + '"'
            $innerWindowStyle = if (Test-IntegratedAgentPrefix $apiPrefix) { 'Normal' } else { 'Hidden' }
            $displayIcon = '"' + $powershellPath + '",0'
        }
        # Encoding handles Windows quoting; this launcher contains no token.
        $fallbackCommand = '$p = Start-Process -FilePath ''' + $innerTarget.Replace("'", "''") +
            ''' -Verb RunAs -WindowStyle ' + $innerWindowStyle + ' -ArgumentList ''' + $innerArguments.Replace("'", "''") +
            ''' -Wait -PassThru; exit $p.ExitCode'
        $encodedFallback = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($fallbackCommand))
        $uninstallCommand = '"' + $powershellPath + '" -NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand ' + $encodedFallback
        $uninstallKey.SetValue('UninstallString', $uninstallCommand, [Microsoft.Win32.RegistryValueKind]::String)
        $uninstallKey.SetValue('DisplayIcon', $displayIcon, [Microsoft.Win32.RegistryValueKind]::String)
        $uninstallKey.SetValue('NoModify', 1, [Microsoft.Win32.RegistryValueKind]::DWord)
        $uninstallKey.SetValue('NoRepair', 1, [Microsoft.Win32.RegistryValueKind]::DWord)
    } finally {
        $uninstallKey.Dispose()
    }
    if (Test-Path -LiteralPath $installedSetupPath -PathType Leaf) {
        Set-InstallerPhase 'create_status_shortcut'
        Write-AgentStatusShortcut
    }
    if ($existingTask) { Unregister-ScheduledTask -TaskName $taskName -TaskPath '\' -Confirm:$false }
    Set-InstallerPhase 'start_service'
    $serviceStartAttempted = $true
    Start-Service -Name $taskName -ErrorAction Stop
    $controller = Get-Service -Name $taskName
    try { $controller.WaitForStatus([ServiceProcess.ServiceControllerStatus]::Running, [TimeSpan]::FromSeconds(20)) }
    finally { $controller.Dispose() }
    Write-Host 'Windows service files are installed. Authenticated server connection must still be verified.'
    Write-Host 'Windows Settings > Apps lists Security Presence Agent for removal.'
    Write-Host ('To remove, run as administrator: & "' + (Join-Path $installPath 'uninstall.ps1') + '"')
    Write-Host 'This downloaded installer contains this device credential. Delete your downloaded copy after installation.'
} catch {
    $installationError = $_.Exception.Message
    if ($serviceStartAttempted) {
        # A worker may have consumed an enrollment ticket before SCM's start
        # confirmation failed. Never discard or roll back that uncertain identity.
        Set-InstallerPhase 'start_service_uncertain'
        Write-Error 'The managed files were retained because service startup or registration may already have begun. Check connection status and repair this installation; do not delete its registration files.' -ErrorAction Continue
        exit 76
    }
    $rollbackFailed = $false
    $safeToRestoreFiles = $true
    if ($shortcutChanged) {
        try {
            Assert-NoReparsePath $statusShortcutPath
            if ($null -ne $shortcutBackup) {
                [IO.File]::WriteAllBytes($statusShortcutPath, $shortcutBackup.Bytes)
                Set-Acl -LiteralPath $statusShortcutPath -AclObject $shortcutBackup.Acl
            } elseif (Test-Path -LiteralPath $statusShortcutPath -PathType Leaf) { Remove-Item -LiteralPath $statusShortcutPath -Force }
        } catch { $rollbackFailed = $true }
    }
    if ($serviceCreated -or $serviceStartAttempted) {
        try {
            Set-Service -Name $taskName -StartupType Disabled
            Stop-OwnedAgentService
            if ($serviceCreated) { $null = Invoke-AgentSc @('delete', $taskName) }
        } catch { $rollbackFailed = $true; $safeToRestoreFiles = $false }
    }
    if ($taskWasRegistered) {
        try {
            Stop-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction SilentlyContinue
            $stopDeadline = [DateTime]::UtcNow.AddSeconds(15)
            do {
                $rollbackTask = Get-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction SilentlyContinue
                if ($null -eq $rollbackTask -or ($rollbackTask.State -ne 'Running' -and $rollbackTask.State -ne 'Queued')) { break }
                if ([DateTime]::UtcNow -ge $stopDeadline) { throw 'The new task did not stop for rollback.' }
                Start-Sleep -Milliseconds 200
            } while ($true)
            if ($null -ne $rollbackTask) { Unregister-ScheduledTask -TaskName $taskName -TaskPath '\' -Confirm:$false }
        } catch { $rollbackFailed = $true }
    }
    foreach ($changedPath in @($changedFiles)) {
        if (-not $safeToRestoreFiles) { break }
        try {
            Assert-NoReparsePath $changedPath
            Assert-NoReparsePath $installPath
            Assert-PrivateDirectory $installPath
            if ($fileBackups.ContainsKey($changedPath)) {
                [IO.File]::WriteAllBytes($changedPath, $fileBackups[$changedPath].Bytes)
                Set-Acl -LiteralPath $changedPath -AclObject $fileBackups[$changedPath].Acl
            } elseif (Test-Path -LiteralPath $changedPath -PathType Leaf) {
                Remove-Item -LiteralPath $changedPath -Force
            }
        } catch { $rollbackFailed = $true }
    }
    if ($registryWasChanged -and $null -ne $machineRegistry) {
        try {
            if ($null -ne $registryBackup) {
                $restoreKey = $machineRegistry.CreateSubKey($uninstallKeyPath)
                try {
                    foreach ($name in $restoreKey.GetValueNames()) { $restoreKey.DeleteValue($name, $false) }
                    foreach ($name in $registryBackup.Keys) { $restoreKey.SetValue($name, $registryBackup[$name].Value, $registryBackup[$name].Kind) }
                } finally { $restoreKey.Dispose() }
            } else {
                # Delete only this exact child key; never recurse into other keys.
                $machineRegistry.DeleteSubKey($uninstallKeyPath, $false)
            }
        } catch { $rollbackFailed = $true }
    }
    if ($null -ne $previousService -and ($serviceWasStopped -or $serviceStartupChanged) -and $safeToRestoreFiles) {
        try {
            $previousStartup = @{ Auto = 'Automatic'; Manual = 'Manual'; Disabled = 'Disabled' }[[string]$previousService.StartMode]
            Set-Service -Name $taskName -StartupType $previousStartup
            $null = Invoke-AgentSc @('sdset', $taskName, $previousServiceSddl)
            if ($previousServiceWasRunning) { Start-Service -Name $taskName }
        } catch { $rollbackFailed = $true }
    }
    if ($previousTaskXml -and $taskWasStopped -and $safeToRestoreFiles) {
        try {
            $null = Register-ScheduledTask -TaskName $taskName -TaskPath '\' -Xml $previousTaskXml -Force
            if ($previousTaskWasRunning) { Start-ScheduledTask -TaskName $taskName -TaskPath '\' }
        } catch { $rollbackFailed = $true }
    }
    if ($createdInstallDirectory -and $safeToRestoreFiles) {
        try {
            Assert-NoReparsePath $installPath
            Assert-PrivateDirectory $installPath
            # A task started during this attempt can have created its known
            # logs and instance lock. Remove only those exact regular files.
            foreach ($logName in @('agent.log', 'agent.log.1', 'service.log', 'service.log.1', '.agent.lock')) {
                $rollbackLog = Join-Path $installPath $logName
                Assert-NoReparsePath $rollbackLog
                if (Test-Path -LiteralPath $rollbackLog -PathType Leaf) { Remove-Item -LiteralPath $rollbackLog -Force }
            }
            if (@(Get-ChildItem -LiteralPath $installPath -Force).Count -eq 0) {
                [IO.Directory]::Delete($installPath, $false)
            } else {
                # Preserve unexpected or locked files and a managed marker so
                # a subsequent installer can repair this partial installation.
                Write-PrivateFile (Join-Path $installPath $markerName) ([Text.Encoding]::UTF8.GetBytes($markerValue))
                $rollbackFailed = $true
            }
        } catch { $rollbackFailed = $true }
    }
    if ($rollbackFailed) { Set-InstallerPhase 'rollback_failed'; $installationError += ' Some rollback steps failed; rerun this installer as administrator to repair the installation.' }
    Write-Error ('Installation failed: ' + $installationError) -ErrorAction Continue
    exit $installationExitCode
} finally {
    if ($null -ne $machineRegistry) { $machineRegistry.Dispose() }
    if ($ownsOperationMutex -and $null -ne $operationMutex) { $operationMutex.ReleaseMutex() }
    if ($null -ne $operationMutex) { $operationMutex.Dispose() }
}
