export interface NavigationItem {
  key: string
  label: string
  to: string
  icon: string
  section: string
  description: string
  keywords: string[]
  entity: string
  aiContext: string
}

export interface NavigationGroup {
  key: string
  label: string
  icon: string
  items: NavigationItem[]
}

export interface SidebarSection {
  key: string
  label: string
  items: NavigationItem[]
}

export const navigationItems: NavigationItem[] = [
  {
    key: 'dashboard',
    label: '대시보드',
    to: '/',
    icon: 'pi pi-home',
    section: '개요',
    description: '자산 현황과 만료 알림',
    keywords: ['홈', '현황', '통계', 'dashboard'],
    entity: 'dashboard',
    aiContext: 'overview.dashboard',
  },
  {
    key: 'devices',
    label: '디바이스',
    to: '/devices',
    icon: 'pi pi-desktop',
    section: '디바이스',
    description: '사번 기준 PC 사용 현황',
    keywords: ['디바이스', 'pc', '컴퓨터', '사번', '사용자', 'serial', 'cpu', 'memory'],
    entity: 'device',
    aiContext: 'device.inventory.employee_device',
  },
  {
    key: 'purchased-devices',
    label: '구매 리스트',
    to: '/purchased-devices',
    icon: 'pi pi-shopping-cart',
    section: '디바이스',
    description: '구매일이 등록된 디바이스',
    keywords: ['구매', '구매한', '구입', '디바이스', '장비', '시리얼', 'purchase'],
    entity: 'device_purchase',
    aiContext: 'device.inventory.purchase_list',
  },
  {
    key: 'distributed-devices',
    label: '배분 리스트',
    to: '/distributed-devices',
    icon: 'pi pi-share-alt',
    section: '디바이스',
    description: '사용자에게 배분된 디바이스',
    keywords: ['배분', '배정', '지급', '사용자', '사번', '디바이스', 'distribution', 'assigned'],
    entity: 'device_distribution',
    aiContext: 'device.inventory.distribution_list',
  },
  {
    key: 'device-licenses',
    label: '라이센스 현황',
    to: '/device-licenses',
    icon: 'pi pi-verified',
    section: '보안',
    description: '사용자별 설치/보안 라이센스',
    keywords: ['라이센스', '한글', 'office', 'cad', 'dlp', 'edr', 'av', '보안', 'security'],
    entity: 'device_license',
    aiContext: 'device.software.license_profile',
  },
  {
    key: 'computer-settings',
    label: '컴퓨터 설정',
    to: '/computer-settings',
    icon: 'pi pi-shield',
    section: '보안',
    description: 'Windows 보안 설정 점검',
    keywords: ['설정', '스마트 앱 컨트롤', '평판', 'exploit', '장치보안', '코어 격리', '보안', 'security'],
    entity: 'computer_setting',
    aiContext: 'device.security.computer_setting',
  },
  {
    key: 'assets',
    label: '자산 목록',
    to: '/assets',
    icon: 'pi pi-box',
    section: '디바이스',
    description: '장비, 태그, 시리얼, 모델',
    keywords: ['디바이스', '장비', '자산', 'asset', 'device', 'serial'],
    entity: 'asset',
    aiContext: 'device.inventory.asset',
  },
  {
    key: 'ip-addresses',
    label: 'IP / MAC',
    to: '/ip-addresses',
    icon: 'pi pi-globe',
    section: '디바이스',
    description: 'IP, MAC, 사용자, 장비 네트워크 현황',
    keywords: ['ip', 'mac', '주소', '네트워크', 'vlan', 'network', '랜카드'],
    entity: 'ip_address',
    aiContext: 'device.network.ip_address',
  },
  {
    key: 'racks',
    label: '서버 랙',
    to: '/racks',
    icon: 'pi pi-server',
    section: '디바이스',
    description: '랙 위치와 사용량',
    keywords: ['랙', '서버', 'rack', 'unit', 'u'],
    entity: 'rack',
    aiContext: 'device.datacenter.rack',
  },
  {
    key: 'maintenance',
    label: '유지보수',
    to: '/maintenance',
    icon: 'pi pi-wrench',
    section: '디바이스',
    description: '정비, 점검, 수리 이력',
    keywords: ['정비', '점검', '수리', 'maintenance'],
    entity: 'maintenance',
    aiContext: 'device.lifecycle.maintenance',
  },
  {
    key: 'certificates',
    label: 'SSL 인증서',
    to: '/certificates',
    icon: 'pi pi-lock',
    section: '보안',
    description: '도메인 인증서와 만료일',
    keywords: ['ssl', 'tls', '인증서', '도메인', 'certificate', '보안', '만료'],
    entity: 'certificate',
    aiContext: 'device.security.certificate',
  },
  {
    key: 'licenses',
    label: '소프트웨어 라이센스',
    to: '/licenses',
    icon: 'pi pi-key',
    section: '계약',
    description: '라이센스 좌석과 만료일',
    keywords: ['라이센스', '소프트웨어', 'license', 'seat'],
    entity: 'software_license',
    aiContext: 'contract.software.license',
  },
  {
    key: 'subscriptions',
    label: 'SaaS/구독',
    to: '/subscriptions',
    icon: 'pi pi-cloud',
    section: '계약',
    description: '클라우드 구독과 비용',
    keywords: ['saas', '구독', '클라우드', '비용', 'subscription'],
    entity: 'cloud_subscription',
    aiContext: 'contract.cloud.subscription',
  },
  {
    key: 'ai-subscriptions',
    label: 'AI 사용 구독',
    to: '/ai-subscriptions',
    icon: 'pi pi-bolt',
    section: '계약',
    description: 'AI 서비스, 모델, 계정, 비용, 토큰 사용량',
    keywords: ['ai', 'openai', 'copilot', 'chatgpt', '구독', '토큰', '모델', '비용'],
    entity: 'ai_subscription',
    aiContext: 'contract.ai.usage_subscription',
  },
  {
    key: 'consumables',
    label: '소모품',
    to: '/consumables',
    icon: 'pi pi-shopping-bag',
    section: '운영',
    description: '재고 수량과 입출고',
    keywords: ['소모품', '재고', '입고', '출고', 'stock'],
    entity: 'consumable',
    aiContext: 'operation.inventory.consumable',
  },
  {
    key: 'notifications',
    label: '알림',
    to: '/notifications',
    icon: 'pi pi-bell',
    section: '운영',
    description: '읽지 않은 알림과 만료 경고',
    keywords: ['알림', '경고', 'notification', 'alert'],
    entity: 'notification',
    aiContext: 'operation.notification',
  },
  {
    key: 'audit-logs',
    label: '사용로그',
    to: '/audit-logs',
    icon: 'pi pi-history',
    section: '관리',
    description: '사용자 작업과 변경 이력',
    keywords: ['사용로그', '감사', '로그', '변경', 'audit', 'history', '보안', '추적'],
    entity: 'audit_log',
    aiContext: 'admin.audit_log',
  },
  {
    key: 'categories',
    label: '카테고리 관리',
    to: '/categories',
    icon: 'pi pi-tags',
    section: '관리',
    description: '자산 분류와 필드 스키마',
    keywords: ['카테고리', '분류', 'category', 'schema'],
    entity: 'category',
    aiContext: 'admin.taxonomy.category',
  },
  {
    key: 'locations',
    label: '위치/부서',
    to: '/locations',
    icon: 'pi pi-map-marker',
    section: '관리',
    description: '장소, 부서, 조직 정보',
    keywords: ['위치', '부서', '장소', 'location', 'department'],
    entity: 'location_department',
    aiContext: 'admin.organization.location_department',
  },
]

const itemByKey = Object.fromEntries(navigationItems.map((item) => [item.key, item]))

function items(keys: string[]): NavigationItem[] {
  return keys.map((key) => itemByKey[key]).filter(Boolean)
}

export const topNavigationGroups: NavigationGroup[] = [
  { key: 'devices', label: '디바이스', icon: 'pi pi-desktop', items: items(['devices', 'purchased-devices', 'distributed-devices', 'assets', 'ip-addresses', 'racks', 'maintenance']) },
  { key: 'security', label: '보안', icon: 'pi pi-shield', items: items(['computer-settings', 'device-licenses', 'certificates']) },
  { key: 'contracts', label: '계약', icon: 'pi pi-briefcase', items: items(['licenses', 'subscriptions', 'ai-subscriptions']) },
  { key: 'operations', label: '운영', icon: 'pi pi-chart-line', items: items(['consumables', 'notifications']) },
  { key: 'admin', label: '관리', icon: 'pi pi-cog', items: items(['categories', 'locations', 'audit-logs']) },
]

export const sidebarSections: SidebarSection[] = [
  { key: 'overview', label: '개요', items: items(['dashboard']) },
  { key: 'devices', label: '디바이스', items: items(['devices', 'purchased-devices', 'distributed-devices', 'assets', 'ip-addresses', 'racks', 'maintenance']) },
  { key: 'security', label: '보안', items: items(['computer-settings', 'device-licenses', 'certificates']) },
  { key: 'contracts', label: '계약', items: items(['licenses', 'subscriptions', 'ai-subscriptions']) },
  { key: 'operations', label: '운영', items: items(['consumables', 'notifications']) },
  { key: 'admin', label: '관리', items: items(['categories', 'locations', 'audit-logs']) },
]

export const featuredSearchItems = items(['devices', 'purchased-devices', 'distributed-devices', 'computer-settings', 'device-licenses', 'ip-addresses'])

export function normalizeSearchText(value: string): string {
  return value.trim().toLocaleLowerCase('ko-KR')
}

export function searchNavigation(query: string, limit = 6): NavigationItem[] {
  const normalized = normalizeSearchText(query)
  if (!normalized) {
    return featuredSearchItems.slice(0, limit)
  }

  return navigationItems
    .map((item) => {
      const haystack = normalizeSearchText(
        [item.label, item.section, item.description, item.entity, item.aiContext, ...item.keywords].join(' '),
      )
      let score = 0
      if (normalizeSearchText(item.label).includes(normalized)) score += 8
      if (normalizeSearchText(item.section).includes(normalized)) score += 5
      if (haystack.includes(normalized)) score += 3
      if (item.keywords.some((keyword) => normalizeSearchText(keyword).includes(normalized))) score += 4
      return { item, score }
    })
    .filter((result) => result.score > 0)
    .sort((a, b) => b.score - a.score || a.item.label.localeCompare(b.item.label, 'ko-KR'))
    .slice(0, limit)
    .map((result) => result.item)
}
