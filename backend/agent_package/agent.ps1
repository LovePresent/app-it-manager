#requires -Version 5.1
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$agentVersion = '0.5.0'
$logPath = Join-Path $PSScriptRoot 'agent.log'
$historyPath = Join-Path $PSScriptRoot 'command-history.json'
$runtimeStatusPath = Join-Path $PSScriptRoot 'runtime-status.json'
$runtimeStatusState = $null
$config = $null
$env:PSModulePath = Join-Path ([Environment]::SystemDirectory) 'WindowsPowerShell\v1.0\Modules'
$instanceLock = $null

function Write-AgentLog {
    param([Parameter(Mandatory = $true)][string]$Event)
    # Log only fixed event names, never HTTP bodies, URLs, configuration or tokens.
    try {
        if ((Test-Path -LiteralPath $logPath) -and (Get-Item -LiteralPath $logPath).Length -ge 262144) {
            $previousLog = $logPath + '.1'
            if (Test-Path -LiteralPath $previousLog) { Remove-Item -LiteralPath $previousLog -Force }
            Move-Item -LiteralPath $logPath -Destination $previousLog
        }
        $safeEvent = $Event -replace '[^A-Za-z0-9 _.-]', ''
        Add-Content -LiteralPath $logPath -Value ((Get-Date).ToUniversalTime().ToString('o') + ' ' + $safeEvent) -Encoding UTF8
    } catch {
        # A logging failure must not stop presence reporting.
    }
}

function Open-AgentInstanceLock {
    param([string]$Path)
    $fullPath = [IO.Path]::GetFullPath($Path)
    if ([IO.Path]::GetFileName($fullPath) -cne '.agent.lock') { throw 'Unexpected agent lock filename.' }
    $current = $fullPath
    while ($current) {
        $item = $null
        try { $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop }
        catch [Management.Automation.ItemNotFoundException] { }
        if ($null -ne $item) {
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Agent lock path is a reparse point.' }
            if ($current -eq $fullPath -and $item.PSIsContainer) { throw 'Agent lock is not a regular file.' }
        }
        $parent = [IO.Directory]::GetParent($current)
        if ($null -eq $parent) { break }
        $current = $parent.FullName
    }
    try {
        return [IO.File]::Open($fullPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    } catch {
        $failure = $_.Exception.GetBaseException()
        $windowsError = $failure.HResult -band 0xFFFF
        if ($failure -is [IO.IOException] -and $windowsError -in @(32, 33)) {
            # Only an existing exclusive lock is a clean duplicate instance.
            return $null
        }
        throw
    }
}

function ConvertTo-AgentIPv4Netmask {
    param([string]$Value)
    if ($Value -match '^\d{1,2}$') {
        $prefix = [int]$Value
        if ($prefix -lt 1 -or $prefix -gt 32) { return $null }
        $octets = @()
        for ($index = 0; $index -lt 4; $index++) {
            $bits = [Math]::Min(8, [Math]::Max(0, $prefix - ($index * 8)))
            $octets += [string](256 - [Math]::Pow(2, 8 - $bits))
        }
        return ($octets -join '.')
    }
    $address = $null
    if (-not [Net.IPAddress]::TryParse($Value, [ref]$address) -or $address.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
        return $null
    }
    $binaryMask = ($address.GetAddressBytes() | ForEach-Object { [Convert]::ToString($_, 2).PadLeft(8, '0') }) -join ''
    if ($binaryMask -notmatch '^1+0*$') { return $null }
    return $address.ToString()
}

function Get-AgentNetworkAdapters {
    # Query only Windows networking inventory. A failure is handled by the
    # heartbeat caller by omitting networkAdapters, preserving saved inventory.
    $configurations = @(Get-CimInstance -ClassName Win32_NetworkAdapterConfiguration -Filter 'IPEnabled = True' -ErrorAction Stop)
    $hardwareAdapters = @(Get-CimInstance -ClassName Win32_NetworkAdapter -ErrorAction Stop)
    $hardwareByIndex = @{}
    foreach ($hardware in $hardwareAdapters) { $hardwareByIndex[[string]$hardware.Index] = $hardware }
    $adapters = New-Object 'Collections.Generic.List[object]'
    foreach ($configuration in @($configurations | Sort-Object -Property Index)) {
        if ($adapters.Count -ge 16) { break }
        $rawMac = [string]$configuration.MACAddress
        $macAddress = $null
        if ($rawMac -match '^(?:[A-Fa-f0-9]{2}[:-]){5}[A-Fa-f0-9]{2}$' -or $rawMac -match '^[A-Fa-f0-9]{12}$') {
            $macHex = ($rawMac -replace '[:-]', '').ToUpperInvariant()
            if ($macHex -ne '000000000000' -and ([Convert]::ToInt32($macHex.Substring(0, 2), 16) -band 1) -eq 0) {
                $macParts = for ($part = 0; $part -lt 12; $part += 2) { $macHex.Substring($part, 2) }
                $macAddress = $macParts -join ':'
            }
        }
        $ipv4 = New-Object 'Collections.Generic.List[object]'
        $ipv6 = New-Object 'Collections.Generic.List[string]'
        $seenV4 = @{}
        $addresses = @($configuration.IPAddress)
        $subnets = @($configuration.IPSubnet)
        for ($index = 0; $index -lt $addresses.Count; $index++) {
            $parsedAddress = $null
            if (-not [Net.IPAddress]::TryParse([string]$addresses[$index], [ref]$parsedAddress)) { continue }
            $normalizedAddress = $parsedAddress.ToString()
            if ($parsedAddress.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork -and $ipv4.Count -lt 8) {
                if ($index -ge $subnets.Count -or $seenV4.ContainsKey($normalizedAddress)) { continue }
                $netmask = ConvertTo-AgentIPv4Netmask ([string]$subnets[$index])
                if ($null -eq $netmask) { continue }
                $ipv4.Add(@{ address = $normalizedAddress; netmask = $netmask })
                $seenV4[$normalizedAddress] = $true
            } elseif ($parsedAddress.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetworkV6 -and $ipv6.Count -lt 8) {
                if (-not $ipv6.Contains($normalizedAddress)) { $ipv6.Add($normalizedAddress) }
            }
        }
        $hardware = $hardwareByIndex[[string]$configuration.Index]
        $name = [string]$configuration.Description
        $physical = $false
        if ($null -ne $hardware) {
            if ($hardware.PSObject.Properties['NetConnectionID'] -and $hardware.NetConnectionID) { $name = [string]$hardware.NetConnectionID }
            if ($hardware.PSObject.Properties['PhysicalAdapter']) { $physical = $hardware.PhysicalAdapter -eq $true }
        }
        $name = ($name -replace '[\x00-\x1F\x7F]', '').Trim()
        if ($name.Length -gt 128) { $name = $name.Substring(0, 128) }
        if (-not $name) { $name = 'Network adapter ' + [string]$configuration.Index }
        $id = ([string]$configuration.SettingID).Trim('{}')
        if (-not $id) { $id = [string]$configuration.Index }
        if ($id.Length -gt 128) { $id = $id.Substring(0, 128) }
        $adapters.Add(@{
            id = $id
            name = $name
            macAddress = $macAddress
            ipv4 = $ipv4.ToArray()
            ipv6 = $ipv6.ToArray()
            physical = [bool]$physical
        })
    }
    return ,$adapters.ToArray()
}

function Add-AgentNetworkInventory {
    param([hashtable]$Payload)
    try {
        $Payload.networkAdapters = Get-AgentNetworkAdapters
    } catch {
        Write-AgentLog 'Network information unavailable.'
    }
}

function ConvertTo-AgentCommandId {
    param($Value)
    if ($Value -isnot [string] -or $Value -notmatch '^[A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12}$') { return $null }
    $parsedId = [Guid]::Empty
    if (-not [Guid]::TryParseExact($Value, 'D', [ref]$parsedId) -or $parsedId -eq [Guid]::Empty) { return $null }
    return $parsedId.ToString('D')
}

function ConvertTo-AgentServerInstant {
    param($Value)
    if ($Value -isnot [string] -or $Value.Length -gt 40 -or
        $Value -notmatch '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,7})?(?:Z|[+-]\d{2}:\d{2})$') { return $null }
    $instant = [DateTimeOffset]::MinValue
    if (-not [DateTimeOffset]::TryParse($Value, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::None, [ref]$instant)) { return $null }
    return $instant.ToUniversalTime()
}

function Assert-AgentHistoryPath {
    param([string]$Path)
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            if (((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'History path is a reparse point.' }
        }
        $parent = [IO.Directory]::GetParent($current)
        if ($null -eq $parent) { break }
        $current = $parent.FullName
    }
    if ((Test-Path -LiteralPath $Path) -and -not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw 'History is not a regular file.' }
    $historyDirectory = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Path))
    $acl = Get-Acl -LiteralPath $historyDirectory
    $trusted = @('S-1-5-18', 'S-1-5-32-544')
    if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $trusted) { throw 'History directory owner is not trusted.' }
    foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
        if ($rule.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and $rule.IdentityReference.Value -notin $trusted) { throw 'History directory is not private.' }
    }
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        $fileAcl = Get-Acl -LiteralPath $Path
        if ($fileAcl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $trusted) { throw 'History file owner is not trusted.' }
        foreach ($rule in $fileAcl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
            if ($rule.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and $rule.IdentityReference.Value -notin $trusted) { throw 'History file is not private.' }
        }
    }
}

function Set-AgentPrivateHistoryAcl {
    param([string]$Path)
    $acl = New-Object Security.AccessControl.FileSecurity
    $acl.SetAccessRuleProtection($true, $false)
    $admins = New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')
    $system = New-Object Security.Principal.SecurityIdentifier('S-1-5-18')
    $acl.SetOwner($admins)
    foreach ($sid in @($admins, $system)) {
        $rule = New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Read-AgentCommandHistory {
    param([string]$Path)
    Assert-AgentHistoryPath $Path
    if (-not (Test-Path -LiteralPath $Path)) { return ,@() }
    if ((Get-Item -LiteralPath $Path -Force).Length -gt 32768) { throw 'History exceeds the size limit.' }
    $history = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
    if ($null -eq $history -or -not $history.PSObject.Properties['version'] -or $history.version -ne 1 -or
        -not $history.PSObject.Properties['executedIds'] -or $history.executedIds -isnot [array] -or $history.executedIds.Count -gt 100) {
        throw 'History format is invalid.'
    }
    $ids = New-Object 'Collections.Generic.List[string]'
    foreach ($value in $history.executedIds) {
        $id = ConvertTo-AgentCommandId $value
        if ($null -eq $id -or $ids.Contains($id)) { throw 'History contains an invalid or duplicate ID.' }
        $ids.Add($id)
    }
    return ,$ids.ToArray()
}

function Save-AgentCommandHistory {
    param([string]$Path, [string[]]$Ids)
    if ($Ids.Count -gt 100) { throw 'History exceeds the entry limit.' }
    $seenIds = @{}
    foreach ($value in $Ids) {
        $id = ConvertTo-AgentCommandId $value
        if ($null -eq $id -or $seenIds.ContainsKey($id)) { throw 'History IDs are invalid.' }
        $seenIds[$id] = $true
    }
    $temporaryPath = $Path + '.tmp'
    Assert-AgentHistoryPath $Path
    Assert-AgentHistoryPath $temporaryPath
    if (Test-Path -LiteralPath $temporaryPath) { Remove-Item -LiteralPath $temporaryPath -Force }
    $emptyFile = [IO.File]::Open($temporaryPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    $emptyFile.Dispose()
    try {
        Set-AgentPrivateHistoryAcl $temporaryPath
        $json = @{ version = 1; executedIds = @($Ids) } | ConvertTo-Json -Compress -Depth 3
        $bytes = [Text.Encoding]::UTF8.GetBytes($json)
        $stream = [IO.File]::Open($temporaryPath, [IO.FileMode]::Truncate, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try {
            $stream.Write($bytes, 0, $bytes.Length)
            $stream.Flush($true)
        } finally { $stream.Dispose() }
        if (Test-Path -LiteralPath $Path) {
            # Both files already have verified private ACLs. Ignore optional
            # metadata-merge errors while keeping the data replacement atomic.
            # PS 5.1 otherwise binds $null to an empty backup pathname.
            [IO.File]::Replace($temporaryPath, $Path, [NullString]::Value, $true)
        } else {
            [IO.File]::Move($temporaryPath, $Path)
        }
    } catch {
        try {
            Assert-AgentHistoryPath $temporaryPath
            if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) { Remove-Item -LiteralPath $temporaryPath -Force }
        } catch { }
        throw
    }
}

function Send-AgentCommandAck {
    param(
        [string]$ServerUrl, [hashtable]$Headers, [string]$DeviceId,
        [string]$CommandId, [string]$Status, [string]$Detail, [string]$ApiPrefix = '/api'
    )
    if ($null -eq (ConvertTo-AgentCommandId $CommandId) -or $ApiPrefix -cnotin @('/api', '/api/v1/agent', '/manage/it/api/v1/agent') -or $Status -cnotin @('accepted', 'failed', 'succeeded') -or
        $Detail -cnotin @('accepted', 'expired', 'duplicate', 'execution_failed', 'invalid_command', 'packet_sent')) { return $false }
    try {
        $ackBody = @{ deviceId = $DeviceId; status = $Status; detail = $Detail } | ConvertTo-Json -Compress
        $ackResponse = Invoke-RestMethod -Method Post -Uri ($ServerUrl.TrimEnd('/') + $ApiPrefix + '/commands/' + $CommandId + '/ack') -Headers $Headers -Body ([Text.Encoding]::UTF8.GetBytes($ackBody)) -ContentType 'application/json; charset=utf-8' -TimeoutSec 10 -MaximumRedirection 0 -ErrorAction Stop
        return ($null -ne $ackResponse -and $null -ne $ackResponse.PSObject.Properties['ok'] -and $ackResponse.ok -is [bool] -and $ackResponse.ok -eq $true)
    } catch {
        Write-AgentLog 'Command acknowledgement failed.'
        return $false
    }
}

function Get-AgentApiPrefix {
    param($Config)
    $prefix = '/api'
    if ($Config.PSObject.Properties['apiPrefix']) { $prefix = [string]$Config.apiPrefix }
    if ($prefix -cnotin @('/api', '/api/v1/agent', '/manage/it/api/v1/agent')) { throw 'Unsupported API prefix.' }
    return $prefix
}

function Get-AgentServerUri {
    param($Config)
    $uri = [Uri]([string]$Config.serverUrl)
    if (-not $uri.IsAbsoluteUri -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -ne '/') { throw 'Invalid server origin.' }
    $mode = 'legacy'
    if ($Config.PSObject.Properties['deploymentMode']) {
        $mode = [string]$Config.deploymentMode
        if ($mode -cnotin @('production', 'development')) { throw 'Invalid deployment policy.' }
    }
    $hostName = $uri.DnsSafeHost.Trim('[', ']').TrimEnd('.').ToLowerInvariant()
    $isLocal = $uri.IsLoopback -or $hostName -eq 'localhost' -or $hostName.EndsWith('.localhost') -or $hostName -eq 'localhost.localdomain'
    $address = $null
    if ([Net.IPAddress]::TryParse($hostName, [ref]$address)) {
        if ($address.IsIPv4MappedToIPv6) { $address = $address.MapToIPv4() }
        $isLocal = $isLocal -or [Net.IPAddress]::IsLoopback($address) -or $address.Equals([Net.IPAddress]::Any) -or $address.Equals([Net.IPAddress]::IPv6Any)
    }
    if ($mode -ceq 'production') {
        if ($uri.Scheme -cne 'https' -or $isLocal) { throw 'Production requires a non-loopback HTTPS server origin.' }
    } elseif ($uri.Scheme -ne 'https' -and -not ($uri.Scheme -eq 'http' -and $uri.IsLoopback)) {
        throw 'HTTP is permitted only for loopback development.'
    }
    return $uri
}

function New-AgentRuntimeStatus {
    param($Config, [string]$Code, $Previous = $null, $HttpStatus = $null, [switch]$Attempted,
          [string]$Phase = '', [DateTimeOffset]$Now = [DateTimeOffset]::UtcNow)
    $phases = @{
        starting = 'configuration'; configuration_invalid = 'configuration'; registration_pending = 'registration'
        registration_network_error = 'registration'; registration_blocked = 'registration'; registration_save_failed = 'registration'
        heartbeat_network_error = 'heartbeat'; authentication_failed = 'heartbeat'; heartbeat_connected = 'heartbeat'
    }
    if ($Code -cnotin @($phases.Keys)) { throw 'Unsupported runtime status code.' }
    if ($Phase -and $Phase -cnotin @('configuration', 'registration', 'heartbeat')) { throw 'Unsupported runtime status phase.' }
    $confirmedHeartbeat = $Code -ceq 'heartbeat_connected'
    $contextServer = $null; $contextPrefix = $null; $contextId = $null; $contextServerId = $null
    if ($null -ne $Config) {
        try {
            $contextServer = (Get-AgentServerUri $Config).AbsoluteUri.TrimEnd('/')
            $contextPrefix = Get-AgentApiPrefix $Config
            $contextServerId = Get-AgentExpectedServerId $Config
            if ($Config.PSObject.Properties['deviceId'] -and [string]$Config.deviceId -match '^[A-Za-z0-9_-]{1,100}$') { $contextId = [string]$Config.deviceId }
        } catch { $contextServer = $null; $contextPrefix = $null; $contextId = $null; $contextServerId = $null }
    }
    $lastSuccess = $null; $lastAttempt = $null
    $safeHttp = $null
    $parsedHttp = 0
    if ($null -ne $HttpStatus -and [int]::TryParse([string]$HttpStatus, [ref]$parsedHttp) -and $parsedHttp -ge 100 -and $parsedHttp -le 599) { $safeHttp = $parsedHttp }
    if ($null -ne $Previous -and $Previous.serverUrl -ceq $contextServer -and $Previous.apiPrefix -ceq $contextPrefix -and $Previous.expectedServerId -ceq $contextServerId) {
        if ($Previous.deviceId -ceq $contextId) {
            $parsedSuccess = ConvertTo-AgentServerInstant $Previous.lastSuccessUtc
            if ($null -ne $parsedSuccess) { $lastSuccess = $parsedSuccess.ToString('o') }
            $parsedAttempt = ConvertTo-AgentServerInstant $Previous.lastAttemptUtc
            if ($null -ne $parsedAttempt) { $lastAttempt = $parsedAttempt.ToString('o') }
            # During a bounded routine request retain the last known connection
            # state, but never advance its success time until the reply validates.
            if ($Code -ceq 'starting' -and $Previous.code -ceq 'heartbeat_connected' -and $null -ne $parsedSuccess -and
                $Now -ge $parsedSuccess -and ($Now - $parsedSuccess).TotalSeconds -le 45) {
                $Code = 'heartbeat_connected'
                $Phase = ''
            }
        }
        # Retrying or receiving an enrollment token is not a successful
        # authenticated heartbeat. Keep the last failure visible until one is.
        if ($Code -in @('starting', 'registration_pending') -and $Previous.code -in @('configuration_invalid', 'registration_network_error', 'registration_blocked', 'registration_save_failed', 'heartbeat_network_error', 'authentication_failed')) {
            $Code = [string]$Previous.code
            if ($null -eq $safeHttp -and [int]::TryParse([string]$Previous.httpStatus, [ref]$parsedHttp) -and $parsedHttp -ge 100 -and $parsedHttp -le 599) { $safeHttp = $parsedHttp }
            $Phase = ''
        }
    }
    $timestamp = $Now.ToUniversalTime().ToString('o')
    if ($Attempted) { $lastAttempt = $timestamp }
    if ($confirmedHeartbeat) { $lastSuccess = $timestamp; $safeHttp = $null }
    $selectedPhase = $phases[$Code]
    if ($Code -ceq 'starting' -and $Phase) { $selectedPhase = $Phase }
    return [pscustomobject]@{
        version = 1; code = $Code; phase = $selectedPhase
        needsAdmin = [bool]($Code -in @('configuration_invalid', 'registration_blocked', 'registration_save_failed', 'authentication_failed'))
        httpStatus = $safeHttp; lastSuccessUtc = $lastSuccess; lastAttemptUtc = $lastAttempt; updatedUtc = $timestamp
        deviceId = $contextId; serverUrl = $contextServer; apiPrefix = $contextPrefix; expectedServerId = $contextServerId
    }
}

function Publish-AgentRuntimeStatus {
    param($Config, [string]$Code, $HttpStatus = $null, [switch]$Attempted, [string]$Phase = '', [string]$Path = $script:runtimeStatusPath)
    try {
        if ([IO.Path]::GetFileName($Path) -cne 'runtime-status.json') { throw 'Invalid runtime status filename.' }
        $next = New-AgentRuntimeStatus -Config $Config -Code $Code -Previous $script:runtimeStatusState -HttpStatus $HttpStatus -Attempted:$Attempted -Phase $Phase
        $script:runtimeStatusState = $next
        $null = Save-AgentConfiguration -Path $Path -Config $next
        return $true
    } catch {
        Write-AgentLog 'Runtime status could not be saved. Check private installation permissions.'
        return $false
    }
}

function Test-AgentHeartbeatResponse {
    param($Response)
    return ($null -ne $Response -and $Response.PSObject.Properties['ok'] -and $Response.ok -is [bool] -and $Response.ok -and
        $Response.PSObject.Properties['serverTime'] -and $null -ne (ConvertTo-AgentServerInstant $Response.serverTime))
}

function Get-AgentHeartbeatFailurePolicy {
    param($Config, [int]$Status, [bool]$EnrollmentAlreadyAttempted)
    if (Test-AgentEnrollmentFallback -Config $Config -Status $Status -AlreadyAttempted $EnrollmentAlreadyAttempted) {
        return @{ code = 'registration_pending'; blocked = $false; enroll = $true }
    }
    if ($Status -in @(401, 403)) { return @{ code = 'authentication_failed'; blocked = $true; enroll = $false } }
    return @{ code = 'heartbeat_network_error'; blocked = $false; enroll = $false }
}

function Get-AgentExpectedServerId {
    param($Config)
    if ($Config.PSObject.Properties['expectedServerId']) {
        if ($Config.expectedServerId -isnot [string] -or $Config.expectedServerId -notmatch '^[A-Fa-f0-9]{64}$') { throw 'Invalid expected server identity.' }
        return $Config.expectedServerId.ToLowerInvariant()
    }
    if ($Config.PSObject.Properties['deploymentMode'] -and $Config.deploymentMode -ceq 'production') { throw 'Production server identity is required.' }
    return $null
}

function Request-AgentServerReadiness {
    param($Config)
    $expected = Get-AgentExpectedServerId $Config
    if ($null -eq $expected) { return @{ status = 'ready'; httpStatus = $null } }
    try {
        $uri = Get-AgentServerUri $Config
        $response = Invoke-RestMethod -Method Get -Uri ($uri.AbsoluteUri.TrimEnd('/') + (Get-AgentApiPrefix $Config) + '/ready') -TimeoutSec 10 -MaximumRedirection 0 -ErrorAction Stop
        if ($null -eq $response -or -not $response.PSObject.Properties['product'] -or $response.product -cne 'app-it-manager-agent' -or
            -not $response.PSObject.Properties['protocol'] -or ($response.protocol -isnot [int] -and $response.protocol -isnot [long]) -or $response.protocol -ne 1 -or
            -not $response.PSObject.Properties['registrationReady'] -or $response.registrationReady -isnot [bool] -or
            -not $response.PSObject.Properties['serverId'] -or $response.serverId -isnot [string] -or $response.serverId.ToLowerInvariant() -cne $expected -or
            -not $response.PSObject.Properties['latestAgentVersion'] -or $response.latestAgentVersion -isnot [string] -or $response.latestAgentVersion -notmatch '^\d+\.\d+\.\d+$' -or
            -not $response.PSObject.Properties['serverTime'] -or $null -eq (ConvertTo-AgentServerInstant $response.serverTime)) { return @{ status = 'blocked'; httpStatus = $null } }
        if (-not $response.registrationReady) { return @{ status = 'retry'; httpStatus = $null } }
        return @{ status = 'ready'; httpStatus = $null }
    } catch {
        $status = Get-AgentHttpFailureStatus $_
        if ($status -in @(400, 401, 403, 409, 410, 422)) { return @{ status = 'blocked'; httpStatus = $status } }
        return @{ status = 'retry'; httpStatus = $status }
    }
}

function Get-AgentHttpFailureStatus {
    param($Failure)
    try { return [int]$Failure.Exception.Response.StatusCode } catch { return 0 }
}

function Test-AgentEnrollmentFallback {
    param($Config, [int]$Status, [bool]$AlreadyAttempted)
    return ($Status -eq 401 -and -not $AlreadyAttempted -and $Config.PSObject.Properties['enrollmentToken'] -and
        [string]$Config.enrollmentToken -match '^[A-Za-z0-9_-]{24,256}$')
}

function Request-AgentEnrollment {
    param($Config, [string]$ApiPrefix)
    try {
        $body = @{ deviceId = [string]$Config.deviceId; enrollmentToken = [string]$Config.enrollmentToken } | ConvertTo-Json -Compress
        $response = Invoke-RestMethod -Method Post -Uri (([string]$Config.serverUrl).TrimEnd('/') + $ApiPrefix + '/enroll') -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType 'application/json; charset=utf-8' -TimeoutSec 10 -MaximumRedirection 0 -ErrorAction Stop
        if ($null -eq $response -or -not $response.PSObject.Properties['deviceToken'] -or
            [string]$response.deviceToken -notmatch '^[A-Za-z0-9_-]{43}$' -or
            ($response.PSObject.Properties['deviceId'] -and [string]$response.deviceId -cne [string]$Config.deviceId)) { return @{ status = 'blocked'; httpStatus = $null } }
        return @{ status = 'received'; token = [string]$response.deviceToken; httpStatus = $null }
    } catch {
        $status = Get-AgentHttpFailureStatus $_
        if ($status -in @(400, 401, 403, 404, 409, 410, 422)) { return @{ status = 'blocked'; httpStatus = $status } }
        return @{ status = 'retry'; httpStatus = $status }
    }
}

function Save-AgentEnrollmentConfiguration {
    param([string]$Path, $Config, [string]$DeviceToken, [string]$ApiPrefix)
    if ($DeviceToken -notmatch '^[A-Za-z0-9_-]{43}$') { throw 'Invalid enrollment credential.' }
    $saved = [pscustomobject]@{
        serverUrl = [string]$Config.serverUrl; deviceId = [string]$Config.deviceId
        deviceToken = $DeviceToken; heartbeatIntervalSeconds = [int]$Config.heartbeatIntervalSeconds; apiPrefix = $ApiPrefix
    }
    $saved | Add-Member -NotePropertyName hadPriorIdentity -NotePropertyValue $true
    foreach ($name in @('inventoryDeviceId', 'serialNumber', 'registrationCreated', 'deploymentMode', 'expectedServerId')) {
        if ($Config.PSObject.Properties[$name]) { $saved | Add-Member -NotePropertyName $name -NotePropertyValue $Config.$name }
    }
    return Save-AgentConfiguration -Path $Path -Config $saved
}

function Save-AgentConfiguration {
    param([string]$Path, $Config)
    $temporaryPath = $Path + '.tmp'
    Assert-AgentHistoryPath $Path
    Assert-AgentHistoryPath $temporaryPath
    if (Test-Path -LiteralPath $temporaryPath) { Remove-Item -LiteralPath $temporaryPath -Force }
    $empty = [IO.File]::Open($temporaryPath, 'CreateNew', 'Write', 'None'); $empty.Dispose()
    try {
        Set-AgentPrivateHistoryAcl $temporaryPath
        $bytes = [Text.Encoding]::UTF8.GetBytes(($Config | ConvertTo-Json -Compress -Depth 8))
        $stream = [IO.File]::Open($temporaryPath, 'Truncate', 'Write', 'None')
        try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
        if (Test-Path -LiteralPath $Path) { [IO.File]::Replace($temporaryPath, $Path, [NullString]::Value, $true) }
        else { [IO.File]::Move($temporaryPath, $Path) }
    } catch {
        try { Assert-AgentHistoryPath $temporaryPath; if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) { Remove-Item -LiteralPath $temporaryPath -Force } } catch { }
        throw
    }
    return $Config
}

function Test-AgentAutomaticRegistration {
    param($Config)
    foreach ($name in @('deviceId', 'deviceToken', 'enrollmentToken')) {
        if ($Config.PSObject.Properties[$name] -and -not [string]::IsNullOrEmpty([string]$Config.$name)) { return $false }
    }
    return ($Config.PSObject.Properties['registrationMode'] -and $Config.registrationMode -ceq 'automatic' -and
        (Get-AgentApiPrefix $Config) -cin @('/api/v1/agent', '/manage/it/api/v1/agent') -and $Config.PSObject.Properties['ticketId'] -and
        $null -ne (ConvertTo-AgentCommandId $Config.ticketId) -and $Config.PSObject.Properties['registrationToken'] -and
        [string]$Config.registrationToken -match '^[A-Za-z0-9_-]{43}$')
}

function ConvertTo-AgentRegistrationSerial {
    param($Value)
    if ($Value -isnot [string]) { return $null }
    $serial = $Value.Trim().ToUpperInvariant()
    if ($serial.Length -gt 128 -or $serial -match '[\x00-\x1F\x7F]' -or $serial -notmatch '^[A-Z0-9 ._:/-]+$') { return $null }
    $compact = $serial -replace '[^A-Z0-9]', ''
    if ($compact.Length -lt 3 -or $compact -match '^(?:0+|F+|X+)$' -or
        $compact -in @('TOBEFILLEDBYOEM', 'TOBEFILLED', 'DEFAULTSTRING', 'DEFAULT', 'OEM', 'SYSTEMSERIALNUMBER', 'SERIALNUMBER', 'UNKNOWN', 'NONE', 'NOTSPECIFIED', 'NOTAPPLICABLE', 'NA', 'INVALID', '123456789', '0123456789', '1234567890')) { return $null }
    return $serial
}

function Get-AgentRegistrationHardware {
    $hardwareUuid = $null; $serialNumber = $null; $identityFailures = 0
    try {
        $product = Get-CimInstance -ClassName Win32_ComputerSystemProduct -ErrorAction Stop
        $hardwareUuid = ConvertTo-AgentCommandId (([string]$product.UUID).Trim().Trim('{}'))
        if ($hardwareUuid -in @('ffffffff-ffff-ffff-ffff-ffffffffffff', '03000200-0400-0500-0006-000700080009')) { $hardwareUuid = $null }
    } catch { $identityFailures++ }
    try {
        $bios = Get-CimInstance -ClassName Win32_BIOS -ErrorAction Stop
        $serialNumber = ConvertTo-AgentRegistrationSerial ([string]$bios.SerialNumber)
    } catch { $identityFailures++ }
    if ($identityFailures -gt 0 -and $null -eq $hardwareUuid -and $null -eq $serialNumber) { throw 'Hardware identity temporarily unavailable.' }
    $deviceType = 'desktop'
    try { if ((Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop).PCSystemType -eq 2) { $deviceType = 'laptop' } } catch { }
    $windows = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
    $os = ([string]$windows.Caption + ' ' + [string]$windows.Version).Trim()
    if ($os.Length -gt 255) { $os = $os.Substring(0, 255) }
    return [pscustomobject]@{ hardwareUuid = $hardwareUuid; serialNumber = $serialNumber; hostname = [Environment]::MachineName; deviceType = $deviceType; os = $os }
}

function Initialize-AgentAutomaticConfiguration {
    param([string]$Path, $Config)
    if (-not (Test-AgentAutomaticRegistration $Config)) { throw 'Invalid automatic registration configuration.' }
    if ($Config.PSObject.Properties['clientNonce']) {
        if ([string]$Config.clientNonce -notmatch '^[A-Za-z0-9_-]{43}$') { throw 'Invalid persisted registration nonce.' }
        if ($Config.PSObject.Properties['registrationHardware']) { return $Config }
    }
    # Work on a copy. A failed disk write must not make an unpersisted nonce
    # appear initialized to the next loop iteration.
    $prepared = $Config | ConvertTo-Json -Depth 8 | ConvertFrom-Json
    if (-not $prepared.PSObject.Properties['clientNonce']) {
        $random = [Security.Cryptography.RandomNumberGenerator]::Create()
        $bytes = New-Object byte[] 32
        try { $random.GetBytes($bytes) } finally { $random.Dispose() }
        $nonce = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
        $prepared | Add-Member -NotePropertyName clientNonce -NotePropertyValue $nonce
    }
    $prepared | Add-Member -NotePropertyName registrationHardware -NotePropertyValue (Get-AgentRegistrationHardware) -Force
    return Save-AgentConfiguration -Path $Path -Config $prepared
}

function Request-AgentAutomaticEnrollment {
    param($Config)
    if (-not (Test-AgentAutomaticRegistration $Config) -or -not $Config.PSObject.Properties['clientNonce'] -or
        [string]$Config.clientNonce -notmatch '^[A-Za-z0-9_-]{43}$' -or -not $Config.PSObject.Properties['registrationHardware']) { throw 'Automatic registration has not been persisted.' }
    try {
        $hardware = $Config.registrationHardware
        $body = @{
            ticketId = [string]$Config.ticketId; registrationToken = [string]$Config.registrationToken; clientNonce = [string]$Config.clientNonce
            hardwareUuid = $hardware.hardwareUuid; serialNumber = $hardware.serialNumber; hostname = $hardware.hostname; deviceType = $hardware.deviceType; os = $hardware.os
        } | ConvertTo-Json -Compress
        $response = Invoke-RestMethod -Method Post -Uri (([string]$Config.serverUrl).TrimEnd('/') + (Get-AgentApiPrefix $Config) + '/auto-enroll') -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType 'application/json; charset=utf-8' -TimeoutSec 10 -MaximumRedirection 0 -ErrorAction Stop
        if ($null -eq $response -or -not $response.PSObject.Properties['ok'] -or $response.ok -isnot [bool] -or -not $response.ok -or
            -not $response.PSObject.Properties['deviceId'] -or $null -eq (ConvertTo-AgentCommandId $response.deviceId) -or
            -not $response.PSObject.Properties['deviceToken'] -or [string]$response.deviceToken -notmatch '^[A-Za-z0-9_-]{43}$' -or
            -not $response.PSObject.Properties['inventoryDeviceId'] -or ($response.inventoryDeviceId -isnot [int] -and $response.inventoryDeviceId -isnot [long]) -or $response.inventoryDeviceId -le 0 -or
            -not $response.PSObject.Properties['created'] -or $response.created -isnot [bool]) { return @{ status = 'blocked'; httpStatus = $null } }
        return @{ status = 'received'; identity = $response; httpStatus = $null }
    } catch {
        $status = Get-AgentHttpFailureStatus $_
        if ($status -in @(400, 401, 403, 404, 409, 410, 422)) { return @{ status = 'blocked'; httpStatus = $status } }
        return @{ status = 'retry'; httpStatus = $status }
    }
}

function Save-AgentAutomaticEnrollmentConfiguration {
    param([string]$Path, $Config, $Identity)
    $saved = [pscustomobject]@{
        serverUrl = [string]$Config.serverUrl; apiPrefix = (Get-AgentApiPrefix $Config); heartbeatIntervalSeconds = [int]$Config.heartbeatIntervalSeconds
        registrationMode = 'automatic'; deviceId = [string]$Identity.deviceId; deviceToken = [string]$Identity.deviceToken
        inventoryDeviceId = [long]$Identity.inventoryDeviceId; registrationCreated = [bool]$Identity.created; hadPriorIdentity = $true
    }
    if ($Config.PSObject.Properties['deploymentMode']) { $saved | Add-Member -NotePropertyName deploymentMode -NotePropertyValue ([string]$Config.deploymentMode) }
    if ($Config.PSObject.Properties['expectedServerId']) { $saved | Add-Member -NotePropertyName expectedServerId -NotePropertyValue ([string]$Config.expectedServerId) }
    if ($Identity.PSObject.Properties['serialNumber'] -and $Identity.serialNumber -is [string]) {
        $serial = ([string]$Identity.serialNumber -replace '[\x00-\x1F\x7F]', '').Trim()
        if ($serial.Length -le 128) { $saved | Add-Member -NotePropertyName serialNumber -NotePropertyValue $serial }
    }
    return Save-AgentConfiguration -Path $Path -Config $saved
}

function Get-AgentValidatedWakePayload {
    param($Payload)
    foreach ($name in @('macAddress', 'sourceAddress', 'broadcastAddress', 'port')) {
        if ($null -eq $Payload -or -not $Payload.PSObject.Properties[$name]) { throw 'Incomplete wake payload.' }
    }
    if (($Payload.port -isnot [int] -and $Payload.port -isnot [long]) -or $Payload.port -ne 9 -or
        $Payload.macAddress -isnot [string] -or $Payload.macAddress -notmatch '^(?:[A-Fa-f0-9]{2}:){5}[A-Fa-f0-9]{2}$') { throw 'Invalid wake payload.' }
    $mac = $Payload.macAddress.Replace(':', '').ToUpperInvariant()
    if ($mac -eq '000000000000' -or ([Convert]::ToInt32($mac.Substring(0, 2), 16) -band 1) -ne 0) { throw 'Invalid target MAC.' }
    foreach ($address in @($Payload.sourceAddress, $Payload.broadcastAddress)) {
        $parsed = $null
        if ($address -isnot [string] -or $address -notmatch '^(?:\d{1,3}\.){3}\d{1,3}$' -or
            -not [Net.IPAddress]::TryParse($address, [ref]$parsed) -or $parsed.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or
            $parsed.ToString() -cne $address) { throw 'Wake requires literal IPv4 addresses.' }
    }
    foreach ($adapter in (Get-AgentNetworkAdapters)) {
        foreach ($local in $adapter.ipv4) {
            if ($local.address -cne $Payload.sourceAddress) { continue }
            $ipBytes = ([Net.IPAddress]::Parse($local.address)).GetAddressBytes()
            $mask = ConvertTo-AgentIPv4Netmask $local.netmask
            if ($null -eq $mask -or $mask -in @('255.255.255.254', '255.255.255.255') -or $ipBytes[0] -eq 0 -or $ipBytes[0] -eq 127 -or $ipBytes[0] -ge 224) { continue }
            $maskBytes = ([Net.IPAddress]::Parse($mask)).GetAddressBytes()
            $broadcast = (0..3 | ForEach-Object { [string]($ipBytes[$_] -bor (255 - $maskBytes[$_])) }) -join '.'
            if ($broadcast -ceq $Payload.broadcastAddress) {
                return @{ macAddress = $Payload.macAddress.ToUpperInvariant(); sourceAddress = $local.address; broadcastAddress = $broadcast; port = 9 }
            }
        }
    }
    throw 'Wake broadcast does not belong to a current local interface.'
}

function New-AgentMagicPacket {
    param([string]$MacAddress)
    $hex = $MacAddress.Replace(':', '')
    if ($hex -notmatch '^[A-Fa-f0-9]{12}$') { throw 'Invalid MAC.' }
    $packet = New-Object byte[] 102
    for ($i = 0; $i -lt 6; $i++) { $packet[$i] = 255 }
    for ($repeat = 0; $repeat -lt 16; $repeat++) {
        for ($i = 0; $i -lt 6; $i++) { $packet[6 + $repeat * 6 + $i] = [Convert]::ToByte($hex.Substring($i * 2, 2), 16) }
    }
    return ,$packet
}

function Invoke-AgentWakeAction {
    param([hashtable]$Payload)
    $packet = New-AgentMagicPacket $Payload.macAddress
    $socket = New-Object Net.Sockets.UdpClient([Net.Sockets.AddressFamily]::InterNetwork)
    try {
        $socket.Client.SendTimeout = 3000
        $socket.EnableBroadcast = $true
        $socket.Client.Bind((New-Object Net.IPEndPoint([Net.IPAddress]::Parse($Payload.sourceAddress), 0)))
        $destination = New-Object Net.IPEndPoint([Net.IPAddress]::Parse($Payload.broadcastAddress), 9)
        return ($socket.Send($packet, $packet.Length, $destination) -eq 102)
    } finally { $socket.Dispose() }
}

function Invoke-AgentPowerAction {
    param([string]$Type)
    # Network data never supplies an executable, argument, shell command or delay.
    $shutdownPath = Join-Path ([Environment]::GetFolderPath('Windows')) 'System32\shutdown.exe'
    if ($Type -ceq 'restart') {
        $arguments = '/r /t 0'
    } elseif ($Type -ceq 'shutdown') {
        $arguments = '/s /t 0'
    } else {
        throw 'Unsupported power action.'
    }
    $process = Start-Process -FilePath $shutdownPath -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru -ErrorAction Stop
    return ($process.ExitCode -eq 0)
}

function Invoke-AgentServerCommands {
    param(
        $Response, [Diagnostics.Stopwatch]$ResponseClock,
        [string]$ServerUrl, [hashtable]$Headers, [string]$DeviceId,
        [string]$HistoryPath, [string]$ApiPrefix = '/api'
    )
    if ($null -eq $Response -or -not $Response.PSObject.Properties['commands']) { return }
    if ($Response.commands -isnot [array] -or $Response.commands.Count -gt 1) {
        Write-AgentLog 'Command response format invalid.'
        return
    }
    if ($Response.commands.Count -eq 0) { return }
    $command = $Response.commands[0]
    if ($null -eq $command -or -not $command.PSObject.Properties['id']) {
        Write-AgentLog 'Command identifier invalid.'
        return
    }
    $commandId = ConvertTo-AgentCommandId $command.id
    if ($null -eq $commandId) {
        Write-AgentLog 'Command identifier invalid.'
        return
    }
    $ackArguments = @{
        ServerUrl = $ServerUrl; Headers = $Headers; DeviceId = $DeviceId; CommandId = $commandId; ApiPrefix = $ApiPrefix
    }
    $serverTime = $null
    $createdAt = $null
    $expiresAt = $null
    if ($Response.PSObject.Properties['serverTime']) { $serverTime = ConvertTo-AgentServerInstant $Response.serverTime }
    if ($command.PSObject.Properties['createdAt']) { $createdAt = ConvertTo-AgentServerInstant $command.createdAt }
    if ($command.PSObject.Properties['expiresAt']) { $expiresAt = ConvertTo-AgentServerInstant $command.expiresAt }
    if (-not $command.PSObject.Properties['type'] -or $command.type -isnot [string] -or $command.type -cnotin @('restart', 'shutdown', 'wake') -or
        $null -eq $serverTime -or $null -eq $createdAt -or $null -eq $expiresAt -or $null -eq $ResponseClock -or
        $createdAt -gt $serverTime -or $expiresAt -le $createdAt -or ($expiresAt - $createdAt).TotalSeconds -gt 60) {
        $null = Send-AgentCommandAck @ackArguments -Status 'failed' -Detail 'invalid_command'
        Write-AgentLog 'Command validation failed.'
        return
    }
    $wakePayload = $null
    if ($command.type -ceq 'wake') {
        try {
            if (-not $command.PSObject.Properties['payload']) { throw 'Missing wake payload.' }
            $wakePayload = Get-AgentValidatedWakePayload $command.payload
        } catch { $null = Send-AgentCommandAck @ackArguments -Status 'failed' -Detail 'invalid_command'; return }
    }
    try {
        $previousIds = Read-AgentCommandHistory $HistoryPath
    } catch {
        $null = Send-AgentCommandAck @ackArguments -Status 'failed' -Detail 'execution_failed'
        Write-AgentLog 'Command history unavailable. Power action refused.'
        return
    }
    if ($previousIds -contains $commandId) {
        $null = Send-AgentCommandAck @ackArguments -Status 'failed' -Detail 'duplicate'
        Write-AgentLog 'Duplicate command refused.'
        return
    }
    # The stopwatch starts BEFORE the heartbeat request. Adding its elapsed
    # duration to serverTime conservatively includes round-trip and ACK delay,
    # so a wrong Windows wall clock cannot extend a command's validity.
    if ($serverTime.Add($ResponseClock.Elapsed) -ge $expiresAt) {
        $null = Send-AgentCommandAck @ackArguments -Status 'failed' -Detail 'expired'
        return
    }
    try {
        $nextIds = @(@($previousIds) + @($commandId) | Select-Object -Last 100)
        # Persist before both acknowledgement and action. If the acknowledgement
        # fails, the reserved ID is still never executed on a later replay.
        Save-AgentCommandHistory -Path $HistoryPath -Ids $nextIds
    } catch {
        $null = Send-AgentCommandAck @ackArguments -Status 'failed' -Detail 'execution_failed'
        Write-AgentLog 'Command could not be persisted. Power action refused.'
        return
    }
    if ($serverTime.Add($ResponseClock.Elapsed) -ge $expiresAt) {
        $null = Send-AgentCommandAck @ackArguments -Status 'failed' -Detail 'expired'
        return
    }
    if (-not (Send-AgentCommandAck @ackArguments -Status 'accepted' -Detail 'accepted')) {
        Write-AgentLog 'Command acceptance was not confirmed. Power action refused.'
        return
    }
    if ($command.type -ceq 'wake') {
        try { $wakePayload = Get-AgentValidatedWakePayload $command.payload }
        catch { $null = Send-AgentCommandAck @ackArguments -Status 'failed' -Detail 'execution_failed'; return }
    }
    if ($serverTime.Add($ResponseClock.Elapsed) -ge $expiresAt) {
        $null = Send-AgentCommandAck @ackArguments -Status 'failed' -Detail 'expired'
        return
    }
    try {
        if ($command.type -ceq 'wake') {
            if (-not (Invoke-AgentWakeAction $wakePayload)) { throw 'Wake send failed.' }
            $null = Send-AgentCommandAck @ackArguments -Status 'succeeded' -Detail 'packet_sent'
            Write-AgentLog 'Wake packet sent. Power-on is not confirmed.'
        } else {
            if (-not (Invoke-AgentPowerAction -Type $command.type)) { throw 'Power action failed.' }
            Write-AgentLog 'Power action accepted by Windows.'
        }
    } catch {
        $null = Send-AgentCommandAck @ackArguments -Status 'failed' -Detail 'execution_failed'
        Write-AgentLog 'Power action failed.'
    }
}

try {
    $instanceLock = Open-AgentInstanceLock (Join-Path $PSScriptRoot '.agent.lock')
    if ($null -eq $instanceLock) { exit 0 }
    $null = Publish-AgentRuntimeStatus -Config $null -Code 'starting'

    try {
        $config = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $serverUri = Get-AgentServerUri $config
        $expectedServerId = Get-AgentExpectedServerId $config
        $apiPrefix = Get-AgentApiPrefix $config
        $hasDeviceToken = $config.PSObject.Properties['deviceToken'] -and [string]$config.deviceToken -match '^[A-Za-z0-9_-]{32,256}$'
        $hasEnrollment = $config.PSObject.Properties['enrollmentToken'] -and [string]$config.enrollmentToken -match '^[A-Za-z0-9_-]{24,256}$'
        $hasAutomaticRegistration = Test-AgentAutomaticRegistration $config
        if ($config.PSObject.Properties['registrationMode'] -and $config.registrationMode -ceq 'automatic' -and
            ($config.PSObject.Properties['ticketId'] -or $config.PSObject.Properties['registrationToken']) -and -not $hasAutomaticRegistration) { throw 'Invalid mixed automatic registration configuration.' }
        $hasIdentity = $config.PSObject.Properties['deviceId'] -and [string]$config.deviceId -match '^[A-Za-z0-9_-]{1,100}$'
        if ((-not $hasAutomaticRegistration -and (-not $hasIdentity -or (-not $hasDeviceToken -and -not $hasEnrollment))) -or ($hasDeviceToken -and -not $hasIdentity)) {
            throw 'Invalid device credentials.'
        }
        $interval = 0
        if (-not [int]::TryParse([string]$config.heartbeatIntervalSeconds, [ref]$interval) -or $interval -lt 5 -or $interval -gt 300) {
            throw 'Invalid heartbeat interval.'
        }
        $endpoint = $serverUri.AbsoluteUri.TrimEnd('/') + $apiPrefix + '/heartbeat'
    } catch {
        $null = Publish-AgentRuntimeStatus -Config $config -Code 'configuration_invalid'
        Write-AgentLog 'Configuration invalid. Reinstall with a new installer.'
        exit 1
    }

    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Write-AgentLog 'Agent started.'
    $null = Publish-AgentRuntimeStatus -Config $config -Code 'starting'
    $wasConnected = $false
    $pendingEnrollmentToken = $null
    $pendingAutomaticIdentity = $null
    $enrollmentFallbackStarted = $false
    $blockedCode = $null
    $blockedHttpStatus = $null
    $serverVerified = $null -eq $expectedServerId
    $serverVerificationAge = $null
    while ($true) {
        if ($null -ne $blockedCode) {
            # Keep a fresh, actionable local diagnosis without repeatedly
            # submitting permanent failures or processing any commands.
            $null = Publish-AgentRuntimeStatus -Config $config -Code $blockedCode -HttpStatus $blockedHttpStatus
            Start-Sleep -Seconds 15
            continue
        }
        if ($null -ne $expectedServerId -and $null -ne $serverVerificationAge -and $serverVerificationAge.Elapsed.TotalSeconds -ge 60) { $serverVerified = $false }
        if (-not $serverVerified) {
            $null = Publish-AgentRuntimeStatus -Config $config -Code 'starting' -Phase 'configuration' -Attempted
            $readiness = Request-AgentServerReadiness $config
            if ($readiness.status -eq 'blocked') {
                $blockedCode = 'configuration_invalid'; $blockedHttpStatus = $readiness.httpStatus
                $null = Publish-AgentRuntimeStatus -Config $config -Code $blockedCode -HttpStatus $blockedHttpStatus
                Write-AgentLog 'Configured server identity or protocol was rejected. Ask your administrator for the correct installer.'
                continue
            }
            if ($readiness.status -eq 'retry') {
                $null = Publish-AgentRuntimeStatus -Config $config -Code 'heartbeat_network_error' -HttpStatus $readiness.httpStatus
                Write-AgentLog 'Server readiness unavailable. Retrying in 30 seconds without sending credentials.'
                Start-Sleep -Seconds 30
                continue
            }
            $serverVerified = $true
            $serverVerificationAge = [Diagnostics.Stopwatch]::StartNew()
        }
        if (-not $hasDeviceToken) {
            if ($hasAutomaticRegistration) {
                if ($null -eq $pendingAutomaticIdentity) {
                    try { $config = Initialize-AgentAutomaticConfiguration -Path (Join-Path $PSScriptRoot 'config.json') -Config $config }
                    catch {
                        $null = Publish-AgentRuntimeStatus -Config $config -Code 'registration_save_failed'
                        Write-AgentLog 'Automatic registration identity could not be prepared or saved. Retrying in 30 seconds.'
                        Start-Sleep -Seconds 30; continue
                    }
                    $null = Publish-AgentRuntimeStatus -Config $config -Code 'registration_pending' -Attempted
                    $automatic = Request-AgentAutomaticEnrollment $config
                    if ($automatic.status -eq 'blocked') {
                        Write-AgentLog 'Automatic registration refused. Ask your administrator to check the ticket and hardware identity or issue a new installer.'
                        $blockedCode = 'registration_blocked'; $blockedHttpStatus = $automatic.httpStatus
                        $null = Publish-AgentRuntimeStatus -Config $config -Code $blockedCode -HttpStatus $blockedHttpStatus
                        continue
                    }
                    if ($automatic.status -eq 'retry') {
                        $null = Publish-AgentRuntimeStatus -Config $config -Code 'registration_network_error' -HttpStatus $automatic.httpStatus
                        Write-AgentLog 'Automatic registration server unavailable. Retrying the saved request in 30 seconds.'
                        Start-Sleep -Seconds 30; continue
                    }
                    $pendingAutomaticIdentity = $automatic.identity
                }
                try {
                    $config = Save-AgentAutomaticEnrollmentConfiguration -Path (Join-Path $PSScriptRoot 'config.json') -Config $config -Identity $pendingAutomaticIdentity
                    $hasDeviceToken = $true; $hasAutomaticRegistration = $false; $pendingAutomaticIdentity = $null
                } catch {
                    $null = Publish-AgentRuntimeStatus -Config $config -Code 'registration_save_failed'
                    Write-AgentLog 'Automatic registration received but configuration could not be saved. Retrying local save in 30 seconds.'
                    Start-Sleep -Seconds 30; continue
                }
            } else {
            if ($null -eq $pendingEnrollmentToken) {
                $null = Publish-AgentRuntimeStatus -Config $config -Code 'registration_pending' -Attempted
                $enrollment = Request-AgentEnrollment -Config $config -ApiPrefix $apiPrefix
                if ($enrollment.status -eq 'blocked') {
                    Write-AgentLog 'Enrollment invalid, consumed or expired. Download a new installer from your administrator.'
                    $blockedCode = 'registration_blocked'; $blockedHttpStatus = $enrollment.httpStatus
                    $null = Publish-AgentRuntimeStatus -Config $config -Code $blockedCode -HttpStatus $blockedHttpStatus
                    continue
                }
                if ($enrollment.status -eq 'retry') {
                    $null = Publish-AgentRuntimeStatus -Config $config -Code 'registration_network_error' -HttpStatus $enrollment.httpStatus
                    Write-AgentLog 'Enrollment server unavailable. Retrying in 30 seconds.'
                    Start-Sleep -Seconds 30; continue
                }
                $pendingEnrollmentToken = $enrollment.token
            }
            try {
                $config = Save-AgentEnrollmentConfiguration -Path (Join-Path $PSScriptRoot 'config.json') -Config $config -DeviceToken $pendingEnrollmentToken -ApiPrefix $apiPrefix
                $hasDeviceToken = $true
                $pendingEnrollmentToken = $null
            } catch {
                $null = Publish-AgentRuntimeStatus -Config $config -Code 'registration_save_failed'
                Write-AgentLog 'Enrollment received but configuration could not be saved. Retrying local save in 30 seconds.'
                Start-Sleep -Seconds 30
                continue
            }
            }
        }
        $headers = @{ Authorization = 'Bearer ' + [string]$config.deviceToken }
        $authenticatedHeartbeat = $false
        try {
            $windows = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
            # This is Windows' reported kernel boot time. Fast Startup can retain it.
            $bootTime = ([DateTime]$windows.LastBootUpTime).ToUniversalTime().ToString('o')
            $payloadObject = @{
                deviceId = [string]$config.deviceId
                hostname = [Environment]::MachineName
                os = ([string]$windows.Caption + ' ' + [string]$windows.Version).Trim()
                bootTime = $bootTime
                agentVersion = $agentVersion
                capabilities = @('power-control-v1', 'network-info-v1', 'wol-relay-v1')
            }
            Add-AgentNetworkInventory $payloadObject
            $payload = $payloadObject | ConvertTo-Json -Compress -Depth 6
            $null = Publish-AgentRuntimeStatus -Config $config -Code 'starting' -Phase 'heartbeat' -Attempted
            $responseClock = [Diagnostics.Stopwatch]::StartNew()
            $response = Invoke-RestMethod -Method Post -Uri $endpoint -Headers $headers -Body ([Text.Encoding]::UTF8.GetBytes($payload)) -ContentType 'application/json; charset=utf-8' -TimeoutSec 10 -MaximumRedirection 0 -ErrorAction Stop
            if (-not (Test-AgentHeartbeatResponse $response)) { throw 'Authenticated heartbeat response was invalid.' }
            if (-not $wasConnected) { Write-AgentLog 'Heartbeat connected.' }
            $wasConnected = $true
            $authenticatedHeartbeat = $true
            $null = Publish-AgentRuntimeStatus -Config $config -Code 'heartbeat_connected'
        } catch {
            $httpStatus = Get-AgentHttpFailureStatus $_
            $policy = Get-AgentHeartbeatFailurePolicy -Config $config -Status $httpStatus -EnrollmentAlreadyAttempted $enrollmentFallbackStarted
            $null = Publish-AgentRuntimeStatus -Config $config -Code $policy.code -HttpStatus $httpStatus
            if ($policy.enroll) {
                $hasDeviceToken = $false
                $enrollmentFallbackStarted = $true
                Write-AgentLog 'Stored credential rejected. Attempting the supplied fresh one-time enrollment.'
            }
            if ($policy.blocked) {
                $blockedCode = $policy.code; $blockedHttpStatus = $httpStatus
                Write-AgentLog 'Device authentication was rejected. Administrator action or a fresh installer is required.'
            } else { Write-AgentLog 'Heartbeat failed. Retrying after interval.' }
            $wasConnected = $false
        }
        if ($authenticatedHeartbeat) {
            try { Invoke-AgentServerCommands -Response $response -ResponseClock $responseClock -ServerUrl $serverUri.AbsoluteUri -Headers $headers -DeviceId ([string]$config.deviceId) -HistoryPath $historyPath -ApiPrefix $apiPrefix }
            catch { Write-AgentLog 'Command processing failed after an authenticated heartbeat.' }
        }
        Start-Sleep -Seconds $interval
    }
} catch {
    $null = Publish-AgentRuntimeStatus -Config $config -Code 'configuration_invalid'
    $failureType = $_.Exception.GetType().Name
    $failureLine = 0
    if ($null -ne $_.InvocationInfo) { $failureLine = [int]$_.InvocationInfo.ScriptLineNumber }
    Write-AgentLog ('Agent stopped unexpectedly. Type ' + $failureType + ' line ' + $failureLine + '.')
    exit 1
} finally {
    if ($null -ne $instanceLock) { $instanceLock.Dispose() }
}
