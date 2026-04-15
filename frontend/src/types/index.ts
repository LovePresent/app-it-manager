export interface User {
  id: number
  email: string
  display_name: string
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
  is_active: boolean
}

export interface Location {
  id: number
  name: string
  building: string | null
  floor: string | null
  room: string | null
}

export interface Department {
  id: number
  name: string
  code: string | null
  manager_name: string | null
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
  purchase_cost: number | null
  warranty_expiry: string | null
  location_id: number | null
  location_name: string | null
  department_id: number | null
  department_name: string | null
  assigned_to_id: number | null
  assigned_to_name: string | null
  vendor_id: number | null
  notes: string | null
  custom_fields: Record<string, any>
  qr_code_path: string | null
  created_at: string
  updated_at: string
}

export type AssetStatus = 'in_stock' | 'assigned' | 'in_maintenance' | 'retired' | 'disposed' | 'lost'

export interface SoftwareLicense {
  id: number
  name: string
  vendor: string | null
  license_key: string | null
  license_type: string | null
  total_seats: number
  used_seats: number
  purchase_date: string | null
  expiry_date: string | null
  cost: number | null
  notes: string | null
  created_at: string
}

export interface CloudSubscription {
  id: number
  service_name: string
  provider: string | null
  plan: string | null
  account_email: string | null
  start_date: string | null
  renewal_date: string | null
  monthly_cost: number | null
  annual_cost: number | null
  status: string
  notes: string | null
  created_at: string
}

export interface IPAddress {
  id: number
  ip_address: string
  subnet_mask: string | null
  gateway: string | null
  dns: string | null
  vlan: string | null
  assigned_to: string | null
  device_name: string | null
  status: string
  notes: string | null
  created_at: string
}

export interface Certificate {
  id: number
  domain: string
  issuer: string | null
  certificate_type: string | null
  issued_date: string | null
  expiry_date: string | null
  auto_renew: boolean
  provider: string | null
  cost: number | null
  notes: string | null
  created_at: string
}

export interface ConsumableStock {
  id: number
  name: string
  category: string | null
  unit: string
  current_qty: number
  min_qty: number
  location: string | null
  notes: string | null
  created_at: string
}

export interface MaintenanceRecord {
  id: number
  asset_id: number
  asset_name: string | null
  type: string
  description: string | null
  performed_by: string | null
  performed_date: string | null
  cost: number | null
  status: string
  next_maintenance_date: string | null
  notes: string | null
  created_at: string
}

export interface Rack {
  id: number
  name: string
  location: string | null
  total_units: number
  used_units: number
  power_capacity: string | null
  notes: string | null
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
  assigned_date: string
  returned_date: string | null
  notes: string | null
}
