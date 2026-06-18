<template>
  <div>
    <div class="page-header">
      <div>
        <h1>{{ pageTitle }}</h1>
        <p class="page-subtitle">{{ pageSubtitle }}</p>
      </div>
      <Button label="디바이스 전체" icon="pi pi-desktop" severity="secondary" @click="goDevices()" />
    </div>

    <div class="summary-strip">
      <div class="summary-item">
        <span>{{ reportMode === 'purchase' ? '구매 등록' : '배분 중' }}</span>
        <strong>{{ total }}</strong>
      </div>
      <div class="summary-item">
        <span>현재 표시</span>
        <strong>{{ displayItems.length }}</strong>
      </div>
      <div class="summary-item">
        <span>사용 중</span>
        <strong>{{ assignedCount }}</strong>
      </div>
      <div class="summary-item">
        <span>재고</span>
        <strong>{{ stockCount }}</strong>
      </div>
    </div>

    <div class="filters-row">
      <IconField>
        <InputIcon class="pi pi-search" />
        <InputText v-model="search" :placeholder="searchPlaceholder" @keyup.enter="resetAndLoad" />
      </IconField>
      <Select v-model="filterType" :options="deviceTypeOptions" optionLabel="label" optionValue="value" placeholder="종류" showClear @change="resetAndLoad" />
      <Select v-model="filterFactory" :options="factoryOptions" placeholder="공장" showClear @change="resetAndLoad" />
      <Select
        v-if="reportMode === 'purchase'"
        v-model="filterStatus"
        :options="statusOptions"
        optionLabel="label"
        optionValue="value"
        placeholder="상태"
        showClear
        @change="resetAndLoad"
      />
      <Select v-model="groupField" :options="groupOptions" optionLabel="label" optionValue="value" placeholder="그룹핑" showClear @change="resetAndLoad" />
    </div>

    <div class="card">
      <DataTable
        :value="displayItems"
        :loading="loading"
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
        <Column v-if="reportMode === 'purchase'" field="purchase_date" header="구매일" sortable style="width:130px" />
        <Column header="사용자" style="min-width:150px">
          <template #body="{ data }">
            <div class="stack-cell">
              <strong>{{ data.user_name || '미배분' }}</strong>
              <small>{{ data.employee_number || '사번 미등록' }}</small>
            </div>
          </template>
        </Column>
        <Column header="부서 / 위치" style="min-width:180px">
          <template #body="{ data }">
            <div class="stack-cell">
              <strong>{{ data.department || '부서 미등록' }}</strong>
              <small>{{ [data.factory, data.location].filter(Boolean).join(' · ') || '위치 미등록' }}</small>
            </div>
          </template>
        </Column>
        <Column header="디바이스" style="min-width:220px">
          <template #body="{ data }">
            <div class="identity-cell">
              <strong>{{ data.serial_number }}</strong>
              <span>{{ deviceTypeLabel(data.device_type) }}</span>
            </div>
          </template>
        </Column>
        <Column header="사양" style="min-width:280px">
          <template #body="{ data }">
            <div class="spec-list">
              <span>CPU {{ data.cpu || '-' }}</span>
              <span>MEM {{ data.memory || '-' }}</span>
              <span>{{ data.storage || 'SSD/HDD -' }}</span>
              <span>GPU {{ data.gpu || '-' }}</span>
            </div>
          </template>
        </Column>
        <Column v-if="reportMode === 'distribution'" field="purchase_date" header="구매일" sortable style="width:130px">
          <template #body="{ data }">{{ data.purchase_date || '-' }}</template>
        </Column>
        <Column header="IP / MAC" style="min-width:190px">
          <template #body="{ data }">
            <div class="identity-cell">
              <strong>{{ data.ip_address || '-' }}</strong>
              <span>{{ data.mac_address || '-' }}</span>
            </div>
          </template>
        </Column>
        <Column header="상태" style="width:100px">
          <template #body="{ data }">
            <Tag :value="statusLabel(data.status)" :severity="statusSeverity(data.status)" />
          </template>
        </Column>
        <Column style="width:70px">
          <template #body="{ data }">
            <Button icon="pi pi-search" text rounded size="small" v-tooltip="'디바이스에서 보기'" @click="goDevices(data.serial_number)" />
          </template>
        </Column>
      </DataTable>
      <Paginator v-if="!groupField" :rows="size" :totalRecords="total" :first="(page - 1) * size" @page="onPage" />
      <div v-else class="group-footer">그룹핑 보기: {{ displayItems.length }}건 표시</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import InputText from 'primevue/inputtext'
import Paginator from 'primevue/paginator'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import api from '@/api'
import type { DeviceRecord } from '@/types'
import { countGroup, groupValue, sortByGroup, type GroupOption } from '@/utils/grouping'

type ReportMode = 'purchase' | 'distribution'

const route = useRoute()
const router = useRouter()
const items = ref<DeviceRecord[]>([])
const loading = ref(false)
const page = ref(1)
const size = ref(30)
const total = ref(0)
const search = ref('')
const filterType = ref<string | null>(null)
const filterFactory = ref<string | null>(null)
const filterStatus = ref<string | null>(null)
const groupField = ref<string | null>(null)

const reportMode = computed<ReportMode>(() => (route.meta.reportMode === 'distribution' ? 'distribution' : 'purchase'))
const pageTitle = computed(() => (reportMode.value === 'purchase' ? '구매 리스트' : '배분 리스트'))
const pageSubtitle = computed(() =>
  reportMode.value === 'purchase'
    ? '구매일이 등록된 디바이스를 구매 기준으로 확인합니다.'
    : '현재 사용자에게 배분되어 사용 중인 디바이스를 확인합니다.',
)
const searchPlaceholder = computed(() =>
  reportMode.value === 'purchase' ? '시리얼, 사용자, 사번, 사양 검색' : '사용자, 사번, 시리얼, 부서 검색',
)

const deviceTypeOptions = [
  { label: '데스크탑', value: 'desktop' },
  { label: '랩탑', value: 'laptop' },
  { label: '일체형', value: 'all_in_one' },
  { label: '모니터', value: 'monitor' },
  { label: '빔프로젝터', value: 'projector' },
  { label: 'TV', value: 'tv' },
  { label: '프린터', value: 'printer' },
  { label: '기타', value: 'unknown' },
]
const factoryOptions = ['1공장', '2공장', '3공장', '본관', '연구소']
const statusOptions = [
  { label: '사용 중', value: 'assigned' },
  { label: '재고', value: 'stock' },
  { label: '교체됨', value: 'replaced' },
  { label: '퇴역', value: 'retired' },
]
const statusLabels: Record<string, string> = {
  assigned: '사용 중',
  stock: '재고',
  replaced: '교체됨',
  retired: '퇴역',
}
const statusSeverityMap: Record<string, string> = {
  assigned: 'success',
  stock: 'warn',
  replaced: 'secondary',
  retired: 'secondary',
}
const groupOptions: GroupOption[] = [
  { label: '사용자 기준', value: 'user_name' },
  { label: '사번 기준', value: 'employee_number' },
  { label: '부서 기준', value: 'department' },
  { label: '위치 기준', value: 'location' },
  { label: '공장 기준', value: 'factory' },
  { label: '종류 기준', value: 'device_type', type: 'deviceType' },
  { label: '상태 기준', value: 'status', type: 'status' },
  { label: '구매일 기준', value: 'purchase_date' },
]

const currentGroupOption = computed(() => groupOptions.find((item) => item.value === groupField.value) ?? null)
const groupFormatters = { deviceType: deviceTypeLabel, status: statusLabel }
const displayItems = computed(() =>
  sortByGroup(items.value as unknown as Record<string, unknown>[], currentGroupOption.value, groupFormatters) as unknown as DeviceRecord[],
)
const assignedCount = computed(() => items.value.filter((item) => item.status === 'assigned').length)
const stockCount = computed(() => items.value.filter((item) => item.status === 'stock').length)

function buildParams() {
  const params: Record<string, unknown> = {
    page: groupField.value ? 1 : page.value,
    size: groupField.value ? 1000 : size.value,
  }
  if (search.value) params.search = search.value
  if (filterType.value) params.device_type = filterType.value
  if (filterFactory.value) params.factory = filterFactory.value
  if (reportMode.value === 'purchase') {
    params.has_purchase_date = true
    if (filterStatus.value) params.status = filterStatus.value
  } else {
    params.status = 'assigned'
  }
  return params
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/devices', { params: buildParams() })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function resetAndLoad() {
  page.value = 1
  void load()
}

function onPage(e: any) {
  page.value = e.page + 1
  void load()
}

function goDevices(query = '') {
  void router.push(query ? { path: '/devices', query: { search: query } } : '/devices')
}

function deviceTypeLabel(value: string) {
  return deviceTypeOptions.find((item) => item.value === value)?.label ?? value
}

function statusLabel(value: string) {
  return statusLabels[value] ?? value
}

function statusSeverity(value: string): any {
  return statusSeverityMap[value] ?? 'info'
}

function groupHeader(item: DeviceRecord) {
  const option = currentGroupOption.value
  if (!option) return ''
  return `${option.label}: ${groupValue(item as unknown as Record<string, unknown>, option, groupFormatters)}`
}

function groupCount(item: DeviceRecord) {
  return countGroup(displayItems.value as unknown as Record<string, unknown>[], item as unknown as Record<string, unknown>, currentGroupOption.value, groupFormatters)
}

watch(reportMode, () => {
  search.value = ''
  filterType.value = null
  filterFactory.value = null
  filterStatus.value = null
  groupField.value = null
  resetAndLoad()
})

onMounted(load)
</script>

<style scoped>
.page-subtitle {
  margin-top: 0.25rem;
  color: #64748b;
  font-size: 0.9rem;
}

.summary-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 0.5rem;
  padding: 0 0.75rem 0.75rem;
}

.summary-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  min-height: 56px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
  padding: 0.75rem 0.9rem;
}

.summary-item span {
  color: #64748b;
  font-size: 0.84rem;
  font-weight: 700;
}

.summary-item strong {
  color: #0f172a;
  font-size: 1.25rem;
}

.identity-cell,
.stack-cell {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.identity-cell strong,
.stack-cell strong {
  color: #0f172a;
  font-size: 0.9rem;
}

.identity-cell span,
.stack-cell small,
.spec-list span {
  color: #64748b;
  font-size: 0.78rem;
}

.spec-list {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.2rem 0.6rem;
}

.spec-list span,
.identity-cell span {
  overflow-wrap: anywhere;
}

.group-header {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.45rem 0.25rem;
  color: #0f172a;
}

.group-header span {
  font-weight: 700;
}

.group-header strong,
.group-footer {
  color: #64748b;
  font-size: 0.82rem;
}

.group-footer {
  padding: 0.85rem 0.25rem 0;
  text-align: right;
}

@media (max-width: 900px) {
  .summary-strip {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 620px) {
  .summary-strip {
    grid-template-columns: 1fr;
  }
}
</style>
