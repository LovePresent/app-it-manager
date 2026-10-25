<template>
  <section class="ip-monitor-section">
    <div class="ip-monitor-heading"><h3>고정 IP 확인 / 점검</h3><DeviceIpStatus :monitor="monitor" :stale="stale" /></div>
    <dl class="ip-monitor-facts">
      <div><dt>사용자가 등록한 기준 IP</dt><dd>{{ device.ip_address || '등록된 기준 IP 없음' }}</dd></div>
      <div><dt>{{ monitor?.source === 'first_seen' ? '최초 확인 IP 기준' : '마지막 비교에 사용한 IP' }}</dt><dd>{{ monitor?.expected_ipv4.join(', ') || '확인 대기' }}</dd></div>
      <div><dt>PC에서 확인된 IP</dt><dd>{{ monitor?.observed_ipv4.join(', ') || '확인 대기' }}</dd></div>
      <div><dt>마지막 IP 확인</dt><dd>{{ formatAgentDate(monitor?.checked_at) }}</dd></div>
    </dl>
    <p class="ip-monitor-help">등록된 IP를 기준으로 실제 PC의 IP 변화를 기록합니다. 등록값과 PC 설정은 자동으로 바꾸지 않습니다. 기준 IP가 없는 새 디바이스는 최초로 확인한 IP를 비교 기준으로 기록합니다.</p>
    <Message v-if="monitor?.reference_error" severity="warn" :closable="false">등록된 기준 IP 형식을 확인해 주세요. 유효한 IPv4 주소를 등록한 후 PC의 다음 연결 신호에서 다시 비교합니다.</Message>
    <Message v-else-if="monitor?.reference_pending" severity="info" :closable="false">기준 IP가 수정되었습니다. PC가 다시 보고하면 새 기준과 비교합니다. 이전 확인 결과로 처리 완료할 수 없습니다.</Message>
    <Message v-else-if="stale || monitor?.stale" severity="warn" :closable="false">현재 IP는 확인되지 않았습니다. 위 주소는 마지막 수집값이며, 남아 있는 점검 건은 유지됩니다.</Message>
    <Message v-else-if="monitor?.status === 'mismatch'" severity="warn" :closable="false">확인된 IP가 기준과 다릅니다. 해당 PC의 네트워크 설정과 변경 사유를 점검해 주세요. 이 기록은 실제로 관측한 변화이며, 변경 시도나 작업자를 확인한 것은 아닙니다.</Message>
    <Message v-else-if="monitor?.status === 'normal'" severity="success" :closable="false">최근 확인된 IP가 기준과 일치합니다. {{ unresolved ? '이전 점검 건의 처리 내용은 관리자가 확인하고 완료해 주세요.' : '현재 확인된 IP 불일치가 없습니다.' }}</Message>
    <div v-if="monitor?.review" class="ip-review-card">
      <div class="ip-monitor-heading"><strong>IP 점검 기록</strong><Tag :value="reviewLabel" :severity="monitor.review.state === 'resolved' ? 'success' : 'warn'" /></div>
      <p v-if="monitor.review.note" class="ip-review-note">{{ monitor.review.note }}</p>
      <p class="ip-monitor-help">{{ monitor.review.reviewed_by || '담당자 확인 대기' }} · {{ formatAgentDate(monitor.review.reviewed_at) }}</p>
      <div v-if="isAdmin && unresolved" class="ip-review-actions">
        <Button v-if="monitor.review.state === 'open'" label="점검 시작" icon="pi pi-search" severity="secondary" :disabled="disabled || stale || submitting" @click="openReview('start')" />
        <Button v-else label="점검 메모 추가" icon="pi pi-pencil" severity="secondary" :disabled="disabled || stale || submitting" @click="openReview('start')" />
        <Button label="처리 완료" icon="pi pi-check" :disabled="!canResolve || disabled || submitting" @click="openReview('resolve')" />
      </div>
      <p v-if="isAdmin && unresolved && !canResolve" class="ip-monitor-help">PC가 연결되어 있고 최신 IP가 현재 기준과 일치한 뒤 처리 완료할 수 있습니다.</p>
      <p v-if="!isAdmin && unresolved" class="ip-monitor-help">관리자가 점검 내용과 조치 결과를 기록할 수 있습니다.</p>
    </div>
    <p class="ip-monitor-help">IP·MAC·어댑터와 수집 정보의 변화, 연결 상태 및 관리자의 점검 기록은 디바이스 로그에서 확인할 수 있습니다.</p>
    <Dialog :visible="reviewRequest !== null" @update:visible="closeReview" :header="reviewRequest?.action === 'resolve' ? 'IP 점검 처리 완료' : 'IP 점검 기록'" modal :closable="!submitting" :closeOnEscape="!submitting" :style="{ width: '520px' }" :breakpoints="{ '600px': '94vw' }">
      <p>{{ device.serial_number }} · {{ reviewRequest?.action === 'resolve' ? '확인한 원인과 처리 결과를 남겨 주세요.' : '점검 사유와 확인할 내용을 남겨 주세요.' }}</p>
      <label for="ip-review-note">점검 내용 (필수)</label>
      <Textarea id="ip-review-note" v-model="reviewNote" rows="5" maxlength="1000" fluid :disabled="submitting" :aria-invalid="Boolean(reviewError)" />
      <small>{{ reviewNote.length }} / 1,000자</small>
      <Message v-if="reviewError" severity="error" :closable="false">{{ reviewError }}</Message>
      <template #footer><Button label="취소" severity="secondary" :disabled="submitting" @click="closeReview(false)" /><Button :label="reviewRequest?.action === 'resolve' ? '처리 완료 기록' : '점검 내용 기록'" :loading="submitting" :disabled="submitting || !reviewNote.trim() || stale || disabled || (reviewRequest?.action === 'resolve' && !canResolve)" @click="submitReview" /></template>
    </Dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import Textarea from 'primevue/textarea'
import { useToast } from 'primevue/usetoast'
import api from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { DeviceRecord } from '@/types'
import type { DeviceAgent } from '@/types/deviceAgent'
import DeviceIpStatus from './DeviceIpStatus.vue'
import { agentErrorMessage, formatAgentDate } from './deviceAgentState'

const props = defineProps<{ device: DeviceRecord; agent: DeviceAgent | null; stale: boolean; disabled: boolean }>()
const emit = defineEmits<{ changed: []; busy: [value: boolean] }>()
const auth = useAuthStore()
const toast = useToast()
const isAdmin = computed(() => auth.user?.role === 'admin')
const monitor = computed(() => props.agent?.network_monitor)
const unresolved = computed(() => Boolean(monitor.value?.review && monitor.value.review.state !== 'resolved'))
const canResolve = computed(() => unresolved.value && !props.stale && props.agent?.status === 'online' && monitor.value?.status === 'normal' && !monitor.value.stale && !monitor.value.alert_active && !monitor.value.reference_pending && !monitor.value.reference_error)
const reviewLabel = computed(() => ({ open: '확인 필요', reviewing: '점검 중', resolved: '처리 완료' }[monitor.value?.review?.state || 'open']))
const reviewRequest = ref<{ deviceId: number; incidentId: string; action: 'start' | 'resolve' } | null>(null)
const reviewNote = ref('')
const reviewError = ref('')
const submitting = ref(false)

function openReview(action: 'start' | 'resolve') {
  if (!isAdmin.value || props.stale || props.disabled || !monitor.value?.review || !unresolved.value || (action === 'resolve' && !canResolve.value)) return
  reviewRequest.value = { deviceId: props.device.id, incidentId: monitor.value.review.incident_id, action }
  reviewNote.value = ''; reviewError.value = ''
}
function closeReview(visible: boolean) { if (!visible && !submitting.value) { reviewRequest.value = null; reviewError.value = '' } }
async function submitReview() {
  const request = reviewRequest.value
  if (!request || submitting.value || !isAdmin.value || props.stale || props.disabled || !reviewNote.value.trim()) return
  if (request.deviceId !== props.device.id || request.incidentId !== monitor.value?.review?.incident_id || !unresolved.value) { reviewError.value = '점검 대상이 변경되었습니다. 창을 닫고 최신 상태에서 다시 확인해 주세요.'; return }
  if (request.action === 'resolve' && !canResolve.value) { reviewError.value = '최신 IP가 현재 기준과 일치하는지 확인해 주세요.'; return }
  submitting.value = true; reviewError.value = ''; emit('busy', true)
  try {
    await api.post(`/devices/${request.deviceId}/agent/ip-review`, { incidentId: request.incidentId, action: request.action, note: reviewNote.value.trim() }, { timeout: 10000 })
    reviewRequest.value = null
    toast.add({ severity: 'success', summary: request.action === 'resolve' ? 'IP 점검 처리를 완료했습니다.' : 'IP 점검 내용을 기록했습니다.', life: 3500 })
  } catch (reason) { reviewError.value = await agentErrorMessage(reason) }
  finally { submitting.value = false; emit('busy', false); emit('changed') }
}
watch(() => props.device.id, () => { reviewRequest.value = null; reviewNote.value = ''; reviewError.value = '' })
</script>

<style scoped>
.ip-monitor-section{display:grid;gap:12px;border-top:1px solid #e2e8f0;padding-top:18px}.ip-monitor-heading{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}.ip-monitor-heading h3{margin:0;font-size:.9rem;color:#334155}.ip-monitor-facts{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:0;background:#f8fafc;border:1px solid #e2e8f0;padding:16px;border-radius:8px}.ip-monitor-facts dt{font-size:.74rem;color:#64748b;margin-bottom:5px}.ip-monitor-facts dd{margin:0;font-size:.83rem;overflow-wrap:anywhere}.ip-monitor-help{margin:0;font-size:.76rem;color:#64748b;line-height:1.8}.ip-review-card{display:grid;gap:10px;padding:14px;border:1px solid #e2e8f0;border-radius:8px}.ip-review-actions{display:flex;gap:8px;flex-wrap:wrap}.ip-review-note{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.82rem;margin:0;line-height:1.8}@media(max-width:640px){.ip-monitor-facts{grid-template-columns:1fr}}
</style>
