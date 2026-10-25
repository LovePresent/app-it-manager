<template>
  <Dialog :visible="visible" @update:visible="emit('update:visible', $event)" :header="`디바이스 로그 · ${device?.serial_number || ''}`" modal :style="{ width: '1050px' }" :breakpoints="{ '1100px': '95vw' }">
    <div class="device-logs-toolbar"><p>디바이스 정보, 에이전트 관측 변화, IP 점검과 관리자 작업을 시간순으로 확인합니다. 표시 시간은 한국 표준시입니다.</p><Button label="새로고침" icon="pi pi-refresh" text :loading="loading" @click="load" /></div>
    <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
    <DataTable :value="entries" :loading="loading" dataKey="id" size="small" stripedRows scrollable class="device-logs-table">
      <Column header="시간 / 작업자" style="min-width:180px"><template #body="{ data }"><div class="device-log-actor"><strong>{{ formatAgentDate(data.timestamp) }}</strong><span>{{ data.user_name || (data.user_id ? `사용자 #${data.user_id}` : '에이전트 / 시스템') }}</span><small v-if="data.ip_address">연결 IP {{ data.ip_address }}</small></div></template></Column>
      <Column header="기록" style="min-width:160px"><template #body="{ data }"><div class="device-log-actor"><Tag :value="logActionLabel(data.action)" :severity="data.action === 'ip_mismatch_detected' ? 'warn' : data.action === 'uninstall_complete' ? 'danger' : 'secondary'" /><small>{{ entityLabel(data.entity_type) }}</small></div></template></Column>
      <Column header="변경 전후 / 상세" style="min-width:390px"><template #body="{ data }">
        <details v-if="data.changes && Object.keys(data.changes).length" class="device-log-details">
          <summary>{{ summary(data.changes) }}</summary>
          <dl><div v-for="(value, key) in data.changes" :key="key" class="device-log-change"><dt>{{ fieldLabel(String(key)) }}</dt><dd v-if="isChange(value)"><div class="device-log-before"><b>변경 전</b><pre>{{ display(value.old) }}</pre></div><div class="device-log-after"><b>변경 후</b><pre>{{ display(value.new) }}</pre></div></dd><dd v-else><pre>{{ display(value) }}</pre></dd></div></dl>
        </details><span v-else>추가 정보 없음</span>
      </template></Column>
      <template #empty>{{ error ? '로그를 불러오지 못했습니다. 새로고침으로 다시 확인해 주세요.' : '기록된 디바이스 로그가 없습니다.' }}</template>
    </DataTable>
    <Paginator :rows="size" :totalRecords="total" :first="(page - 1) * size" :rowsPerPageOptions="[20, 50, 100]" @page="onPage" />
    <template #footer><span class="device-log-count">총 {{ total }}건</span><Button label="닫기" severity="secondary" @click="emit('update:visible', false)" /></template>
  </Dialog>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import Paginator from 'primevue/paginator'
import Tag from 'primevue/tag'
import api from '@/api'
import type { DeviceRecord, PaginatedResponse } from '@/types'
import { agentErrorMessage, formatAgentDate } from './deviceAgentState'
import { logActionLabel } from './deviceLogLabels'

interface DeviceLogEntry { id: number; action: string; entity_type: string; user_id: number | null; user_name: string | null; ip_address: string | null; timestamp: string; changes: Record<string, unknown> | null }
const props = defineProps<{ visible: boolean; device: DeviceRecord | null }>()
const emit = defineEmits<{ 'update:visible': [visible: boolean] }>()
const entries = ref<DeviceLogEntry[]>([])
const page = ref(1)
const size = ref(20)
const total = ref(0)
const loading = ref(false)
const error = ref('')
let sequence = 0

function isChange(value: unknown): value is { old: unknown; new: unknown } { return value !== null && typeof value === 'object' && Object.prototype.hasOwnProperty.call(value, 'old') && Object.prototype.hasOwnProperty.call(value, 'new') }
function entityLabel(value: string) { return ({ device: '디바이스 정보', device_agent: 'PC 에이전트', device_command: '전원 요청', computer_setting: '보안 설정', device_license: '라이센스' } as Record<string, string>)[value] || value }
function fieldLabel(value: string) {
  const labels: Record<string, string> = { agent_id: '에이전트 번호', command_id: '요청 번호', ticket_id: '설치 파일 번호', format: '설치 형식', expires_at: '유효 기한', id: '식별값', name: '어댑터 이름', macAddress: 'MAC 주소', ipv4: 'IPv4', ipv6: 'IPv6', address: 'IP 주소', netmask: '서브넷 마스크', physical: '물리 어댑터' }
  if (labels[value]) return labels[value]
  return ({ hostname: 'PC 이름', os_version: '운영 체제', agent_version: '에이전트 버전', boot_time: '부팅 시간', capabilities: '지원 기능', observed_ip: '서버에서 본 연결 IP', connection_state: '연결 상태', installation_state: '설치 상태', service_state: '서비스 상태', network_adapters: '네트워크 어댑터', baseline_ipv4: '최초 IP 기준', expected_ipv4: '기준 IP', observed_ipv4: '확인된 IP', source: '비교 기준 출처', evidence: '확인 근거', review: '점검 기록', incident_id: '점검 번호', state: '상태', note: '점검 메모', notes: '메모', ip_address: '등록 IP', mac_address: '등록 MAC', serial_number: '시리얼', user_name: '사용자', employee_number: '사번', device_type: '장비 종류', department: '부서', location: '위치', factory: '공장', status: '상태', before: '변경 전', after: '변경 후', reviewed_by: '점검자', reviewed_at: '점검 시간', type: '요청 종류', detail: '결과', device_id: '디바이스 번호', previous_device_id: '이전 디바이스 번호', cpu: 'CPU', memory: '메모리', storage: '저장 장치', gpu: '그래픽', hardware_key: '하드웨어 식별값', registration_mode: '등록 방식', installed: '설치됨', uninstalled_at: '제거 완료 시각' } as Record<string, string>)[value] || value
}
function display(value: unknown): string {
  if (value === null || value === undefined || value === '') return '없음'
  if (typeof value === 'boolean') return value ? '예' : '아니오'
  if (Array.isArray(value)) return value.length ? value.map(display).join('\n') : '없음'
  if (typeof value === 'object') return Object.entries(value).map(([key, item]) => `${fieldLabel(key)}: ${display(item)}`).join('\n')
  const text = String(value)
  const capabilities: Record<string, string> = { 'power-control-v1': '전원 제어', 'wol-relay-v1': 'WOL 중계', 'network-info-v1': '네트워크 정보 수집', 'network-inventory-v1': '네트워크 정보 수집', exe: 'EXE 설치 파일' }
  if (capabilities[text]) return capabilities[text]
  return ({ online: '켜져 있음', offline: '연결 끊김', pending: '대기', revoked: '연결 해제', installed: '설치됨', uninstalled: '프로그램 삭제됨', worker_missing: '프로그램 파일 없음', worker_stopped: '프로세스 중지', running: '실행 중', inventory: '등록 IP', first_seen: '최초 확인 IP', unconfigured: '미설정', agent_snapshot: '에이전트 관측', open: '확인 필요', reviewing: '점검 중', resolved: '처리 완료', normal: '일치', mismatch: '불일치', unknown: '미확인', restart: '재시작', shutdown: '종료', wake: '켜기 (WOL)' } as Record<string, string>)[text] || text
}
function summary(changes: Record<string, unknown>): string {
  const fields = Object.keys(changes)
  return `${fields.slice(0, 4).map(fieldLabel).join(' · ')}${fields.length > 4 ? ` 외 ${fields.length - 4}개` : ''} — 상세 보기`
}
async function load() {
  if (!props.visible || !props.device) return
  const request = ++sequence
  const id = props.device.id
  loading.value = true; error.value = ''
  try {
    const { data } = await api.get<PaginatedResponse<DeviceLogEntry>>(`/devices/${id}/logs`, { params: { page: page.value, size: size.value }, skipGlobalLoading: true, timeout: 10000 })
    if (request !== sequence || !props.visible || props.device?.id !== id) return
    entries.value = data.items; total.value = data.total
  } catch (reason) { if (request === sequence) { entries.value = []; error.value = await agentErrorMessage(reason) } }
  finally { if (request === sequence) loading.value = false }
}
function onPage(event: { page: number; rows: number }) { page.value = event.page + 1; size.value = event.rows; void load() }
watch(() => [props.visible, props.device?.id], () => { sequence += 1; entries.value = []; total.value = 0; page.value = 1; error.value = ''; loading.value = false; if (props.visible) void load() }, { immediate: true })
onBeforeUnmount(() => { sequence += 1 })
</script>

<style scoped>
.device-logs-toolbar{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:14px}.device-logs-toolbar p{font-size:.78rem;line-height:1.8;color:#64748b;margin:0}.device-logs-toolbar :deep(.p-button){flex-shrink:0}.device-log-actor{display:grid;gap:6px;font-size:.76rem}.device-log-actor strong{font-weight:500}.device-log-actor small{color:#64748b}.device-log-details summary{cursor:pointer;line-height:1.8;color:#334155;font-size:.77rem}.device-log-details dl{margin:10px 0 0;display:grid;gap:12px}.device-log-change dt{font-weight:600;font-size:.76rem;margin-bottom:5px;color:#334155}.device-log-change dd{margin:0;display:grid;gap:5px}.device-log-change pre{font-family:inherit;font-size:.73rem;line-height:1.8;white-space:pre-wrap;overflow-wrap:anywhere;margin:0}.device-log-before,.device-log-after{display:grid;grid-template-columns:58px minmax(0,1fr);gap:8px;padding:8px;border-radius:5px;background:#f8fafc}.device-log-before b,.device-log-after b{font-size:.7rem;color:#64748b}.device-log-after{background:#eff6ff}.device-log-count{font-size:.78rem;color:#64748b;margin-right:auto}.device-logs-table{font-size:.76rem}
</style>
