<template>
  <div>
    <div class="page-header">
      <div>
        <h1>컴퓨터 설정</h1>
        <p class="page-subtitle">사번 기준으로 Windows 보안 설정 적용 상태를 확인합니다.</p>
      </div>
      <Button label="설정 등록" icon="pi pi-plus" @click="openCreate" />
    </div>

    <div class="filters-row">
      <IconField>
        <InputIcon class="pi pi-search" />
        <InputText v-model="search" placeholder="사용자, 사번, 시리얼 검색" @keyup.enter="load" />
      </IconField>
      <Select v-model="groupField" :options="groupOptions" optionLabel="label" optionValue="value" placeholder="그룹핑" showClear @change="onGroupChange" />
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
        <Column header="사용자" style="min-width:145px">
          <template #body="{ data }">
            <div class="stack-cell">
              <strong>{{ data.user_name || '-' }}</strong>
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
        <Column header="시리얼" field="serial_number" sortable />
        <Column header="스마트 앱 컨트롤"><template #body="{ data }"><span :class="data.smart_app_control ? 'status-dot on' : 'status-dot'" /></template></Column>
        <Column header="평판기반 보호"><template #body="{ data }"><span :class="data.reputation_based_protection ? 'status-dot on' : 'status-dot'" /></template></Column>
        <Column header="Exploit Protection"><template #body="{ data }"><span :class="data.exploit_protection ? 'status-dot on' : 'status-dot'" /></template></Column>
        <Column header="장치보안 코어 격리"><template #body="{ data }"><span :class="data.core_isolation ? 'status-dot on' : 'status-dot'" /></template></Column>
        <Column header="상태" style="width:90px">
          <template #body="{ data }"><Tag :value="`${enabledCount(data)}/4`" :severity="enabledCount(data) >= 4 ? 'success' : 'danger'" /></template>
        </Column>
        <Column style="width:90px">
          <template #body="{ data }">
            <Button icon="pi pi-pencil" text rounded size="small" @click="openEdit(data)" />
            <Button icon="pi pi-trash" text rounded size="small" severity="danger" @click="remove(data.id)" />
          </template>
        </Column>
      </DataTable>
      <Paginator v-if="!groupField" :rows="size" :totalRecords="total" :first="(page - 1) * size" @page="onPage" />
      <div v-else class="group-footer">그룹핑 보기: {{ displayItems.length }}건 표시</div>
    </div>

    <Dialog v-model:visible="showDialog" :header="editId !== null ? '컴퓨터 설정 수정' : '컴퓨터 설정 등록'" :modal="true" style="width:720px">
      <div class="form-grid">
        <div class="field full">
          <label>디바이스 *</label>
          <Select v-model="form.device_id" :options="deviceOptions" optionLabel="label" optionValue="value" filter fluid />
        </div>
        <div class="check-grid full">
          <label v-for="field in settingFields" :key="field.key" class="check-field">
            <Checkbox v-model="form[field.key]" binary />
            <span>{{ field.label }}</span>
          </label>
        </div>
        <div class="field full"><label>비고</label><Textarea v-model="form.notes" rows="2" fluid /></div>
      </div>
      <template #footer>
        <Button label="취소" severity="secondary" @click="showDialog = false" />
        <Button :label="editId !== null ? '수정' : '저장'" @click="save" />
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import InputText from 'primevue/inputtext'
import Paginator from 'primevue/paginator'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import Textarea from 'primevue/textarea'
import { useToast } from 'primevue/usetoast'
import api from '@/api'
import type { ComputerSettingRecord, DeviceRecord } from '@/types'
import { countGroup, groupValue, sortByGroup, type GroupOption } from '@/utils/grouping'

const toast = useToast()
const items = ref<ComputerSettingRecord[]>([])
const devices = ref<DeviceRecord[]>([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)
const search = ref('')
const groupField = ref<string | null>(null)
const showDialog = ref(false)
const editId = ref<number | null>(null)

const settingFields = [
  { key: 'smart_app_control', label: '스마트 앱 컨트롤' },
  { key: 'reputation_based_protection', label: '평판기반 보호' },
  { key: 'exploit_protection', label: 'Exploit Protection' },
  { key: 'core_isolation', label: '장치보안 코어 격리' },
]
const groupOptions: GroupOption[] = [
  { label: '사용자 기준', value: 'user_name' },
  { label: '사번 기준', value: 'employee_number' },
  { label: '부서 기준', value: 'department' },
  { label: '위치 기준', value: 'location' },
  { label: '공장 기준', value: 'factory' },
  { label: '종류 기준', value: 'device_type', type: 'deviceType' },
  { label: '시리얼 기준', value: 'serial_number' },
  { label: '스마트 앱 컨트롤 기준', value: 'smart_app_control', type: 'boolean' },
  { label: '평판기반 보호 기준', value: 'reputation_based_protection', type: 'boolean' },
  { label: 'Exploit Protection 기준', value: 'exploit_protection', type: 'boolean' },
  { label: '장치보안 코어 격리 기준', value: 'core_isolation', type: 'boolean' },
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

const emptyForm = () => ({
  device_id: null,
  smart_app_control: false,
  reputation_based_protection: false,
  exploit_protection: false,
  core_isolation: false,
  notes: '',
})

const form = ref<any>(emptyForm())
const currentGroupOption = computed(() => groupOptions.find((item) => item.value === groupField.value) ?? null)
const groupFormatters = { deviceType: deviceTypeLabel }
const displayItems = computed(() => sortByGroup(items.value as unknown as Record<string, unknown>[], currentGroupOption.value, groupFormatters) as unknown as ComputerSettingRecord[])
const deviceOptions = computed(() =>
  devices.value.map((device) => ({
    label: `${device.user_name || '미지정'} / ${device.employee_number || '-'} / ${device.department || '-'} / ${device.serial_number}`,
    value: device.id,
  })),
)

async function loadDevices() {
  const { data } = await api.get('/devices', { params: { page: 1, size: 100 } })
  devices.value = data.items
}

async function load() {
  loading.value = true
  try {
    const params: any = { page: groupField.value ? 1 : page.value, size: groupField.value ? 1000 : size.value }
    if (search.value) params.search = search.value
    const { data } = await api.get('/computer-settings', { params })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function onGroupChange() {
  page.value = 1
  load()
}

function onPage(e: any) {
  page.value = e.page + 1
  load()
}

function openCreate() {
  editId.value = null
  form.value = emptyForm()
  showDialog.value = true
}

function openEdit(item: ComputerSettingRecord) {
  editId.value = item.id
  form.value = { ...item }
  showDialog.value = true
}

async function save() {
  try {
    if (editId.value !== null) await api.put(`/computer-settings/${editId.value}`, form.value)
    else await api.post('/computer-settings', form.value)
    toast.add({ severity: 'success', summary: '저장 완료', life: 3000 })
    showDialog.value = false
    load()
  } catch (err: any) {
    toast.add({ severity: 'error', summary: '오류', detail: err.response?.data?.detail ?? '저장 실패', life: 5000 })
  }
}

async function remove(id: number) {
  await api.delete(`/computer-settings/${id}`)
  load()
}

function enabledCount(item: ComputerSettingRecord) {
  return settingFields.filter((field) => Boolean((item as any)[field.key])).length
}

function deviceTypeLabel(value: string) {
  return deviceTypeLabels[value] ?? value
}

function groupHeader(item: ComputerSettingRecord) {
  const option = currentGroupOption.value
  if (!option) return ''
  return `${option.label}: ${groupValue(item as unknown as Record<string, unknown>, option, groupFormatters)}`
}

function groupCount(item: ComputerSettingRecord) {
  return countGroup(displayItems.value as unknown as Record<string, unknown>[], item as unknown as Record<string, unknown>, currentGroupOption.value, groupFormatters)
}

onMounted(() => {
  loadDevices()
  load()
})
</script>

<style scoped>
.page-subtitle{margin-top:0.25rem;color:#64748b;font-size:0.9rem}
.identity-cell{display:flex;flex-direction:column;gap:0.2rem}
.identity-cell strong{font-size:0.9rem;color:#0f172a}
.identity-cell span{font-size:0.78rem;color:#64748b}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
.field{display:flex;flex-direction:column;gap:0.25rem}
.field.full,.check-grid.full{grid-column:1/-1}
.field label{font-size:0.85rem;font-weight:600;color:#475569}
.check-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:0.75rem}
.check-field{display:flex;align-items:center;gap:0.5rem;padding:0.65rem;border:1px solid #e2e8f0;border-radius:8px;font-size:0.9rem}
.status-dot{width:10px;height:10px;border-radius:999px;background:#cbd5e1;display:inline-block}
.status-dot.on{background:#22c55e}
.group-header{width:100%;display:flex;align-items:center;justify-content:space-between;padding:0.45rem 0.25rem;color:#0f172a}
.group-header span{font-weight:700}
.group-header strong,.group-footer{color:#64748b;font-size:0.82rem}
.group-footer{padding:0.85rem 0.25rem 0;text-align:right}
@media (max-width:800px){.form-grid,.check-grid{grid-template-columns:1fr}}
</style>
