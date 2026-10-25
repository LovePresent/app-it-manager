export interface AgentNetworkAdapter {
  id: string
  name: string
  macAddress: string | null
  ipv4: Array<{ address: string; netmask: string }>
  ipv6: string[]
  physical: boolean
}

export interface AgentWolConfiguration {
  macAddress: string
  relayDeviceId: number
  sourceAddress: string
  broadcastAddress: string
  port: number
}

export interface AgentIpReview {
  incident_id: string
  state: 'open' | 'reviewing' | 'resolved'
  note: string | null
  reviewed_by: string | null
  reviewed_at: string | null
}

export interface AgentNetworkMonitor {
  status: 'normal' | 'mismatch' | 'unknown'
  source: 'inventory' | 'first_seen' | 'unconfigured'
  expected_ipv4: string[]
  observed_ipv4: string[]
  baseline_ipv4: string[]
  checked_at: string | null
  alert_active: boolean
  stale: boolean
  last_status?: 'normal' | 'mismatch' | 'unknown' | null
  reference_error: boolean
  reference_pending: boolean
  review: AgentIpReview | null
}

export interface DeviceAgent {
  id: string
  device_id: number
  name: string
  serial_number: string
  status: 'pending' | 'online' | 'offline' | 'revoked' | 'uninstalled' | 'worker_missing' | 'worker_stopped'
  installation_state?: 'pending' | 'installed' | 'uninstalled'
  uninstalled_at?: string | null
  service_state?: 'running' | 'worker_stopped' | 'worker_missing' | null
  service_last_seen_at?: string | null
  network_monitor?: AgentNetworkMonitor | null
  last_seen_at: string | null
  hostname: string | null
  os_version?: string | null
  boot_time?: string | null
  agent_version: string | null
  network_adapters: AgentNetworkAdapter[]
  network_updated_at: string | null
  observed_ip: string | null
  capabilities: string[]
  wol: AgentWolConfiguration | null
  enrollment_expires_at: string | null
}

export interface DeviceAgentCommand {
  id: string
  type: 'restart' | 'shutdown' | 'wake'
  status: 'pending' | 'delivered' | 'accepted' | 'failed' | 'expired' | 'unconfirmed' | 'sent'
  detail: string | null
  created_at: string
  expires_at: string | null
  delivered_at?: string | null
  acknowledged_at?: string | null
  finished_at?: string | null
}

export interface DeviceAgentListResponse {
  items: DeviceAgent[]
  total: number
  server_time: string
  heartbeat_interval_seconds: number
  offline_after_seconds: number
  installer_formats: Array<'exe'>
  latest_agent_version?: string
}

export interface DeviceAgentDetailResponse {
  agent: DeviceAgent | null
  commands: DeviceAgentCommand[]
  relay_devices: DeviceAgent[]
  server_time: string
  installer_formats: Array<'exe'>
  latest_agent_version?: string
}
