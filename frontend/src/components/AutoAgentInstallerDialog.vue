<template>
  <Dialog :visible="visible" @update:visible="updateVisible" header="PC 자동 등록 설치 파일" modal :closable="!preparing" :closeOnEscape="!preparing" :style="{ width: '620px' }" :breakpoints="{ '700px': '94vw' }">
    <div class="auto-installer-content">
      <p class="auto-installer-intro">디바이스를 미리 추가할 필요가 없습니다. Windows PC에서 EXE를 실행하면 기기 정보를 수집해 자산과 에이전트를 함께 연결합니다.</p>
      <ol class="auto-installer-steps">
        <li>설치 파일의 유효 시간을 정해 EXE를 내려받습니다.</li>
        <li>파일을 대상 PC에서 더블클릭하고 Windows 관리자 실행을 승인합니다.</li>
        <li>하드웨어 식별값·BIOS 시리얼로 연결되지 않은 기존 자산을 찾습니다. 일치하는 자산이 없으면 ‘재고’ 상태의 디바이스를 자동 등록합니다.</li>
      </ol>
      <Message severity="info" :closable="false">기존 자산의 상태와 수동 IP 입력값은 유지합니다. PC 이름이나 IP가 같다는 이유로 자산을 병합하지 않습니다. 이미 에이전트가 연결된 PC의 업데이트는 해당 PC 관리창에서 진행하세요.</Message>
      <form @submit.prevent="prepareInstaller">
        <div class="auto-installer-fields">
          <div><label for="auto-agent-expiry">설치 파일 유효 시간</label><InputNumber inputId="auto-agent-expiry" v-model="expiresHours" :min="1" :max="168" :minFractionDigits="0" :maxFractionDigits="0" :useGrouping="false" suffix="시간" showButtons fluid :disabled="preparing || !isAdmin" aria-describedby="auto-agent-expiry-hint" /><small id="auto-agent-expiry-hint">발급 후 1~168시간 · 기본 24시간</small></div>
        </div>
        <p class="auto-installer-scope">등록 PC 수 제한은 없습니다. 유효 기간 동안 관리할 PC에 같은 설치 파일을 사용할 수 있습니다. 승인한 PC에만 전달하고 사용 후 파일을 삭제하세요.</p>
        <Message v-if="errorMessage" severity="error" :closable="false">{{ errorMessage }}</Message>
        <div class="auto-installer-actions"><Button :label="preparing ? 'EXE 설치 파일 준비 중…' : downloadedInstaller ? '새 EXE 설치 파일 발급' : 'EXE 설치 파일 받기'" icon="pi pi-download" type="submit" :loading="preparing" :disabled="preparing || !isAdmin || !validOptions" /></div>
      </form>
      <Message v-if="downloadedInstaller" severity="success" :closable="false">
        <strong>설치 파일이 준비되었습니다.</strong>
        <div class="auto-installer-result">{{ downloadedInstaller.expiresAt ? `유효 기한 ${formatAgentDate(downloadedInstaller.expiresAt)} (한국 표준시)` : `발급 후 ${downloadedInstaller.expiresHours}시간 동안 유효` }}</div>
        <div class="auto-installer-result">{{ downloadedInstaller.filename }}</div>
        <p class="auto-installer-result">다운로드만으로 PC가 등록되지는 않습니다. 대상 PC에서 설치를 완료하면 디바이스 목록과 연결 상태에 반영됩니다.</p>
        <Button label="이 파일 다시 다운로드" icon="pi pi-download" severity="secondary" size="small" :disabled="preparing || !isAdmin" @click="retryDownload" />
      </Message>
    </div>
    <template #footer><Button label="닫기" severity="secondary" :disabled="preparing" @click="updateVisible(false)" /></template>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputNumber from 'primevue/inputnumber'
import Message from 'primevue/message'
import api from '@/api'
import { useAuthStore } from '@/stores/auth'
import { agentErrorMessage, formatAgentDate } from './deviceAgentState'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ 'update:visible': [visible: boolean] }>()
const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.role === 'admin')
const expiresHours = ref<number | null>(24)
const preparing = ref(false)
const errorMessage = ref('')
const downloadedInstaller = shallowRef<{ blob: Blob; filename: string; expiresHours: number; expiresAt: string | null } | null>(null)
const validOptions = computed(() => Number.isInteger(expiresHours.value) && Number(expiresHours.value) >= 1 && Number(expiresHours.value) <= 168)
let disposed = false

function updateVisible(value: boolean) { if (!preparing.value) emit('update:visible', value) }
function saveInstaller() {
  if (!downloadedInstaller.value || !isAdmin.value) return
  const url = URL.createObjectURL(downloadedInstaller.value.blob)
  const link = document.createElement('a')
  link.href = url
  link.download = downloadedInstaller.value.filename
  document.body.append(link)
  try { link.click() } finally { link.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000) }
}
function retryDownload() {
  if (preparing.value) return
  errorMessage.value = ''
  try { saveInstaller() } catch { errorMessage.value = '다운로드하지 못했습니다. 브라우저 다운로드 설정을 확인하고 다시 눌러 주세요.' }
}
async function prepareInstaller() {
  if (!isAdmin.value || preparing.value || !props.visible) return
  if (!validOptions.value) { errorMessage.value = '유효 시간은 1~168시간의 정수로 입력해 주세요.'; return }
  const requestedHours = Number(expiresHours.value)
  preparing.value = true
  errorMessage.value = ''
  try {
    const response = await api.post<Blob>('/agents/auto-installer', { expires_hours: requestedHours }, { responseType: 'blob', timeout: 60000, loadingLabel: 'PC 자동 등록 EXE 설치 파일을 준비하는 중' })
    if (disposed || !isAdmin.value) return
    const disposition = String(response.headers['content-disposition'] || '')
    const extended = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1]
    const basic = /filename="?([^";]+)"?/i.exec(disposition)?.[1]
    let filename = basic || 'ITManager-PC-Auto-Setup.exe'
    if (extended) { try { filename = decodeURIComponent(extended) } catch { /* Keep the ordinary filename. */ } }
    filename = filename.replace(/[\\/:*?"<>|\x00-\x1F]/g, '_')
    if (!filename.toLowerCase().endsWith('.exe')) filename = 'ITManager-PC-Auto-Setup.exe'
    const expiryHeader = String(response.headers['x-enrollment-expires-at'] || '')
    downloadedInstaller.value = { blob: response.data, filename, expiresHours: requestedHours, expiresAt: Number.isFinite(Date.parse(expiryHeader)) ? expiryHeader : null }
    try { saveInstaller() } catch { errorMessage.value = '파일은 준비되었지만 다운로드하지 못했습니다. 아래 다시 다운로드 버튼을 눌러 주세요.' }
  } catch (reason) { if (!disposed) errorMessage.value = await agentErrorMessage(reason) }
  finally { preparing.value = false }
}
function beforeUnload(event: BeforeUnloadEvent) { if (preparing.value) { event.preventDefault(); event.returnValue = '' } }
watch(isAdmin, allowed => { if (!allowed) { downloadedInstaller.value = null; emit('update:visible', false) } })
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => { disposed = true; downloadedInstaller.value = null; window.removeEventListener('beforeunload', beforeUnload) })
</script>

<style scoped>
.auto-installer-content{display:grid;gap:16px}.auto-installer-intro{font-size:.88rem;line-height:1.9;color:#334155;margin:0}.auto-installer-steps{margin:0;padding-left:22px;color:#64748b;font-size:.8rem;line-height:1.9;display:grid;gap:7px}.auto-installer-fields{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:4px 0 12px}.auto-installer-fields label{display:block;font-size:.8rem;color:#475569;font-weight:600;margin-bottom:8px}.auto-installer-fields small{display:block;font-size:.72rem;color:#94a3b8;margin-top:7px}.auto-installer-scope{font-size:.76rem;line-height:1.8;color:#64748b}.auto-installer-actions{display:flex;justify-content:flex-end;margin-top:18px}.auto-installer-result{font-size:.78rem;line-height:1.8;margin:7px 0;overflow-wrap:anywhere}@media(max-width:550px){.auto-installer-fields{grid-template-columns:1fr}.auto-installer-actions :deep(.p-button){width:100%}}
</style>
