<template>
  <div>
    <div class="page-header"><h1>감사 로그</h1></div>
    <div class="filters-row">
      <Select v-model="filterEntity" :options="entityTypes" placeholder="엔티티 유형" showClear @change="load" />
      <Select v-model="filterAction" :options="['create','update','delete','assign','return']" placeholder="액션" showClear @change="load" />
    </div>
    <div class="card">
      <DataTable :value="items" :loading="loading" stripedRows size="small">
        <Column field="created_at" header="시간" sortable style="width:180px" />
        <Column field="user_email" header="사용자" />
        <Column field="action" header="액션"><template #body="{data}"><Tag :value="data.action" :severity="actionSeverity(data.action)" /></template></Column>
        <Column field="entity_type" header="대상" />
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

const items = ref<any[]>([]); const loading = ref(false)
const page = ref(1); const size = ref(30); const total = ref(0)
const filterEntity = ref<string | null>(null); const filterAction = ref<string | null>(null)
const entityTypes = ['asset', 'license', 'subscription', 'ip_address', 'certificate', 'consumable', 'maintenance', 'rack']

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
onMounted(load)
</script>
