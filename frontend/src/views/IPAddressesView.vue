<template>
  <div>
    <div class="page-header">
      <div>
        <h1>IP / MAC 현황</h1>
        <p class="page-subtitle">디바이스의 IP, MAC, 사용자, 부서, 위치를 한 화면에서 확인합니다.</p>
      </div>
      <Button label="IP 대장 추가" icon="pi pi-plus" @click="openCreate" />
    </div>

    <div class="summary-strip">
      <div class="summary-item"><span>IP/MAC 장비</span><strong>{{ networkItems.length }}</strong></div>
      <div class="summary-item"><span>IP 등록</span><strong>{{ ipTotal }}</strong></div>
      <div class="summary-item"><span>MAC 등록</span><strong>{{ macCount }}</strong></div>
      <div class="summary-item"><span>변경 이력</span><strong>{{ historyTotal }}</strong></div>
    </div>

    <div class="filters-row">
      <IconField>
        <InputIcon class="pi pi-search" />
        <InputText v-model="search" placeholder="IP, MAC, 사용자, 부서, 시리얼 검색" @keyup.enter="load" />
      </IconField>
      <Select v-model="filterStatus" :options="statusOptions" optionLabel="label" optionValue="value" placeholder="IP 대장 상태" showClear @change="load" />
      <Select v-model="groupField" :options="groupOptions" optionLabel="label" optionValue="value" placeholder="디바이스 그룹핑" showClear @change="loadDevices" />
      <Button label="검색" icon="pi pi-search" @click="load" />
    </div>

    <div class="card band-card">
      <div class="card-title-row">
        <div>
          <div class="card-title">IP / MAC 네트워크 보기</div>
          <p class="band-rule">기본은 실제 IP 주소를 부서별로 묶어 표시합니다. VLAN은 하위 보기에서 확인합니다.</p>
        </div>
        <div class="network-actions">
          <div class="view-toggle" aria-label="IP/MAC 하위 보기">
            <button type="button" :class="{ active: networkMode === 'ip' }" @click="networkMode = 'ip'">IP 목록</button>
            <button type="button" :class="{ active: networkMode === 'vlan' }" @click="networkMode = 'vlan'">VLAN 대역</button>
          </div>
          <Tag value="1공장 10.1.x.x · 2공장 22.x.x.x / 10.2.x.x · 3공장 33.x.x.x / 10.3.x.x" severity="info" />
        </div>
      </div>

      <div class="factory-filter-list" aria-label="공장 필터">
        <button
          v-for="factory in factoryFilterItems"
          :key="factory.code || 'all'"
          type="button"
          class="factory-filter-button"
          :class="{ active: bandFactoryFilter === factory.code }"
          @click="setFactoryFilter(factory.code)"
        >
          <strong>{{ factory.label }}</strong>
          <span>{{ factory.total }}개</span>
        </button>
      </div>

      <div class="band-filter-row">
        <Select v-model="bandVlanFilter" :options="bandVlanOptions" optionLabel="label" optionValue="value" placeholder="VLAN" showClear />
        <Select v-model="bandDepartmentFilter" :options="bandDepartmentOptions" optionLabel="label" optionValue="value" placeholder="부서" showClear />
      </div>

      <DataTable
        v-if="networkMode === 'ip'"
        :value="filteredBandRows"
        rowGroupMode="subheader"
        groupRowsBy="departmentGroupKey"
        sortMode="single"
        sortField="departmentGroupKey"
        :sortOrder="1"
        stripedRows
        size="small"
        class="band-ip-table readable-table"
      >
        <template #groupheader="{ data }">
          <div class="group-header department-group">
            <span>{{ data.department }}</span>
            <strong>{{ departmentBandGroupCount(data) }}개 IP</strong>
          </div>
        </template>
        <Column field="address" header="IP 주소" sortable style="min-width:150px">
          <template #body="{ data }"><strong class="ip-text">{{ data.address }}</strong></template>
        </Column>
        <Column field="vlan" header="VLAN" sortable style="width:88px">
          <template #body="{ data }"><span class="vlan-number">{{ data.vlan }}</span></template>
        </Column>
        <Column field="department" header="부서" style="min-width:150px">
          <template #body="{ data }">{{ data.department }}</template>
        </Column>
        <Column field="factoryLabel" header="공장" style="width:92px" />
        <Column field="userNo" header="사용자NO" sortable style="width:105px" />
        <Column header="사용자" style="min-width:150px">
          <template #body="{ data }">
            <div class="stack-cell">
              <strong>{{ data.userName || '-' }}</strong>
              <small>{{ data.employeeNumber || '사번 미등록' }}</small>
            </div>
          </template>
        </Column>
        <Column field="macAddress" header="MAC" style="min-width:155px">
          <template #body="{ data }"><code>{{ data.macAddress || '-' }}</code></template>
        </Column>
        <Column header="디바이스 / 상태" style="min-width:190px">
          <template #body="{ data }">
            <div class="identity-cell">
              <strong>{{ data.serialNumber || data.assetTag || '-' }}</strong>
              <span>{{ [data.deviceTypeLabel, data.ledgerStatusLabel, data.sourceLabel].filter(Boolean).join(' · ') }}</span>
            </div>
          </template>
        </Column>
      </DataTable>

      <DataTable v-if="networkMode === 'vlan'" :value="filteredVlanSummaries" stripedRows size="small" class="band-summary-table readable-table">
        <Column field="factoryLabel" header="공장" style="width:110px" />
        <Column field="vlan" header="VLAN" style="width:88px">
          <template #body="{ data }"><span class="vlan-number">{{ data.vlan }}</span></template>
        </Column>
        <Column field="department" header="부서" style="min-width:150px">
          <template #body="{ data }">
            <strong>{{ data.department }}</strong>
          </template>
        </Column>
        <Column field="subnet" header="대역" />
        <Column header="사용자NO 범위">
          <template #body="{ data }">{{ data.userRange }}</template>
        </Column>
        <Column header="현황" style="min-width:210px">
          <template #body="{ data }">
            <div class="band-meter">
              <span>전체 {{ data.total }}</span>
              <span>사용 {{ data.usedCount }}</span>
              <span>예약 {{ data.reservedCount }}</span>
              <span>가용 {{ data.availableCount }}</span>
            </div>
          </template>
        </Column>
      </DataTable>

      <DataTable
        v-if="networkMode === 'vlan'"
        :value="filteredBandRows"
        rowGroupMode="subheader"
        groupRowsBy="vlanDepartmentKey"
        sortMode="single"
        sortField="vlanDepartmentKey"
        :sortOrder="1"
        stripedRows
        size="small"
        class="band-ip-table readable-table"
      >
        <template #groupheader="{ data }">
          <div class="group-header">
            <span>{{ data.factoryLabel }} · VLAN {{ data.vlan }} · {{ data.department }}</span>
            <strong>{{ bandGroupCount(data) }}건</strong>
          </div>
        </template>
        <Column field="address" header="IP" sortable>
          <template #body="{ data }"><strong>{{ data.address }}</strong></template>
        </Column>
        <Column field="factoryLabel" header="공장" />
        <Column field="vlan" header="VLAN" style="width:88px">
          <template #body="{ data }"><span class="vlan-number">{{ data.vlan }}</span></template>
        </Column>
        <Column field="department" header="부서" style="min-width:150px">
          <template #body="{ data }"><strong>{{ data.department }}</strong></template>
        </Column>
        <Column field="userNo" header="사용자NO" sortable />
        <Column header="사용자">
          <template #body="{ data }">
            <div class="stack-cell">
              <strong>{{ data.userName || '-' }}</strong>
              <small>{{ data.employeeNumber || '사번 미등록' }}</small>
            </div>
          </template>
        </Column>
        <Column field="macAddress" header="MAC">
          <template #body="{ data }"><code>{{ data.macAddress || '-' }}</code></template>
        </Column>
        <Column header="디바이스 / 상태">
          <template #body="{ data }">
            <div class="identity-cell">
              <strong>{{ data.serialNumber || data.assetTag || '-' }}</strong>
              <span>{{ [data.deviceTypeLabel, data.ledgerStatusLabel, data.sourceLabel].filter(Boolean).join(' · ') }}</span>
            </div>
          </template>
        </Column>
      </DataTable>
      <div class="table-note">디바이스 IP와 IP 주소 대장을 합산해 최대 1000건 기준으로 표시</div>
    </div>

    <div class="card">
      <div class="card-title">디바이스 원본 IP / MAC</div>
      <DataTable
        :value="displayNetworkItems"
        :loading="deviceLoading"
        :rowGroupMode="groupField ? 'subheader' : undefined"
        :groupRowsBy="groupField || undefined"
        sortMode="single"
        :sortField="groupField || undefined"
        :sortOrder="1"
        stripedRows
        size="small"
      >
        <template #groupheader="{ data }">
          <div class="group-header">
            <span>{{ groupHeader(data) }}</span>
            <strong>{{ groupCount(data) }}건</strong>
          </div>
        </template>
        <Column field="ip_address" header="IP" sortable>
          <template #body="{ data }"><strong>{{ data.ip_address || '-' }}</strong></template>
        </Column>
        <Column field="mac_address" header="MAC" sortable>
          <template #body="{ data }"><code>{{ data.mac_address || '-' }}</code></template>
        </Column>
        <Column header="사용자" style="min-width:145px">
          <template #body="{ data }">
            <div class="stack-cell">
              <strong>{{ data.user_name || '미지정' }}</strong>
              <small>{{ data.employee_number || '사번 미등록' }}</small>
            </div>
          </template>
        </Column>
        <Column header="부서 / 위치" style="min-width:165px">
          <template #body="{ data }">
            <div class="stack-cell">
              <strong>{{ data.department || '부서 미등록' }}</strong>
              <small>{{ [data.factory, data.location].filter(Boolean).join(' · ') || '위치 미등록' }}</small>
            </div>
          </template>
        </Column>
        <Column header="디바이스">
          <template #body="{ data }">
            <div class="identity-cell">
              <strong>{{ data.serial_number }}</strong>
              <span>{{ deviceTypeLabel(data.device_type) }} · {{ data.os_version || '-' }}</span>
            </div>
          </template>
        </Column>
        <Column style="width:70px">
          <template #body="{ data }">
            <Button icon="pi pi-eye" text rounded size="small" v-tooltip="'자세히'" @click="openNetworkDetail(data)" />
          </template>
        </Column>
      </DataTable>
      <div class="table-note">검색 결과 기준 최대 1000건 표시</div>
    </div>

    <div class="card">
      <div class="card-title">IP 주소 대장</div>
      <DataTable :value="ipItems" :loading="ipLoading" stripedRows size="small">
        <Column field="address" header="IP 주소" sortable />
        <Column field="subnet" header="서브넷" />
        <Column field="gateway" header="게이트웨이" />
        <Column field="dns_primary" header="DNS">
          <template #body="{ data }">{{ [data.dns_primary, data.dns_secondary].filter(Boolean).join(' / ') || '-' }}</template>
        </Column>
        <Column field="vlan" header="VLAN" />
        <Column header="연결 자산">
          <template #body="{ data }">{{ [data.asset_tag, data.asset_name].filter(Boolean).join(' · ') || '-' }}</template>
        </Column>
        <Column field="status" header="상태">
          <template #body="{ data }"><Tag :severity="ipStatusSeverity(data.status)" :value="ipStatusLabel(data.status)" /></template>
        </Column>
        <Column style="width:90px">
          <template #body="{ data }">
            <Button icon="pi pi-pencil" text rounded size="small" @click="startEdit(data)" />
            <Button icon="pi pi-trash" text rounded size="small" severity="danger" @click="remove(data.id)" />
          </template>
        </Column>
      </DataTable>
      <Paginator :rows="size" :totalRecords="ipTotal" :first="(page - 1) * size" @page="onPage" />
    </div>

    <div class="card">
      <div class="card-title">IP / MAC 변경 이력</div>
      <DataTable :value="historyItems" :loading="historyLoading" stripedRows size="small">
        <Column header="변경일" style="min-width:150px">
          <template #body="{ data }">{{ dateTimeText(data.created_at) }}</template>
        </Column>
        <Column header="대상" style="min-width:170px">
          <template #body="{ data }">
            <div class="stack-cell">
              <strong>{{ historyTarget(data) }}</strong>
              <small>{{ sourceLabel(data.source_type) }}</small>
            </div>
          </template>
        </Column>
        <Column header="IP 변경" style="min-width:210px">
          <template #body="{ data }">
            <div class="change-cell">
              <code>{{ data.old_ip_address || '-' }}</code>
              <i class="pi pi-arrow-right"></i>
              <code>{{ data.new_ip_address || '-' }}</code>
            </div>
          </template>
        </Column>
        <Column header="MAC 변경" style="min-width:240px">
          <template #body="{ data }">
            <div class="change-cell">
              <code>{{ data.old_mac_address || '-' }}</code>
              <i class="pi pi-arrow-right"></i>
              <code>{{ data.new_mac_address || '-' }}</code>
            </div>
          </template>
        </Column>
        <Column header="상태">
          <template #body="{ data }">{{ statusChangeText(data) }}</template>
        </Column>
        <Column field="change_reason" header="사유" />
        <Column field="notes" header="비고">
          <template #body="{ data }">{{ data.notes || '-' }}</template>
        </Column>
      </DataTable>
      <Paginator :rows="historySize" :totalRecords="historyTotal" :first="(historyPage - 1) * historySize" @page="onHistoryPage" />
    </div>

    <Dialog v-model:visible="showCreate" :header="editId !== null ? 'IP 대장 수정' : 'IP 대장 추가'" :modal="true" style="width:640px">
      <div class="form-grid">
        <div class="field"><label>IP 주소 *</label><InputText v-model="form.address" fluid /></div>
        <div class="field"><label>서브넷</label><InputText v-model="form.subnet" fluid /></div>
        <div class="field"><label>게이트웨이</label><InputText v-model="form.gateway" fluid /></div>
        <div class="field"><label>DNS 1</label><InputText v-model="form.dns_primary" fluid /></div>
        <div class="field"><label>DNS 2</label><InputText v-model="form.dns_secondary" fluid /></div>
        <div class="field"><label>VLAN 번호</label><InputText v-model="form.vlan" fluid placeholder="예: 20" /></div>
        <div class="field"><label>상태</label><Select v-model="form.status" :options="statusOptions" optionLabel="label" optionValue="value" fluid /></div>
        <div class="field"><label>설명</label><InputText v-model="form.description" fluid /></div>
        <div class="field full"><label>비고</label><Textarea v-model="form.notes" rows="2" fluid /></div>
      </div>
      <template #footer>
        <Button label="취소" severity="secondary" @click="showCreate = false" />
        <Button :label="editId !== null ? '수정' : '저장'" @click="save" />
      </template>
    </Dialog>

    <Dialog v-model:visible="showDetail" header="IP / MAC 상세" :modal="true" style="width:620px">
      <div v-if="selectedDevice" class="detail-grid">
        <div><span>IP</span><strong>{{ selectedDevice.ip_address || '-' }}</strong></div>
        <div><span>MAC</span><strong>{{ selectedDevice.mac_address || '-' }}</strong></div>
        <div><span>사용자</span><strong>{{ selectedDevice.user_name || '미지정' }}</strong></div>
        <div><span>사번</span><strong>{{ selectedDevice.employee_number || '-' }}</strong></div>
        <div><span>부서</span><strong>{{ selectedDevice.department || '-' }}</strong></div>
        <div><span>위치</span><strong>{{ [selectedDevice.factory, selectedDevice.location].filter(Boolean).join(' · ') || '-' }}</strong></div>
        <div><span>시리얼</span><strong>{{ selectedDevice.serial_number }}</strong></div>
        <div><span>OS</span><strong>{{ selectedDevice.os_version || '-' }}</strong></div>
      </div>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Paginator from 'primevue/paginator'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Textarea from 'primevue/textarea'
import Select from 'primevue/select'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import Tag from 'primevue/tag'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'
import api from '@/api'
import type { DeviceRecord, IPAddress, IPChangeHistory } from '@/types'
import { countGroup, groupValue, sortByGroup, type GroupOption } from '@/utils/grouping'

interface IPBandParts {
  valid: boolean
  factoryCode: string
  factoryLabel: string
  vlan: string
  userNo: string
  userNoNumber: number
  subnet: string
}

interface IPBandRow extends IPBandParts {
  address: string
  macAddress: string | null
  department: string
  departmentGroupKey: string
  vlanDepartmentKey: string
  userName: string | null
  employeeNumber: string | null
  serialNumber: string | null
  assetTag: string | null
  deviceTypeLabel: string
  ledgerStatus: string | null
  ledgerStatusLabel: string
  sourceLabel: string
}

const route = useRoute()
const toast = useToast()
const devices = ref<DeviceRecord[]>([])
const ipItems = ref<IPAddress[]>([])
const allIpItems = ref<IPAddress[]>([])
const historyItems = ref<IPChangeHistory[]>([])
const deviceLoading = ref(false)
const ipLoading = ref(false)
const historyLoading = ref(false)
const page = ref(1)
const size = ref(20)
const ipTotal = ref(0)
const historyPage = ref(1)
const historySize = ref(20)
const historyTotal = ref(0)
const search = ref('')
const filterStatus = ref<string | null>(null)
const groupField = ref<string | null>(null)
const networkMode = ref<'ip' | 'vlan'>('ip')
const bandFactoryFilter = ref<string | null>(null)
const bandVlanFilter = ref<string | null>(null)
const bandDepartmentFilter = ref<string | null>(null)
const showCreate = ref(false)
const showDetail = ref(false)
const editId = ref<number | null>(null)
const selectedDevice = ref<DeviceRecord | null>(null)

const statusOptions = [
  { label: '사용 가능', value: 'available' },
  { label: '할당됨', value: 'assigned' },
  { label: '예약됨', value: 'reserved' },
]
const factoryBandOptions = [
  { code: '1', label: '1공장', prefixes: ['10.1'] },
  { code: '2', label: '2공장', prefixes: ['22', '10.2'] },
  { code: '3', label: '3공장', prefixes: ['33', '10.3'] },
]
const groupOptions: GroupOption[] = [
  { label: '사용자 기준', value: 'user_name' },
  { label: '사번 기준', value: 'employee_number' },
  { label: '부서 기준', value: 'department' },
  { label: '위치 기준', value: 'location' },
  { label: '공장 기준', value: 'factory' },
  { label: 'IP 기준', value: 'ip_address' },
  { label: 'MAC 기준', value: 'mac_address' },
  { label: '종류 기준', value: 'device_type', type: 'deviceType' },
  { label: 'OS 기준', value: 'os_version' },
]
const deviceTypeLabels: Record<string, string> = {
  desktop: '데스크탑',
  laptop: '랩탑',
  monitor: '모니터',
  all_in_one: '일체형',
  projector: '빔프로젝터',
  tv: 'TV',
  printer: '프린터',
  unknown: '기타',
}

const form = ref<any>(emptyForm())
const networkItems = computed(() => devices.value.filter((item) => item.ip_address || item.mac_address))
const macCount = computed(() => networkItems.value.filter((item) => item.mac_address).length)
const currentGroupOption = computed(() => groupOptions.find((item) => item.value === groupField.value) ?? null)
const groupFormatters = { deviceType: deviceTypeLabel }
const displayNetworkItems = computed(() => sortByGroup(networkItems.value as unknown as Record<string, unknown>[], currentGroupOption.value, groupFormatters) as unknown as DeviceRecord[])
const bandRows = computed(() => buildBandRows())
const bandVlanOptions = computed(() => {
  const vlans = new Set(
    bandRows.value
      .filter((row) => !bandFactoryFilter.value || row.factoryCode === bandFactoryFilter.value)
      .map((row) => row.vlan)
      .filter((value) => value !== '-'),
  )
  return [...vlans].sort(compareNumericText).map((value) => ({ label: `VLAN ${value}`, value }))
})
const bandDepartmentOptions = computed(() => {
  const departments = new Set(
    bandRows.value
      .filter((row) => !bandFactoryFilter.value || row.factoryCode === bandFactoryFilter.value)
      .filter((row) => !bandVlanFilter.value || row.vlan === bandVlanFilter.value)
      .map((row) => row.department),
  )
  return [...departments].sort((a, b) => a.localeCompare(b, 'ko-KR')).map((value) => ({ label: value, value }))
})
const filteredBandRows = computed(() =>
  bandRows.value.filter((row) => {
    if (bandFactoryFilter.value && row.factoryCode !== bandFactoryFilter.value) return false
    if (bandVlanFilter.value && row.vlan !== bandVlanFilter.value) return false
    if (bandDepartmentFilter.value && row.department !== bandDepartmentFilter.value) return false
    return true
  }),
)
const vlanSummaries = computed(() => buildVlanSummaries(bandRows.value))
const filteredVlanSummaries = computed(() =>
  vlanSummaries.value.filter((item) => {
    if (bandFactoryFilter.value && item.factoryCode !== bandFactoryFilter.value) return false
    if (bandVlanFilter.value && item.vlan !== bandVlanFilter.value) return false
    if (bandDepartmentFilter.value && item.department !== bandDepartmentFilter.value) return false
    return true
  }),
)
const factorySummaries = computed(() =>
  factoryBandOptions.map((factory) => {
    const rows = bandRows.value.filter((row) => row.factoryCode === factory.code)
    return {
      code: factory.code,
      label: factory.label,
      total: rows.length,
      vlanCount: new Set(rows.map((row) => row.vlan)).size,
      usedCount: rows.filter((row) => row.userName || row.serialNumber || row.macAddress).length,
    }
  }),
)
const factoryFilterItems = computed(() => [
  {
    code: null,
    label: '전체',
    total: bandRows.value.length,
  },
  ...factorySummaries.value.map((factory) => ({
    code: factory.code,
    label: factory.label.split(' ')[0],
    total: factory.total,
  })),
])

function routeSearchValue() {
  return typeof route.query.search === 'string' ? route.query.search : ''
}

function emptyForm() {
  return {
    address: '',
    subnet: '',
    gateway: '',
    dns_primary: '',
    dns_secondary: '',
    vlan: '',
    status: 'available',
    description: '',
    notes: '',
  }
}

function parseIpBand(address: string | null | undefined): IPBandParts {
  const fallback = {
    valid: false,
    factoryCode: 'other',
    factoryLabel: '규칙 외',
    vlan: '-',
    userNo: '-',
    userNoNumber: Number.MAX_SAFE_INTEGER,
    subnet: '-',
  }
  if (!address) return fallback

  const octets = address.split('.').map((part) => Number(part))
  const validOctets = octets.length === 4 && octets.every((part) => Number.isInteger(part) && part >= 0 && part <= 255)
  if (!validOctets) return fallback

  const factory = matchFactoryBand(octets)
  if (!factory) {
    return fallback
  }

  return {
    valid: true,
    factoryCode: factory.code,
    factoryLabel: factory.label,
    vlan: String(octets[2]),
    userNo: String(octets[3]),
    userNoNumber: octets[3],
    subnet: `${octets[0]}.${octets[1]}.${octets[2]}.0/24`,
  }
}

function matchFactoryBand(octets: number[]) {
  return factoryBandOptions.find((factory) =>
    factory.prefixes.some((prefix) => {
      const prefixOctets = prefix.split('.').map((part) => Number(part))
      return prefixOctets.every((part, index) => octets[index] === part)
    }),
  )
}

function normalizeDepartment(value: string | null | undefined) {
  return value?.trim() || '부서 미등록'
}

function vlanDepartmentKey(parts: IPBandParts, department: string) {
  return [
    String(factorySortValue(parts.factoryCode)).padStart(2, '0'),
    String(numericValue(parts.vlan)).padStart(3, '0'),
    department,
  ].join('|')
}

function buildBandRows(): IPBandRow[] {
  const rows = new Map<string, IPBandRow>()

  networkItems.value.forEach((device) => {
    if (!device.ip_address) return
    const parsed = parseIpBand(device.ip_address)
    const department = normalizeDepartment(device.department)
    rows.set(device.ip_address, {
      ...parsed,
      address: device.ip_address,
      macAddress: device.mac_address,
      department,
      departmentGroupKey: department,
      vlanDepartmentKey: vlanDepartmentKey(parsed, department),
      userName: device.user_name,
      employeeNumber: device.employee_number,
      serialNumber: device.serial_number,
      assetTag: null,
      deviceTypeLabel: deviceTypeLabel(device.device_type),
      ledgerStatus: null,
      ledgerStatusLabel: '',
      sourceLabel: '디바이스',
    })
  })

  allIpItems.value.forEach((ip) => {
    const parsed = parseIpBand(ip.address)
    const existing = rows.get(ip.address)
    if (existing) {
      existing.ledgerStatus = ip.status
      existing.ledgerStatusLabel = ipStatusLabel(ip.status)
      existing.assetTag = ip.asset_tag
      existing.sourceLabel = '디바이스 + IP 대장'
      return
    }
    rows.set(ip.address, {
      ...parsed,
      address: ip.address,
      macAddress: null,
      department: '부서 미등록',
      departmentGroupKey: '부서 미등록',
      vlanDepartmentKey: vlanDepartmentKey(parsed, '부서 미등록'),
      userName: null,
      employeeNumber: null,
      serialNumber: null,
      assetTag: ip.asset_tag,
      deviceTypeLabel: '',
      ledgerStatus: ip.status,
      ledgerStatusLabel: ipStatusLabel(ip.status),
      sourceLabel: 'IP 대장',
    })
  })

  return [...rows.values()].sort((a, b) => {
    const factoryCompare = factorySortValue(a.factoryCode) - factorySortValue(b.factoryCode)
    if (factoryCompare !== 0) return factoryCompare
    const vlanCompare = numericValue(a.vlan) - numericValue(b.vlan)
    if (vlanCompare !== 0) return vlanCompare
    const departmentCompare = a.department.localeCompare(b.department, 'ko-KR')
    if (departmentCompare !== 0) return departmentCompare
    return a.userNoNumber - b.userNoNumber
  })
}

function buildVlanSummaries(rows: IPBandRow[]) {
  const summaries = new Map<string, {
    factoryCode: string
    factoryLabel: string
    vlan: string
    department: string
    subnet: string
    total: number
    usedCount: number
    reservedCount: number
    availableCount: number
    userNos: number[]
    userRange: string
  }>()

  rows.forEach((row) => {
    const key = `${row.factoryCode}|${row.vlan}|${row.department}`
    if (!summaries.has(key)) {
      summaries.set(key, {
        factoryCode: row.factoryCode,
        factoryLabel: row.factoryLabel,
        vlan: row.vlan,
        department: row.department,
        subnet: row.subnet,
        total: 0,
        usedCount: 0,
        reservedCount: 0,
        availableCount: 0,
        userNos: [],
        userRange: '-',
      })
    }
    const item = summaries.get(key)!
    item.total += 1
    if (row.userName || row.serialNumber || row.macAddress || row.ledgerStatus === 'assigned') item.usedCount += 1
    if (row.ledgerStatus === 'reserved') item.reservedCount += 1
    if (row.ledgerStatus === 'available') item.availableCount += 1
    if (Number.isFinite(row.userNoNumber) && row.userNoNumber !== Number.MAX_SAFE_INTEGER) {
      item.userNos.push(row.userNoNumber)
    }
  })

  return [...summaries.values()]
    .map((item) => {
      const sortedUserNos = [...item.userNos].sort((a, b) => a - b)
      return {
        ...item,
        userRange: sortedUserNos.length > 0 ? `${sortedUserNos[0]} - ${sortedUserNos[sortedUserNos.length - 1]}` : '-',
      }
    })
    .sort((a, b) => {
      const factoryCompare = factorySortValue(a.factoryCode) - factorySortValue(b.factoryCode)
      if (factoryCompare !== 0) return factoryCompare
      const vlanCompare = numericValue(a.vlan) - numericValue(b.vlan)
      if (vlanCompare !== 0) return vlanCompare
      return a.department.localeCompare(b.department, 'ko-KR')
    })
}

function numericValue(value: string) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : Number.MAX_SAFE_INTEGER
}

function factorySortValue(value: string) {
  if (value === 'other') return 99
  return numericValue(value)
}

function compareNumericText(a: string, b: string) {
  return numericValue(a) - numericValue(b)
}

function setFactoryFilter(code: string | null) {
  bandFactoryFilter.value = code
  bandVlanFilter.value = null
  bandDepartmentFilter.value = null
}

async function loadDevices() {
  deviceLoading.value = true
  try {
    const params: any = { page: 1, size: 1000 }
    if (search.value) params.search = search.value
    const { data } = await api.get('/devices', { params })
    devices.value = data.items
  } finally {
    deviceLoading.value = false
  }
}

async function loadIps() {
  ipLoading.value = true
  try {
    const params: any = { page: page.value, size: size.value }
    if (search.value) params.search = search.value
    if (filterStatus.value) params.status = filterStatus.value
    const bandParams = { ...params, page: 1, size: 1000 }
    const [pageRes, bandRes] = await Promise.all([
      api.get('/ip-addresses', { params }),
      api.get('/ip-addresses', { params: bandParams }),
    ])
    ipItems.value = pageRes.data.items
    ipTotal.value = pageRes.data.total
    allIpItems.value = bandRes.data.items
  } finally {
    ipLoading.value = false
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const params: any = { page: historyPage.value, size: historySize.value }
    if (search.value) params.search = search.value
    const { data } = await api.get('/ip-change-history', { params })
    historyItems.value = data.items
    historyTotal.value = data.total
  } finally {
    historyLoading.value = false
  }
}

function load() {
  page.value = 1
  historyPage.value = 1
  void loadDevices()
  void loadIps()
  void loadHistory()
}

function onPage(e: any) {
  page.value = e.page + 1
  void loadIps()
}

function onHistoryPage(e: any) {
  historyPage.value = e.page + 1
  void loadHistory()
}

function openCreate() {
  editId.value = null
  form.value = emptyForm()
  showCreate.value = true
}

function startEdit(item: IPAddress) {
  editId.value = item.id
  form.value = { ...item }
  showCreate.value = true
}

function openNetworkDetail(item: DeviceRecord) {
  selectedDevice.value = item
  showDetail.value = true
}

async function save() {
  try {
    const payload = normalizePayload(form.value)
    if (editId.value !== null) await api.put(`/ip-addresses/${editId.value}`, payload)
    else await api.post('/ip-addresses', payload)
    toast.add({ severity: 'success', summary: '저장 완료', life: 3000 })
    showCreate.value = false
    editId.value = null
    void loadIps()
    void loadHistory()
  } catch (err: any) {
    toast.add({ severity: 'error', summary: '오류', detail: err.response?.data?.detail ?? '실패', life: 5000 })
  }
}

async function remove(id: number) {
  await api.delete(`/ip-addresses/${id}`)
  void loadIps()
}

function normalizePayload(source: Record<string, any>) {
  const payload = { ...source }
  Object.keys(payload).forEach((key) => {
    if (payload[key] === '') payload[key] = null
  })
  return payload
}

function deviceTypeLabel(value: string) {
  return deviceTypeLabels[value] ?? value
}

function ipStatusLabel(value: string) {
  return statusOptions.find((item) => item.value === value)?.label ?? value
}

function ipStatusSeverity(value: string): any {
  return { available: 'success', assigned: 'info', reserved: 'warn' }[value] ?? 'secondary'
}

function sourceLabel(value: string) {
  return value === 'device' ? '디바이스 IP/MAC' : 'IP 주소 대장'
}

function historyTarget(item: IPChangeHistory) {
  return item.new_serial_number || item.old_serial_number || item.asset_tag || item.asset_name || '-'
}

function statusChangeText(item: IPChangeHistory) {
  if (!item.old_status && !item.new_status) return '-'
  return `${item.old_status || '-'} -> ${item.new_status || '-'}`
}

function dateTimeText(value: string | null) {
  if (!value) return '-'
  return new Date(value).toLocaleString('ko-KR')
}

function bandGroupCount(item: IPBandRow) {
  return filteredBandRows.value.filter((row) => row.vlanDepartmentKey === item.vlanDepartmentKey).length
}

function departmentBandGroupCount(item: IPBandRow) {
  return filteredBandRows.value.filter((row) => row.department === item.department).length
}

function groupHeader(item: DeviceRecord) {
  const option = currentGroupOption.value
  if (!option) return ''
  return `${option.label}: ${groupValue(item as unknown as Record<string, unknown>, option, groupFormatters)}`
}

function groupCount(item: DeviceRecord) {
  return countGroup(displayNetworkItems.value as unknown as Record<string, unknown>[], item as unknown as Record<string, unknown>, currentGroupOption.value, groupFormatters)
}

watch(
  () => route.query.search,
  () => {
    const nextSearch = routeSearchValue()
    if (nextSearch !== search.value) {
      search.value = nextSearch
      load()
    }
  },
)

watch([bandFactoryFilter, bandVlanFilter], () => {
  if (!bandDepartmentFilter.value) return
  const exists = bandDepartmentOptions.value.some((item) => item.value === bandDepartmentFilter.value)
  if (!exists) bandDepartmentFilter.value = null
})

onMounted(() => {
  search.value = routeSearchValue()
  load()
})
</script>

<style scoped>
.page-subtitle{margin-top:0.25rem;color:#64748b;font-size:0.9rem}
.card-title-row{display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;margin-bottom:1rem}
.band-rule{margin:0.2rem 0 0;color:#64748b;font-size:0.84rem;font-weight:600;line-height:1.45}
.band-card :deep(.p-tag){white-space:normal;text-align:left;line-height:1.35}
.network-actions{display:flex;align-items:flex-start;justify-content:flex-end;gap:0.6rem;flex-wrap:wrap}
.factory-filter-list{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:0.5rem;margin-bottom:0.85rem}
.factory-filter-button{border:1px solid #dbe3ef;border-radius:8px;background:#fff;display:flex;align-items:center;justify-content:space-between;gap:0.65rem;padding:0.7rem 0.85rem;text-align:left;cursor:pointer;min-height:44px}
.factory-filter-button:hover,.factory-filter-button.active{border-color:#2563eb;background:#eef4ff}
.factory-filter-button strong{color:#0f172a;font-size:0.92rem;line-height:1.1}.factory-filter-button span{color:#475569;font-size:0.82rem;font-weight:800;white-space:nowrap}
.band-filter-row{display:flex;align-items:center;gap:0.5rem;margin-bottom:0.85rem;flex-wrap:wrap}
.band-summary-table{margin-bottom:0.9rem}.band-ip-table{border-top:1px solid #eef2f7;padding-top:0.75rem}
.band-meter{display:flex;align-items:center;gap:0.45rem;flex-wrap:wrap}.band-meter span{border:1px solid #e2e8f0;border-radius:999px;padding:0.18rem 0.5rem;color:#475569;font-size:0.78rem;font-weight:700;background:#fff}
.summary-strip{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:0.75rem;margin-bottom:1rem}
.summary-item{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:0.85rem 1rem;display:flex;align-items:center;justify-content:space-between}
.summary-item span{color:#64748b;font-size:0.85rem;font-weight:600}.summary-item strong{color:#0f172a;font-size:1.35rem}
.view-toggle{display:inline-flex;align-items:center;gap:0.25rem;border:1px solid #dbe3ef;background:#f8fafc;border-radius:8px;padding:0.2rem}
.view-toggle button{border:0;background:transparent;border-radius:6px;color:#475569;cursor:pointer;font-weight:800;padding:0.5rem 0.75rem;white-space:nowrap}
.view-toggle button.active{background:#fff;color:#1d4ed8;box-shadow:0 1px 2px rgba(15,23,42,.08)}
.card + .card{margin-top:1rem}.card-title{font-weight:800;color:#0f172a;margin-bottom:0.75rem}
.identity-cell{display:flex;flex-direction:column;gap:0.2rem}.identity-cell strong{font-size:0.9rem;color:#0f172a}.identity-cell span{font-size:0.78rem;color:#64748b}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;color:#334155}
.change-cell{display:flex;align-items:center;gap:0.45rem;white-space:nowrap}.change-cell i{color:#94a3b8;font-size:0.8rem}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.field{display:flex;flex-direction:column;gap:0.25rem}.field.full{grid-column:1/-1}.field label{font-size:0.85rem;font-weight:600;color:#475569}
.group-header{width:100%;display:flex;align-items:center;justify-content:space-between;padding:0.55rem 0.35rem;color:#0f172a}.group-header span{font-weight:800}.group-header strong,.table-note{color:#64748b;font-size:0.82rem}.table-note{padding:0.85rem 0.25rem 0;text-align:right}
.department-group{background:#f8fafc;border-left:3px solid #2563eb;padding-left:0.65rem}
.ip-text{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;color:#0f172a;font-size:0.92rem}
.vlan-number{display:inline-flex;align-items:center;justify-content:center;min-width:2.4rem;border-radius:6px;background:#eef2ff;color:#3730a3;font-weight:900;padding:0.2rem 0.45rem}
.readable-table :deep(.p-datatable-thead > tr > th){background:#f8fafc;color:#475569;font-size:0.78rem}
.readable-table :deep(.p-datatable-tbody > tr > td){padding-top:0.65rem;padding-bottom:0.65rem}
.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:0.85rem}.detail-grid div{border:1px solid #e2e8f0;border-radius:8px;padding:0.75rem;display:flex;flex-direction:column;gap:0.25rem}.detail-grid span{font-size:0.78rem;color:#64748b}.detail-grid strong{font-size:0.95rem;color:#0f172a}
@media (max-width:900px){.summary-strip,.form-grid,.detail-grid,.factory-filter-list{grid-template-columns:1fr}.card-title-row,.band-filter-row,.network-actions{flex-direction:column;align-items:stretch}.view-toggle{width:100%}.view-toggle button{flex:1}}
</style>
