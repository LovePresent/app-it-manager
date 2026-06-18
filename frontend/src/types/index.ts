export interface User {
  id: number
  email: string
  name: string
  display_name: string
  role: string
  department: string | null
  is_admin: boolean
  is_active: boolean
  avatar_url: string | null
}

export interface Category {
  id: number
  name: string
  slug: string
  icon: string | null
  description: string | null
  sort_order: number
}

export interface Location {
  id: number
  name: string
  type: string | null
  parent_id: number | null
  description: string | null
  created_at: string | null
}

export interface Department {
  id: number
  name: string
  code: string | null
  manager: string | null
  created_at: string | null
}

export interface Vendor {
  id: number
  name: string
  contact_person: string | null
  contact_email: string | null
  contact_phone: string | null
  website: string | null
  notes: string | null
}

export interface Asset {
  id: number
  asset_tag: string
  name: string
  category_id: number
  category_name: string | null
  status: AssetStatus
  serial_number: string | null
  model: string | null
  manufacturer: string | null
  purchase_date: string | null
  purchase_price: number | null
  warranty_expiry: string | null
  location_id: number | null
  location_name: string | null
  department_id: number | null
  department_name: string | null
  assigned_to: number | null
  assigned_user_name: string | null
  vendor_id: number | null
  vendor_name: string | null
  notes: string | null
  custom_fields: Record<string, any>
  qr_code_path: string | null
  created_at: string
  updated_at: string
}

export type AssetStatus = 'in_stock' | 'assigned' | 'in_maintenance' | 'retired' | 'disposed' | 'lost'

export interface DeviceLicenseSummary {
  hangul: boolean
  ms_office: boolean
  cad: boolean
  windows_security: boolean
  pc_manager: boolean
  dlp: boolean
  av: boolean
  edr: boolean
  renewal_date: string | null
}

export interface ComputerSettingSummary {
  smart_app_control: boolean
  reputation_based_protection: boolean
  exploit_protection: boolean
  core_isolation: boolean
}

export interface DeviceRecord {
  id: number
  user_name: string | null
  employee_number: string | null
  serial_number: string
  device_type: string
  cpu: string | null
  memory: string | null
  storage: string | null
  gpu: string | null
  os_version: string | null
  ip_address: string | null
  mac_address: string | null
  purchase_date: string | null
  manufacture_date: string | null
  location: string | null
  department: string | null
  factory: string | null
  status: string
  notes: string | null
  license_summary: DeviceLicenseSummary | null
  computer_setting_summary: ComputerSettingSummary | null
  created_at: string | null
  updated_at: string | null
}

export interface DeviceLicenseRecord {
  id: number
  device_id: number
  user_name: string | null
  employee_number: string | null
  serial_number: string | null
  device_type: string | null
  location: string | null
  department: string | null
  factory: string | null
  hangul: boolean
  ms_office: boolean
  cad: boolean
  windows_security: boolean
  pc_manager: boolean
  dlp: boolean
  av: boolean
  edr: boolean
  purchase_date: string | null
  manufacture_date: string | null
  renewal_date: string | null
  notes: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ComputerSettingRecord {
  id: number
  device_id: number
  user_name: string | null
  employee_number: string | null
  serial_number: string | null
  device_type: string | null
  location: string | null
  department: string | null
  factory: string | null
  smart_app_control: boolean
  reputation_based_protection: boolean
  exploit_protection: boolean
  core_isolation: boolean
  notes: string | null
  created_at: string | null
  updated_at: string | null
}

export interface DeviceUsageHistory {
  id: number
  device_id: number
  user_name: string | null
  employee_number: string | null
  serial_number: string
  started_at: string | null
  ended_at: string | null
  change_reason: string
  notes: string | null
  created_at: string | null
}

export interface SoftwareLicense {
  id: number
  asset_id: number
  asset_name: string | null
  asset_tag: string | null
  vendor_id: number | null
  vendor_name: string | null
  license_key: string | null
  license_type: string | null
  seats_total: number | null
  seats_used: number
  expiry_date: string | null
  notes: string | null
  created_at: string
}

export interface CloudSubscription {
  id: number
  asset_id: number
  asset_name: string | null
  asset_tag: string | null
  provider: string | null
  plan: string | null
  billing_cycle: string | null
  renewal_date: string | null
  monthly_cost: number | null
  auto_renew: boolean
  account_url: string | null
  notes: string | null
  created_at: string
}

export interface IPAddress {
  id: number
  address: string
  subnet: string | null
  gateway: string | null
  dns_primary: string | null
  dns_secondary: string | null
  vlan: string | null
  status: string
  asset_id: number | null
  asset_name: string | null
  asset_tag: string | null
  description: string | null
  notes: string | null
  created_at: string
}

export interface IPChangeHistory {
  id: number
  source_type: string
  source_id: number
  device_id: number | null
  ip_address_id: number | null
  old_serial_number: string | null
  new_serial_number: string | null
  user_name: string | null
  employee_number: string | null
  asset_tag: string | null
  asset_name: string | null
  old_ip_address: string | null
  new_ip_address: string | null
  old_mac_address: string | null
  new_mac_address: string | null
  old_status: string | null
  new_status: string | null
  change_reason: string
  notes: string | null
  created_at: string | null
}

export interface AIUsageSubscription {
  id: number
  service_name: string
  provider: string | null
  model_name: string | null
  plan_name: string | null
  account_email: string | null
  owner_name: string | null
  employee_number: string | null
  department: string | null
  billing_cycle: string | null
  monthly_cost: number | null
  token_limit: number | null
  used_tokens: number | null
  renewal_date: string | null
  auto_renew: boolean
  status: string
  usage_purpose: string | null
  notes: string | null
  created_at: string | null
  updated_at: string | null
}

export interface Certificate {
  id: number
  asset_id: number
  asset_name: string | null
  asset_tag: string | null
  domain: string
  issuer: string | null
  cert_type: string | null
  issued_date: string | null
  expiry_date: string | null
  auto_renew: boolean
  registrar: string | null
  notes: string | null
  created_at: string
}

export interface ConsumableStock {
  id: number
  asset_id: number
  asset_name: string | null
  asset_tag: string | null
  unit: string
  qty_in_stock: number
  min_stock_level: number
  last_restock_date: string | null
  is_low_stock: boolean
  created_at: string
}

export interface MaintenanceRecord {
  id: number
  asset_id: number
  asset_name: string | null
  asset_tag: string | null
  maintenance_type: string
  description: string | null
  cost: number | null
  scheduled_date: string | null
  completed_date: string | null
  vendor_id: number | null
  vendor_name: string | null
  technician: string | null
  status: string
  notes: string | null
  created_at: string
}

export interface Rack {
  id: number
  name: string
  location_id: number | null
  location_name: string | null
  total_units: number
  used_units: number
  power_capacity: number | null
  description: string | null
  created_at: string
}

export interface Notification {
  id: number
  user_id: number | null
  title: string
  message: string
  type: string
  entity_type: string | null
  entity_id: number | null
  is_read: boolean
  created_at: string
}

export interface AuditLog {
  id: number
  user_id: number | null
  user_email: string | null
  action: string
  entity_type: string
  entity_id: number | null
  changes: Record<string, any> | null
  ip_address: string | null
  created_at: string
}

export interface DashboardStats {
  total_assets: number
  assigned_assets: number
  in_stock_assets: number
  in_maintenance_assets: number
  retired_assets: number
  total_licenses: number
  expiring_licenses: number
  total_subscriptions: number
  total_monthly_cost: number
  total_certificates: number
  expiring_certificates: number
  total_ip_addresses: number
  low_stock_consumables: number
  pending_maintenance: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  size: number
  pages: number
}

export interface AssignmentRecord {
  id: number
  asset_id: number
  user_id: number
  user_name: string | null
  assigned_at: string
  returned_at: string | null
  notes: string | null
}
