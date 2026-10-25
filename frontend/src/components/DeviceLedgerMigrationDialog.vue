<template>
  <Dialog :visible="visible" @update:visible="updateVisible" header="장비 대장 가져오기" modal :closable="!busy" :closeOnEscape="!busy" :style="{ width: '800px' }" :breakpoints="{ '850px': '95vw' }">
    <div class="ledger-migration" aria-live="polite">
      <p class="ledger-intro">내보낸 JSON 파일을 선택하면 운영 장비 대장과 비교합니다. 미리보기 결과를 확인한 후 가져오기를 적용할 수 있습니다.</p>
      <Message severity="info" :closable="false">기존 장비 정보는 덮어쓰지 않습니다. 충돌하거나 연결을 확인해야 하는 항목은 보류 또는 확인 필요 항목으로 표시됩니다.</Message>
      <div class="ledger-file">
        <label for="device-ledger-file">장비 대장 JSON 파일</label>
        <input id="device-ledger-file" ref="fileInput" type="file" accept=".json,application/json" :disabled="busy || !isAdmin" @change="selectFile" aria-describedby="device-ledger-file-hint" />
        <small id="device-ledger-file-hint">최대 8MiB · 선택한 파일은 로그인한 서버로 전송됩니다. 브라우저 저장소에 보관하지 않습니다.</small>
        <span v-if="selectedFile" class="ledger-file-name">{{ selectedFile.name }} · {{ formatSize(selectedFile.size) }}</span>
      </div>
      <Message v-if="errorMessage" severity="error" :closable="false">{{ errorMessage }}</Message>
      <div class="ledger-actions"><Button :label="phase === 'preview' ? '운영 장비 대장과 비교 중…' : preview ? '미리보기 다시 확인' : '미리보기'" icon="pi pi-search" :loading="phase === 'preview'" :disabled="busy || !selectedFile || !isAdmin" @click="loadPreview" /></div>

      <section v-if="preview" class="ledger-preview" aria-labelledby="ledger-preview-title">
        <h3 id="ledger-preview-title">{{ receipt ? '가져오기 결과' : '가져오기 전 확인' }}</h3>
        <Message v-if="receipt" severity="success" :closable="false">
          <strong>{{ preview.already_applied ? '이미 반영된 파일입니다. 중복으로 가져오지 않았습니다.' : '가져오기가 반영되었습니다.' }}</strong>
          <div>서버 처리 시각: {{ formatAgentDate(receipt.applied_at) }}</div>
        </Message>
        <Message v-else-if="!preview.can_apply" severity="warn" :closable="false">현재 파일은 가져오기를 적용할 수 없습니다. 아래 확인 사항을 검토해 주세요.</Message>
        <div v-if="!receipt" class="ledger-counts">
          <div><span>새로 추가</span><strong>{{ preview.summary.create }}</strong></div>
          <div><span>기존 항목 연결</span><strong>{{ preview.summary.reuse }}</strong></div>
          <div><span>보류 / 제외</span><strong>{{ preview.summary.skip }}</strong></div>
          <div><span>확인 필요</span><strong>{{ preview.summary.manual_review }}</strong></div>
        </div>
        <div v-else class="ledger-counts">
          <div><span>추가됨</span><strong>{{ total(receipt.created_counts) }}</strong></div>
          <div><span>기존 항목 연결</span><strong>{{ total(receipt.reused_counts) }}</strong></div>
          <div><span>보류 / 제외</span><strong>{{ total(receipt.skipped_counts) }}</strong></div>
        </div>
        <p class="ledger-help">건수에는 디바이스와 연관 이력이 포함됩니다. 항목별 내역을 함께 확인해 주세요.</p>
        <DataTable :value="tableRows" size="small" dataKey="table" stripedRows scrollable>
          <Column field="label" header="항목" /><Column field="create" :header="receipt ? '추가됨' : '새로 추가'" /><Column field="reuse" header="기존 항목 연결" /><Column field="skip" header="보류 / 제외" />
        </DataTable>
        <Message v-if="excludedRows.length" severity="warn" :closable="false">
          <strong>가져오기에서 제외하고 원본에 남긴 이력</strong>
          <div v-for="item in excludedRows" :key="item.key">{{ item.label }}: {{ item.count }}건</div>
          <div>현재 장비와의 연결을 확인할 수 없어 가져오지 않습니다. 원본 자료는 그대로 보존됩니다.</div>
        </Message>
        <p class="ledger-help">설치된 에이전트의 인증 정보와 원격 명령은 가져오지 않습니다.</p>
        <div v-if="preview.issues.length" class="ledger-issues">
          <h4>확인 사항 {{ preview.issues.length }}건</h4>
          <p v-if="receipt" class="ledger-help">반영이 끝나도 아래 확인 사항은 남을 수 있습니다. 보류 항목은 자동으로 덮어쓰거나 다시 추가하지 않습니다.</p>
          <ul><li v-for="(issue, index) in visibleIssues" :key="index"><strong>{{ tableLabel(issue.table) }}{{ issue.source_id === null ? '' : ` · 원본 ${issue.source_id}` }}</strong><span>{{ issue.message }}</span><small>{{ issue.code }}</small></li></ul>
          <p v-if="preview.issues.length > visibleIssues.length" class="ledger-help">{{ visibleIssues.length }}건을 표시했습니다. 전체 확인 사항은 {{ preview.issues.length }}건입니다.</p>
          <Button v-if="preview.issues.length > 50" :label="showAllIssues ? '50건만 보기' : '확인 사항 전체 보기'" text size="small" @click="showAllIssues = !showAllIssues" />
        </div>
        <details class="ledger-verification"><summary>파일 및 확인 정보</summary><dl><dt>가져오기 번호</dt><dd>{{ preview.batch_id }}</dd><dt>파일 검증값</dt><dd>{{ preview.payload_sha256 }}</dd><template v-if="!receipt"><dt>미리보기 확인값</dt><dd>{{ preview.preview_fingerprint }}</dd></template></dl></details>
        <div v-if="!receipt && preview.can_apply" class="ledger-confirmation">
          <p>현재 미리보기를 확인한 파일을 운영 장비 대장에 반영합니다. 서버의 관련 정보가 바뀌면 미리보기를 다시 확인해야 합니다.</p>
          <Button label="확인 후 가져오기 적용" icon="pi pi-check" :loading="phase === 'apply'" :disabled="!canApply" @click="applyMigration" />
        </div>
      </section>
    </div>
    <template #footer><Button label="닫기" severity="secondary" :disabled="busy" @click="updateVisible(false)" /></template>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import api from '@/api'
import { useAuthStore } from '@/stores/auth'
import { formatAgentDate } from './deviceAgentState'

type Counts = Record<string, number>
interface MigrationReceipt { batch_id: string; payload_sha256: string; applied_at: string; created_counts: Counts; reused_counts: Counts; skipped_counts: Counts }
interface MigrationPreview {
  batch_id: string
  payload_sha256: string
  preview_fingerprint: string
  can_apply: boolean
  already_applied: boolean
  summary: { create: number; reuse: number; skip: number; manual_review: number }
  tables: Record<string, { create: number; reuse: number; skip: number }>
  issues: { code: string; table: string; source_id: number | string | null; message: string }[]
  receipt: MigrationReceipt | null
  excluded?: Record<string, string | number>
  applied?: boolean
}

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ 'update:visible': [visible: boolean]; applied: [] }>()
const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.role === 'admin')
const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = shallowRef<File | null>(null)
const previewFile = shallowRef<File | null>(null)
const preview = shallowRef<MigrationPreview | null>(null)
const phase = ref<'preview' | 'apply' | null>(null)
const busy = computed(() => phase.value !== null)
const errorMessage = ref('')
const showAllIssues = ref(false)
const receipt = computed(() => preview.value?.receipt || null)
const visibleIssues = computed(() => showAllIssues.value ? preview.value?.issues || [] : (preview.value?.issues || []).slice(0, 50))
const excludedRows = computed(() => [
  { key: 'unmatched_or_previous_device_audits', label: '대상을 확인할 수 없거나 이전 장비에 속한 이력' },
  { key: 'unproven_child_audits', label: '장비 연결을 확인할 수 없는 하위 자료 이력' },
].map(item => ({ ...item, count: preview.value?.excluded?.[item.key] })).filter((item): item is { key: string; label: string; count: number } => typeof item.count === 'number' && Number.isSafeInteger(item.count) && item.count > 0))
const canApply = computed(() => isAdmin.value && props.visible && !busy.value && !!preview.value?.can_apply && !preview.value.already_applied && !receipt.value && selectedFile.value === previewFile.value)
const tableNames: Record<string, string> = { devices: '디바이스', device_licenses: '장비 라이선스', computer_settings: 'PC 설정', device_usage_history: '장비 사용 이력', ip_change_history: 'IP 변경 이력', audit_logs: '변경 기록', license_assignments: '라이선스 할당', purchase_allocations: '구매 배분', software_licenses: '소프트웨어 라이선스', assets: '자산', asset_categories: '자산 분류', vendors: '거래처', purchases: '구매 내역', user_refs: '기존 사용자 연결' }
const tableRows = computed(() => {
  const current = preview.value
  if (!current) return []
  const result = receipt.value
  const tables = result ? new Set([...Object.keys(result.created_counts), ...Object.keys(result.reused_counts), ...Object.keys(result.skipped_counts)]) : new Set(Object.keys(current.tables))
  return [...tables].map(table => ({ table, label: tableLabel(table), ...(result ? { create: result.created_counts[table] || 0, reuse: result.reused_counts[table] || 0, skip: result.skipped_counts[table] || 0 } : current.tables[table]) }))
})
let sequence = 0
let controller: AbortController | null = null
let disposed = false

function tableLabel(table: string) { return tableNames[table] || table }
function total(counts: Counts) { return Object.values(counts).reduce((sum, count) => sum + count, 0) }
function formatSize(bytes: number) { return bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KiB` : `${(bytes / (1024 * 1024)).toFixed(2)} MiB` }
function clearPreview() { preview.value = null; previewFile.value = null; showAllIssues.value = false }
function reset() { ++sequence; controller?.abort(); controller = null; phase.value = null; clearPreview(); selectedFile.value = null; errorMessage.value = ''; if (fileInput.value) fileInput.value.value = '' }
function updateVisible(visible: boolean) { if (!busy.value) emit('update:visible', visible) }
function selectFile(event: Event) {
  ++sequence; controller?.abort(); controller = null; phase.value = null; clearPreview(); errorMessage.value = ''; selectedFile.value = null
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.json')) { errorMessage.value = '내보낸 JSON 파일을 선택해 주세요.'; return }
  if (!file.size || file.size > 8 * 1024 * 1024) { errorMessage.value = '파일은 비어 있지 않은 8MiB 이하의 JSON이어야 합니다.'; return }
  selectedFile.value = file
}
function validCounts(value: unknown): value is Counts { return !!value && typeof value === 'object' && !Array.isArray(value) && Object.values(value).every(item => Number.isSafeInteger(item) && Number(item) >= 0) }
function validPreview(value: MigrationPreview): boolean {
  return !!value && typeof value.batch_id === 'string' && /^[a-f0-9]{64}$/.test(value.payload_sha256) && /^[a-f0-9]{64}$/.test(value.preview_fingerprint) && typeof value.can_apply === 'boolean' && typeof value.already_applied === 'boolean' && validCounts(value.summary) && ['create', 'reuse', 'skip', 'manual_review'].every(key => key in value.summary) && !!value.tables && Object.values(value.tables).every(counts => validCounts(counts) && ['create', 'reuse', 'skip'].every(key => key in counts)) && Array.isArray(value.issues) && value.issues.every(issue => typeof issue.code === 'string' && typeof issue.table === 'string' && typeof issue.message === 'string') && (!value.receipt || (value.receipt.batch_id === value.batch_id && value.receipt.payload_sha256 === value.payload_sha256 && Number.isFinite(Date.parse(value.receipt.applied_at)) && validCounts(value.receipt.created_counts) && validCounts(value.receipt.reused_counts) && validCounts(value.receipt.skipped_counts))) && (!value.already_applied || !!value.receipt)
}
function failureMessage(reason: unknown, applying: boolean) {
  const status = (reason as { response?: { status?: number } })?.response?.status
  if (status === 401) return '로그인 시간이 만료되었습니다. 다시 로그인한 뒤 같은 파일의 미리보기를 확인해 주세요.'
  if (status === 403) return '장비 대장 가져오기는 관리자만 사용할 수 있습니다.'
  if (status === 409) return '운영 장비 대장 또는 파일 확인 정보가 바뀌었습니다. 미리보기를 다시 확인한 뒤 적용해 주세요.'
  if (status === 413) return '파일이 서버의 허용 크기를 초과했습니다. 8MiB 이하의 파일을 선택해 주세요.'
  if (status === 422) return '장비 대장 형식이나 연결 정보를 확인할 수 없습니다. 올바르게 내보낸 파일인지 확인해 주세요.'
  return applying ? '가져오기 결과를 확인하지 못했습니다. 처리됐을 수 있으므로 같은 파일로 미리보기를 다시 확인해 주세요. 서버 처리 기록을 확인한 뒤 중복 없이 진행합니다.' : '서버에서 미리보기를 확인하지 못했습니다. 연결 상태를 확인하고 다시 시도해 주세요.'
}
function makeForm(file: File, fingerprint?: string) { const form = new FormData(); form.append('file', file); if (fingerprint) form.append('preview_fingerprint', fingerprint); return form }
async function loadPreview() {
  const file = selectedFile.value
  if (!file || busy.value || !isAdmin.value || !props.visible) return
  const request = ++sequence
  clearPreview(); errorMessage.value = ''; phase.value = 'preview'; controller = new AbortController()
  try {
    const { data } = await api.post<MigrationPreview>('/devices/migration/preview', makeForm(file), { headers: { 'Content-Type': undefined }, timeout: 60000, signal: controller.signal })
    if (disposed || request !== sequence || selectedFile.value !== file || !isAdmin.value || !props.visible) return
    if (!validPreview(data)) { errorMessage.value = '미리보기 응답을 확인할 수 없습니다. 다시 확인해 주세요.'; return }
    preview.value = data; previewFile.value = file
  } catch (reason) { if (!disposed && request === sequence) errorMessage.value = failureMessage(reason, false) }
  finally { if (request === sequence) { phase.value = null; controller = null } }
}
async function applyMigration() {
  const file = selectedFile.value
  const confirmed = preview.value
  if (!file || !confirmed || !canApply.value) return
  const request = ++sequence
  errorMessage.value = ''; phase.value = 'apply'; controller = new AbortController()
  try {
    const { data } = await api.post<MigrationPreview>('/devices/migration/apply', makeForm(file, confirmed.preview_fingerprint), { headers: { 'Content-Type': undefined }, timeout: 120000, signal: controller.signal })
    if (disposed || request !== sequence || selectedFile.value !== file || !isAdmin.value || !props.visible) return
    if (!validPreview(data) || data.applied !== true || !data.receipt || data.payload_sha256 !== confirmed.payload_sha256 || data.batch_id !== confirmed.batch_id) {
      clearPreview(); errorMessage.value = '서버 처리 결과를 확인할 수 없습니다. 같은 파일로 미리보기를 다시 확인해 처리 기록을 조회해 주세요.'; return
    }
    preview.value = data; emit('applied')
  } catch (reason) { if (!disposed && request === sequence) { clearPreview(); errorMessage.value = failureMessage(reason, true) } }
  finally { if (request === sequence) { phase.value = null; controller = null } }
}
function beforeUnload(event: BeforeUnloadEvent) { if (busy.value) { event.preventDefault(); event.returnValue = '' } }
watch(() => props.visible, visible => { if (!visible) reset() })
watch(isAdmin, allowed => { if (!allowed) { reset(); emit('update:visible', false) } })
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => { disposed = true; reset(); window.removeEventListener('beforeunload', beforeUnload) })
</script>

<style scoped>
.ledger-migration{display:grid;gap:16px;font-size:.84rem;color:#334155}.ledger-intro,.ledger-confirmation p{margin:0;line-height:1.8}.ledger-file{display:grid;gap:9px;border:1px solid #cbd5e1;border-radius:8px;padding:16px}.ledger-file label,.ledger-preview h3{font-weight:600}.ledger-file input{max-width:100%;font:inherit}.ledger-file small,.ledger-help{font-size:.76rem;color:#64748b;line-height:1.7}.ledger-file-name{overflow-wrap:anywhere}.ledger-actions{display:flex;justify-content:flex-end}.ledger-preview{display:grid;gap:14px;border-top:1px solid #e2e8f0;padding-top:18px}.ledger-preview h3,.ledger-issues h4,.ledger-help{margin:0}.ledger-counts{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.ledger-counts>div{display:grid;gap:6px;border:1px solid #e2e8f0;border-radius:7px;padding:12px}.ledger-counts span{font-size:.75rem;color:#64748b}.ledger-counts strong{font-size:1.3rem;color:#0f172a}.ledger-issues ul{display:grid;gap:10px;padding:0;list-style:none;max-height:300px;overflow:auto}.ledger-issues li{display:grid;gap:4px;background:#fff7ed;border-radius:6px;padding:11px;overflow-wrap:anywhere}.ledger-issues small{color:#64748b}.ledger-verification{font-size:.75rem;overflow-wrap:anywhere}.ledger-verification summary{cursor:pointer;color:#475569}.ledger-verification dt{font-weight:600;margin-top:8px}.ledger-verification dd{margin:4px 0;font-family:monospace}.ledger-confirmation{display:grid;gap:12px;justify-items:end;padding:15px;background:#f8fafc;border-radius:8px}.ledger-confirmation p{justify-self:start;font-size:.8rem}.ledger-preview :deep(.p-datatable){font-size:.78rem}@media(max-width:550px){.ledger-counts{grid-template-columns:repeat(2,1fr)}.ledger-actions :deep(.p-button),.ledger-confirmation :deep(.p-button){width:100%}}
</style>
