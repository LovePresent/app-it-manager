<template>
  <section class="agent-fleet">
    <div class="agent-fleet-heading"><div><h2>PC 연결 및 점검</h2><p>EXE를 설치하면 새 디바이스를 등록하거나 기존 장비에 연결합니다. 기존 고정 IP와 업무 정보는 유지합니다.</p></div><div v-if="isAdmin" class="agent-fleet-actions"><Button label="장비 대장 가져오기" icon="pi pi-upload" severity="secondary" outlined @click="showMigration = true" /><Button label="PC 자동 등록 설치 파일" icon="pi pi-download" @click="showInstaller = true" /></div></div>
    <Message v-if="error || actionError" severity="warn" :closable="false">{{ actionError || error }}</Message>
    <div class="agent-fleet-tools"><InputText v-model="search" placeholder="연결된 PC 시리얼, 이름, IP 검색" /><small>5초 자동 확인 · {{ formatAgentDate(lastUpdated) }}</small></div>
    <DataTable :value="filtered" dataKey="id" size="small" stripedRows paginator :rows="10" :rowsPerPageOptions="[10, 25, 50]" scrollable>
      <Column field="serial_number" header="디바이스" /><Column field="hostname" header="PC 이름" />
      <Column header="연결"><template #body="{ data }"><DeviceAgentStatus :agent="data" :loaded="loaded" :stale="stale" /></template></Column>
      <Column header="IP 확인"><template #body="{ data }"><DeviceIpStatus :monitor="data.network_monitor" :stale="stale" /><small class="agent-observed-ip">{{ agentIPv4(data).join(', ') || '수집 대기' }}</small></template></Column>
      <Column header="마지막 연결"><template #body="{ data }">{{ formatAgentDate(data.last_seen_at) }}</template></Column>
      <Column header="관리"><template #body="{ data }"><Button label="PC 관리" icon="pi pi-desktop" text size="small" @click="openDevice(data.device_id)" /><Button label="디바이스 로그" icon="pi pi-list" text size="small" @click="openDevice(data.device_id, true)" /></template></Column>
      <template #empty>{{ loaded ? '아직 연결된 PC가 없습니다. 자동 등록 EXE를 설치해 주세요.' : 'PC 연결 정보를 확인하고 있습니다.' }}</template>
    </DataTable>
    <AutoAgentInstallerDialog v-model:visible="showInstaller" />
    <DeviceLedgerMigrationDialog v-if="isAdmin" v-model:visible="showMigration" @applied="onMigrationApplied" />
    <DeviceAgentDialog v-model:visible="showAgent" :device="selectedDevice" @changed="refresh" />
    <DeviceLogsDialog v-model:visible="showLogs" :device="selectedDevice" />
  </section>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import api from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { DeviceRecord } from '@/types'
import AutoAgentInstallerDialog from './AutoAgentInstallerDialog.vue'
import DeviceAgentDialog from './DeviceAgentDialog.vue'
import DeviceAgentStatus from './DeviceAgentStatus.vue'
import DeviceIpStatus from './DeviceIpStatus.vue'
import DeviceLogsDialog from './DeviceLogsDialog.vue'
import DeviceLedgerMigrationDialog from './DeviceLedgerMigrationDialog.vue'
import { agentErrorMessage, agentIPv4, formatAgentDate, useDeviceAgentPresence } from './deviceAgentState'

const emit = defineEmits<{ inventoryChanged: [] }>()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const { agents, loaded, stale, lastUpdated, error, refresh } = useDeviceAgentPresence()
const isAdmin = computed(() => auth.user?.role === 'admin')
const search = ref('')
const showInstaller = ref(false)
const showMigration = ref(false)
const showAgent = ref(false)
const showLogs = ref(false)
const selectedDevice = ref<DeviceRecord | null>(null)
const actionError = ref('')
const filtered = computed(() => {
  const query = search.value.trim().toLowerCase()
  return query ? agents.value.filter(agent => `${agent.serial_number} ${agent.hostname || ''} ${agentIPv4(agent).join(' ')}`.toLowerCase().includes(query)) : agents.value
})
let knownIds: Set<number> | null = null
let requestSequence = 0
function onMigrationApplied() { emit('inventoryChanged'); void refresh() }
watch(isAdmin, allowed => { if (!allowed) showMigration.value = false })
watch(agents, current => {
  const next = new Set(current.map(agent => agent.device_id))
  if (knownIds && [...next].some(id => !knownIds!.has(id))) emit('inventoryChanged')
  knownIds = next
})
async function openDevice(id: number, logs = false) {
  if (!Number.isSafeInteger(id) || id < 1) return
  const request = ++requestSequence
  actionError.value = ''
  try {
    const { data } = await api.get<DeviceRecord>(`/devices/${id}`)
    if (request !== requestSequence) return
    selectedDevice.value = data
    showLogs.value = logs; showAgent.value = !logs
  } catch (reason) { if (request === requestSequence) actionError.value = await agentErrorMessage(reason) }
}
watch(() => [route.query.deviceId, route.query.view], () => {
  if (typeof route.query.deviceId === 'string' && /^[1-9]\d*$/.test(route.query.deviceId)) void openDevice(Number(route.query.deviceId), route.query.view === 'logs')
}, { immediate: true })
watch(() => [showAgent.value, showLogs.value], () => {
  if (!showAgent.value && !showLogs.value && route.query.deviceId) {
    const query = { ...route.query }; delete query.deviceId; delete query.view
    void router.replace({ query })
  }
})
</script>
<style scoped>
.agent-fleet{border:1px solid #e2e8f0;border-radius:10px;padding:18px;margin:18px 0;background:#fff}.agent-fleet-heading{display:flex;align-items:center;justify-content:space-between;gap:15px;flex-wrap:wrap}.agent-fleet-actions{display:flex;gap:8px;flex-wrap:wrap}.agent-fleet h2{font-size:1rem;margin:0 0 8px}.agent-fleet p,.agent-fleet small{font-size:.78rem;line-height:1.7;color:#64748b}.agent-fleet-tools{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:15px 0}.agent-observed-ip{display:block;margin-top:5px}.agent-fleet :deep(.p-datatable){font-size:.78rem}
</style>
