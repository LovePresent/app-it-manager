#requires -Version 5.1
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$taskName = 'SecurityPresenceAgent'
$installPath = [IO.Path]::GetFullPath((Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'SecurityPresenceAgent'))
$powershellPath = Join-Path ([Environment]::SystemDirectory) 'WindowsPowerShell\v1.0\powershell.exe'
$env:PSModulePath = Join-Path ([IO.Path]::GetDirectoryName($powershellPath)) 'Modules'
$uninstallKeyPath = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\SecurityPresenceAgent'
$machineRegistry = $null
$hasOwnedUninstallKey = $false
$operationMutex = $null
$ownsOperationMutex = $false
$servicePath = Join-Path $installPath 'SecurityPresenceService.exe'
$scPath = Join-Path ([Environment]::GetFolderPath('Windows')) 'System32\sc.exe'
$neverRegisteredAutomatic = $false
$startupChanged = $false
$destructiveCleanupStarted = $false
$originalService = $null
$originalTask = $null
$uninstallReceipt = $null
$receiptServerUrl = $null
$receiptDeviceId = $null
$receiptApiPrefix = '/api/v1/agent'
$statusShortcutName = 'App-IT-Manager ' + [char]0xC5F0 + [char]0xACB0 + ' ' + [char]0xC0C1 + [char]0xD0DC + '.lnk'
$statusShortcutPath = Join-Path ([Environment]::GetFolderPath('CommonPrograms')) $statusShortcutName

function Assert-NoReparsePath {
    param([string]$Path)
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            if (((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'A symbolic link or junction was found. Removal was stopped.'
            }
        }
        $parent = [IO.Directory]::GetParent($current)
        if ($null -eq $parent) { break }
        $current = $parent.FullName
    }
}

function Test-AgentNeverRegisteredAutomatic {
    param($Config)
    if (-not $Config.PSObject.Properties['registrationMode'] -or $Config.registrationMode -cne 'automatic' -or
        -not $Config.PSObject.Properties['apiPrefix'] -or -not (Test-UninstallIntegratedPrefix ([string]$Config.apiPrefix)) -or
        -not $Config.PSObject.Properties['ticketId'] -or [string]$Config.ticketId -notmatch '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$' -or
        [string]$Config.ticketId -eq '00000000-0000-0000-0000-000000000000' -or
        -not $Config.PSObject.Properties['registrationToken'] -or [string]$Config.registrationToken -notmatch '^[A-Za-z0-9_-]{43}$') { return $false }
    foreach ($name in @('deviceId', 'deviceToken', 'inventoryDeviceId', 'enrollmentToken')) {
        if ($Config.PSObject.Properties[$name] -and -not [string]::IsNullOrEmpty([string]$Config.$name)) { return $false }
    }
    if ($Config.PSObject.Properties['hadPriorIdentity'] -and ($Config.hadPriorIdentity -isnot [bool] -or $Config.hadPriorIdentity)) { return $false }
    return $true
}

function Test-UninstallIntegratedPrefix {
    param([string]$Prefix)
    return $Prefix -cin @('/api/v1/agent', '/manage/it/api/v1/agent')
}

function Get-UninstallServerUri {
    param($Config)
    $uri = [Uri]([string]$Config.serverUrl)
    if (-not $uri.IsAbsoluteUri -or $uri.AbsolutePath -ne '/' -or $uri.UserInfo -or $uri.Query -or $uri.Fragment) { throw 'The approval server origin is invalid.' }
    $mode = 'legacy'
    if ($Config.PSObject.Properties['deploymentMode']) {
        $mode = [string]$Config.deploymentMode
        if ($mode -cnotin @('production', 'development')) { throw 'The deployment policy is invalid.' }
    }
    $hostName = $uri.DnsSafeHost.Trim([char[]]'[]').TrimEnd('.').ToLowerInvariant()
    $local = $uri.IsLoopback -or $hostName -eq 'localhost' -or $hostName.EndsWith('.localhost') -or $hostName -eq 'localhost.localdomain'
    $address = $null
    if ([Net.IPAddress]::TryParse($hostName, [ref]$address)) {
        if ($address.IsIPv4MappedToIPv6) { $address = $address.MapToIPv4() }
        $local = $local -or [Net.IPAddress]::IsLoopback($address) -or $address.Equals([Net.IPAddress]::Any) -or $address.Equals([Net.IPAddress]::IPv6Any)
    }
    if ($mode -ceq 'production') {
        if ($uri.Scheme -cne 'https' -or $local) { throw 'Production removal approval requires a non-loopback HTTPS server.' }
        if (-not $Config.PSObject.Properties['expectedServerId']) { throw 'The production server identity is missing.' }
    } elseif ($uri.Scheme -ne 'https' -and -not ($uri.Scheme -eq 'http' -and $uri.IsLoopback)) { throw 'The approval server requires HTTPS.' }
    return $uri
}

function Assert-UninstallServerReadiness {
    param($Config, [Uri]$ServerUri, [string]$ApiPrefix)
    if (-not $Config.PSObject.Properties['expectedServerId']) { return }
    if ($Config.expectedServerId -isnot [string] -or $Config.expectedServerId -notmatch '^[A-Fa-f0-9]{64}$') { throw 'The expected approval server identity is invalid.' }
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        $ready = Invoke-RestMethod -Method Get -Uri ($ServerUri.AbsoluteUri.TrimEnd('/') + $ApiPrefix + '/ready') -TimeoutSec 10 -MaximumRedirection 0 -ErrorAction Stop
        $serverTime = [DateTimeOffset]::MinValue
        if ($null -eq $ready -or -not $ready.PSObject.Properties['product'] -or $ready.product -cne 'app-it-manager-agent' -or
            -not $ready.PSObject.Properties['protocol'] -or ($ready.protocol -isnot [int] -and $ready.protocol -isnot [long]) -or $ready.protocol -ne 1 -or
            -not $ready.PSObject.Properties['registrationReady'] -or $ready.registrationReady -isnot [bool] -or -not $ready.registrationReady -or
            -not $ready.PSObject.Properties['serverId'] -or $ready.serverId -isnot [string] -or $ready.serverId.ToLowerInvariant() -cne $Config.expectedServerId.ToLowerInvariant() -or
            -not $ready.PSObject.Properties['latestAgentVersion'] -or [string]$ready.latestAgentVersion -notmatch '^\d+\.\d+\.\d+$' -or
            -not $ready.PSObject.Properties['serverTime'] -or $ready.serverTime -isnot [string] -or
            -not [DateTimeOffset]::TryParse($ready.serverTime, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::None, [ref]$serverTime)) { throw 'Readiness mismatch.' }
    } catch { throw 'Cannot verify the configured approval server identity and agent protocol. No approval code was sent.' }
}

function Get-UninstallStatusLauncherArguments {
    param([string]$SetupPath)
    $command = '$p = Start-Process -FilePath ''' + $SetupPath.Replace("'", "''") +
        ''' -Verb RunAs -WindowStyle Normal -ArgumentList ''--status'' -Wait -PassThru; exit $p.ExitCode'
    return '-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand ' + [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
}

function Test-AgentOwnedStatusShortcut {
    param($Shortcut, [string]$SetupPath, [string]$PowerShellPath)
    try {
        return ([IO.Path]::GetFullPath([string]$Shortcut.TargetPath) -ieq [IO.Path]::GetFullPath($PowerShellPath) -and
            $Shortcut.Arguments -ceq (Get-UninstallStatusLauncherArguments $SetupPath) -and
            $Shortcut.Description -ceq 'App-IT-Manager connection status (SecurityPresenceAgent/1)')
    } catch { return $false }
}

function Remove-OwnedAgentStatusShortcut {
    if (-not (Test-Path -LiteralPath $statusShortcutPath -PathType Leaf)) { return }
    Assert-NoReparsePath $statusShortcutPath
    $shell = $null; $shortcut = $null; $owned = $false
    try {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($statusShortcutPath)
        $owned = Test-AgentOwnedStatusShortcut -Shortcut $shortcut -SetupPath (Join-Path $installPath 'SecurityPresenceSetup.exe') -PowerShellPath $powershellPath
    } catch { Write-Host 'An unverifiable connection-status shortcut was preserved.' }
    finally {
        if ($null -ne $shortcut) { $null = [Runtime.InteropServices.Marshal]::FinalReleaseComObject($shortcut) }
        if ($null -ne $shell) { $null = [Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) }
    }
    if ($owned) { Remove-Item -LiteralPath $statusShortcutPath -Force }
    else { Write-Host 'An unrelated connection-status shortcut was preserved.' }
}

function Restore-AgentRemovalStartup {
    param($Service, $Task)
    if ($null -ne $Service) {
        $mode = @{ Auto = 'Automatic'; Manual = 'Manual'; Disabled = 'Disabled' }[[string]$Service.StartMode]
        Set-Service -Name 'SecurityPresenceAgent' -StartupType $mode -ErrorAction Stop
        if ($Service.State -eq 'Running') { Start-Service -Name 'SecurityPresenceAgent' -ErrorAction Stop }
    }
    if ($null -ne $Task -and $Task.Settings.Enabled) {
        $null = Enable-ScheduledTask -TaskName 'SecurityPresenceAgent' -TaskPath '\' -ErrorAction Stop
        if ($Task.State -eq 'Running') { Start-ScheduledTask -TaskName 'SecurityPresenceAgent' -TaskPath '\' -ErrorAction Stop }
    }
}

function Send-AgentUninstallCompletion {
    param([string]$ServerUrl, [string]$DeviceId, [string]$Receipt, [string]$ApiPrefix = '/api/v1/agent')
    if (-not (Test-UninstallIntegratedPrefix $ApiPrefix) -or $Receipt -notmatch '^[A-Za-z0-9_-]{43}$' -or $DeviceId -notmatch '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$') { return $false }
    try {
        $body = @{ deviceId = $DeviceId; receipt = $Receipt } | ConvertTo-Json -Compress
        $response = Invoke-RestMethod -Method Post -Uri ($ServerUrl.TrimEnd('/') + $ApiPrefix + '/uninstall/complete') -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType 'application/json; charset=utf-8' -TimeoutSec 10 -MaximumRedirection 0 -ErrorAction Stop
        return ($null -ne $response -and $response.PSObject.Properties['ok'] -and $response.ok -is [bool] -and $response.ok)
    } catch { return $false }
}

try {
    Write-Host ('Removing the Windows presence service from ' + $installPath)
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        if (-not $PSCommandPath) { throw 'Run the saved uninstall.ps1 file as administrator.' }
        $arguments = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '"'
        # Direct script removal may require an interactive masked approval prompt.
        $elevated = Start-Process -FilePath $powershellPath -Verb RunAs -WindowStyle Normal -ArgumentList $arguments -PassThru -Wait
        if ($elevated.ExitCode -ne 0) {
            throw ('The elevated uninstaller failed (exit code ' + $elevated.ExitCode + '). Run this script from an Administrator PowerShell window to see the error.')
        }
        Write-Host 'Windows presence agent removed. The dashboard record will become offline after the timeout.'
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

    Assert-NoReparsePath $installPath
    if (-not (Test-Path -LiteralPath $installPath -PathType Container)) { throw 'The managed installation directory was not found.' }
    $acl = Get-Acl -LiteralPath $installPath
    $trusted = @('S-1-5-18', 'S-1-5-32-544')
    if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $trusted) { throw 'The installation directory has an unexpected owner.' }
    foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
        if ($rule.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and $rule.IdentityReference.Value -notin $trusted) {
            throw 'The installation directory has unexpected access permissions.'
        }
    }
    $markerPath = Join-Path $installPath '.security-presence-managed'
    Assert-NoReparsePath $markerPath
    if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf) -or (Get-Content -LiteralPath $markerPath -Raw).Trim() -ne 'SecurityPresenceAgent/1') {
        throw 'The directory is not a managed presence-agent installation.'
    }

    $registryView = [Microsoft.Win32.RegistryView]::Default
    if ([Environment]::Is64BitOperatingSystem) { $registryView = [Microsoft.Win32.RegistryView]::Registry64 }
    $machineRegistry = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine, $registryView)
    $uninstallKey = $machineRegistry.OpenSubKey($uninstallKeyPath, $true)
    try {
        if ($null -ne $uninstallKey) {
            if ($uninstallKey.GetValue('SecurityPresenceManaged', '') -ne 'SecurityPresenceAgent/1' -or
                $uninstallKey.GetValue('InstallLocation', '') -ne $installPath -or $uninstallKey.SubKeyCount -ne 0) {
                throw 'The Windows Apps registration does not belong to this installation. Nothing was removed.'
            }
            $hasOwnedUninstallKey = $true
        }
    } finally {
        if ($null -ne $uninstallKey) { $uninstallKey.Dispose() }
    }

    # The GUI relaunches from a protected helper directory before calling this
    # script, so its installed executable is no longer locked by the GUI.
    $knownFiles = @('SecurityPresenceService.exe', 'SecurityPresenceSetup.exe', 'agent.ps1', 'config.json.tmp', 'agent.log', 'agent.log.1', 'service.log', 'service.log.1', '.agent.lock', 'command-history.json', 'command-history.json.tmp', 'runtime-status.json', 'runtime-status.json.tmp', 'config.json', 'uninstall.ps1', '.security-presence-managed')
    foreach ($name in $knownFiles) {
        $target = [IO.Path]::GetFullPath((Join-Path $installPath $name))
        if ([IO.Path]::GetDirectoryName($target) -ne $installPath) { throw 'A file path escaped the installation directory.' }
        Assert-NoReparsePath $target
        if ((Test-Path -LiteralPath $target) -and (Get-Item -LiteralPath $target -Force).PSIsContainer) {
            throw 'An unexpected directory occupies an agent file path.'
        }
    }

    $service = Get-CimInstance -ClassName Win32_Service -Filter "Name='SecurityPresenceAgent'" -ErrorAction Stop
    if ($null -ne $service -and ($service.PathName.Trim() -ne ('"' + $servicePath + '"') -or $service.StartName -ne 'LocalSystem')) {
        throw 'The Windows service does not match this installation. Nothing was removed.'
    }
    $task = Get-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction SilentlyContinue
    if ($task) {
        $expectedArguments = '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + (Join-Path $installPath 'agent.ps1') + '"'
        if (@($task.Actions).Count -ne 1 -or $task.Actions[0].Execute -ne $powershellPath -or $task.Actions[0].Arguments -ne $expectedArguments) {
            throw 'The scheduled task does not match this installation. Nothing was removed.'
        }
    }
    $originalService = $service
    $originalTask = $task
    $configPath = Join-Path $installPath 'config.json'
    $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $apiPrefix = '/api'
    if ($config.PSObject.Properties['apiPrefix']) { $apiPrefix = [string]$config.apiPrefix }
    if ($apiPrefix -cnotin @('/api', '/api/v1/agent', '/manage/it/api/v1/agent')) { throw 'The agent API configuration is invalid.' }
    $neverRegisteredAutomatic = Test-AgentNeverRegisteredAutomatic $config
    if ((Test-UninstallIntegratedPrefix $apiPrefix) -and -not $neverRegisteredAutomatic) {
        $serverUri = Get-UninstallServerUri $config
        Assert-UninstallServerReadiness -Config $config -ServerUri $serverUri -ApiPrefix $apiPrefix
        if ([Console]::IsInputRedirected) { $approvalCode = [Console]::ReadLine() }
        else {
            $secureCode = Read-Host 'App IT Manager administrator uninstall approval code' -AsSecureString
            $codePointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureCode)
            try { $approvalCode = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($codePointer) }
            finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($codePointer); $secureCode.Dispose() }
        }
        try {
            if ($approvalCode -notmatch '^[A-Za-z0-9_-]{24,128}$') { throw 'Invalid approval.' }
            [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
            $approvalBody = @{ deviceId = [string]$config.deviceId; code = $approvalCode } | ConvertTo-Json -Compress
            $approval = Invoke-RestMethod -Method Post -Uri ($serverUri.AbsoluteUri.TrimEnd('/') + $apiPrefix + '/uninstall/authorize') -Body ([Text.Encoding]::UTF8.GetBytes($approvalBody)) -ContentType 'application/json; charset=utf-8' -TimeoutSec 10 -MaximumRedirection 0 -ErrorAction Stop
            if ($null -eq $approval -or -not $approval.PSObject.Properties['ok'] -or $approval.ok -isnot [bool] -or -not $approval.ok) { throw 'Approval refused.' }
            if (-not $approval.PSObject.Properties['receipt'] -or [string]$approval.receipt -notmatch '^[A-Za-z0-9_-]{43}$') { throw 'Approval receipt missing.' }
            # Keep the completion receipt only in this process's memory. It is
            # never written into config, arguments, logs or a helper file.
            $uninstallReceipt = [string]$approval.receipt
            $receiptServerUrl = $serverUri.AbsoluteUri
            $receiptDeviceId = [string]$config.deviceId
            $receiptApiPrefix = $apiPrefix
        } catch { throw 'Uninstall approval failed, expired, or unavailable. Request a new approval code from your App IT Manager administrator.' }
        finally { $approvalCode = $null; $approvalBody = $null }
    }
    if ($neverRegisteredAutomatic) { Write-Host 'No issued device identity is saved. This unregistered automatic installation may be removed by a Windows administrator.' }
    if ($null -ne $service) {
        # Pending recovery actions must not restart the service during removal.
        Set-Service -Name $taskName -StartupType Disabled
        $startupChanged = $true
        $controller = Get-Service -Name $taskName
        try {
            if ($controller.Status -ne 'Stopped') { Stop-Service -Name $taskName -ErrorAction Stop }
            $controller.WaitForStatus([ServiceProcess.ServiceControllerStatus]::Stopped, [TimeSpan]::FromSeconds(25))
        } finally { $controller.Dispose() }
        $deadline = [DateTime]::UtcNow.AddSeconds(10)
        do {
            try { $probe = [IO.File]::Open($servicePath, 'Open', 'ReadWrite', 'None'); $probe.Dispose(); break }
            catch { if ([DateTime]::UtcNow -ge $deadline) { throw 'The stopped service executable is still in use. Retry removal.' }; Start-Sleep -Milliseconds 200 }
        } while ($true)
    }
    $task = Get-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction SilentlyContinue
    if ($task) {
        $expectedArguments = '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + (Join-Path $installPath 'agent.ps1') + '"'
        if (@($task.Actions).Count -ne 1 -or $task.Actions[0].Execute -ne $powershellPath -or $task.Actions[0].Arguments -ne $expectedArguments) {
            throw 'The scheduled task does not match this installation. Nothing was removed.'
        }
        $null = Disable-ScheduledTask -TaskName $taskName -TaskPath '\'
        $startupChanged = $true
        Stop-ScheduledTask -TaskName $taskName -TaskPath '\'
        $stopDeadline = [DateTime]::UtcNow.AddSeconds(15)
        do {
            $stoppingTask = Get-ScheduledTask -TaskName $taskName -TaskPath '\'
            if ($stoppingTask.State -ne 'Running' -and $stoppingTask.State -ne 'Queued') { break }
            if ([DateTime]::UtcNow -ge $stopDeadline) { throw 'The agent did not stop in time. Try uninstalling again after it stops.' }
            Start-Sleep -Milliseconds 200
        } while ($true)
    }

    if ($neverRegisteredAutomatic) {
        # Registration may finish between the first UI/config snapshot and
        # service stop. Recheck only after every owned worker is stopped.
        $registrationLock = $null
        try {
            $lockPath = Join-Path $installPath '.agent.lock'
            Assert-NoReparsePath $lockPath
            if (Test-Path -LiteralPath $lockPath -PathType Leaf) { $registrationLock = [IO.File]::Open($lockPath, 'Open', 'ReadWrite', 'None') }
            $latestConfig = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if (-not (Test-AgentNeverRegisteredAutomatic $latestConfig)) {
                throw 'Registration completed while removal was being prepared. Request an App IT Manager administrator approval code and try again.'
            }
        } finally { if ($null -ne $registrationLock) { $registrationLock.Dispose() } }
    }
    $destructiveCleanupStarted = $true
    if ($null -ne $service) {
        $null = & $scPath delete $taskName
        if ($LASTEXITCODE -ne 0) { throw 'Windows could not remove the service registration.' }
    }
    if ($task) { Unregister-ScheduledTask -TaskName $taskName -TaskPath '\' -Confirm:$false }

    # Delete only known files after checking every exact absolute path. Never recurse.
    foreach ($name in $knownFiles) {
        if ($name -in @('config.json', 'uninstall.ps1', '.security-presence-managed')) { continue }
        $target = [IO.Path]::GetFullPath((Join-Path $installPath $name))
        if ([IO.Path]::GetDirectoryName($target) -ne $installPath) { throw 'A file path escaped the installation directory.' }
        Assert-NoReparsePath $target
        if (Test-Path -LiteralPath $target) {
            if ((Get-Item -LiteralPath $target -Force).PSIsContainer) { throw 'An unexpected directory occupies an agent file path.' }
            Remove-Item -LiteralPath $target -Force
        }
    }
    if ($hasOwnedUninstallKey) {
        # Delete only this exact application key, never a registry subtree.
        $machineRegistry.DeleteSubKey($uninstallKeyPath, $false)
    }
    Remove-OwnedAgentStatusShortcut
    # Keep approval configuration and the removal script available if a prior
    # file was locked or registry cleanup failed, so an administrator can retry.
    foreach ($name in @('config.json', 'uninstall.ps1', '.security-presence-managed')) {
        $target = Join-Path $installPath $name
        Assert-NoReparsePath $target
        if (Test-Path -LiteralPath $target -PathType Leaf) { Remove-Item -LiteralPath $target -Force }
    }
    Assert-NoReparsePath $installPath
    if (@(Get-ChildItem -LiteralPath $installPath -Force).Count -eq 0) {
        [IO.Directory]::Delete($installPath, $false)
    } else {
        Write-Host ('Unknown files were preserved in ' + $installPath)
    }
    if ($null -ne $uninstallReceipt) {
        $completionConfirmed = $false
        for ($attempt = 0; $attempt -lt 3; $attempt++) {
            if (Send-AgentUninstallCompletion -ServerUrl $receiptServerUrl -DeviceId $receiptDeviceId -Receipt $uninstallReceipt -ApiPrefix $receiptApiPrefix) { $completionConfirmed = $true; break }
            if ($attempt -lt 2) { Start-Sleep -Seconds 3 }
        }
        $uninstallReceipt = $null
        if (-not $completionConfirmed) {
            Write-Host 'The agent was removed locally, but the server could not confirm removal. Ask your administrator to review the dashboard.'
            exit 75
        }
    }
    Write-Host 'Windows presence agent removed. Registered installations report completion only after successful local cleanup.'
} catch {
    $removalFailure = $_.Exception.Message
    if ($neverRegisteredAutomatic -and $startupChanged -and -not $destructiveCleanupStarted) {
        try { Restore-AgentRemovalStartup -Service $originalService -Task $originalTask }
        catch { $removalFailure += ' The previous startup state could not be fully restored; ask your Windows administrator to repair the service.' }
    }
    Write-Error ('Removal failed: ' + $removalFailure)
    exit 1
} finally {
    if ($null -ne $machineRegistry) { $machineRegistry.Dispose() }
    if ($ownsOperationMutex -and $null -ne $operationMutex) { $operationMutex.ReleaseMutex() }
    if ($null -ne $operationMutex) { $operationMutex.Dispose() }
}
