<template>
  <div>
    <div class="page-header"><h1>사용로그</h1></div>
    <div class="filters-row">
      <Select v-model="filterEntity" :options="entityTypes" optionLabel="label" optionValue="value" placeholder="대상 유형" showClear @change="resetAndLoad" />
      <Select v-model="filterAction" :options="deviceLogActions" optionLabel="label" optionValue="value" placeholder="기록 종류" showClear @change="resetAndLoad" />
    </div>
    <div class="card">
      <DataTable :value="items" :loading="loading" stripedRows size="small">
        <Column field="timestamp" header="시간 (한국 표준시)" sortable style="width:180px"><template #body="{ data }">{{ formatAgentDate(data.timestamp) }}</template></Column>
        <Column field="user_name" header="작업자"><template #body="{ data }">{{ data.user_name || '에이전트 / 시스템' }}</template></Column>
        <Column field="action" header="기록"><template #body="{data}"><Tag :value="logActionLabel(data.action)" :severity="actionSeverity(data.action)" /></template></Column>
        <Column field="entity_type" header="대상"><template #body="{ data }">{{ entityLabel(data.entity_type) }}</template></Column>
        <Column field="entity_id" header="ID" style="width:60px" />
        <Column header="변경 내용">
          <template #body="{data}">
            <span v-if="data.changes" style="font-size:0.85rem;color:#64748b">{{ summarize(data.changes) }}</span>
            <span v-else>-</span>
          </template>
        </Column>
      </DataTable>
      <Paginator :rows="size" :totalRecords="total" :first="(page-1)*size" @page="onPage" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Paginator from 'primevue/paginator'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import api from '@/api'
import { deviceLogActions, logActionLabel } from '@/components/deviceLogLabels'
import { formatAgentDate } from '@/components/deviceAgentState'

const items = ref<any[]>([]); const loading = ref(false)
const page = ref(1); const size = ref(30); const total = ref(0)
const filterEntity = ref<string | null>(null); const filterAction = ref<string | null>(null)
const entityTypes = ['asset', 'device', 'license', 'device_license', 'computer_setting', 'subscription', 'ip_address', 'certificate', 'consumable', 'maintenance', 'rack', 'project', 'device_agent', 'device_command']
  .map(value => ({ value, label: entityLabel(value) }))
function entityLabel(value: string) { return ({ asset: '자산', device: '디바이스', license: '라이센스', device_license: '디바이스 라이센스', computer_setting: '보안 설정', subscription: '구독', ip_address: 'IP 주소', certificate: '인증서', consumable: '소모품', maintenance: '유지보수', rack: '랙', project: '프로젝트', device_agent: 'PC 에이전트', device_command: 'PC 전원 요청' } as Record<string, string>)[value] || value }

function actionSeverity(a: string): any {
  const m: Record<string, string> = { create: 'success', update: 'info', delete: 'danger', assign: 'warn', return: 'secondary' }
  return m[a] ?? 'info'
}

function summarize(changes: Record<string, any>): string {
  const keys = Object.keys(changes)
  if (keys.length === 0) return '-'
  return keys.slice(0, 3).map(k => `${k}: ${JSON.stringify(changes[k])}`).join(', ') + (keys.length > 3 ? ` (+${keys.length - 3})` : '')
}

async function load() {
  loading.value = true
  try {
    const params: any = { page: page.value, size: size.value }
    if (filterEntity.value) params.entity_type = filterEntity.value
    if (filterAction.value) params.action = filterAction.value
    const { data } = await api.get('/audit-logs', { params })
    items.value = data.items; total.value = data.total
  } finally { loading.value = false }
}

function onPage(e: any) { page.value = e.page + 1; load() }
function resetAndLoad() { page.value = 1; void load() }
onMounted(load)
</script>
