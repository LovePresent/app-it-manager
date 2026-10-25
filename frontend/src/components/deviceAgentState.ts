import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import api from '@/api'
import type { DeviceAgent, DeviceAgentListResponse } from '@/types/deviceAgent'

const agents = shallowRef<DeviceAgent[]>([])
const loaded = ref(false)
const stale = ref(false)
const lastUpdated = ref<string | null>(null)
const error = ref('')
let subscribers = 0
let timer: ReturnType<typeof setInterval> | undefined
let inFlight = false
let lastReceivedAt = 0

export function agentIPv4(agent?: DeviceAgent | null): string[] {
  return [...new Set((agent?.network_adapters || []).flatMap(adapter => (adapter.ipv4 || []).map(entry => entry.address)).filter(Boolean))]
}

export function formatAgentDate(value?: string | null): string {
  if (!value) return '—'
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`
  if (!Number.isFinite(Date.parse(normalized))) return '—'
  return new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(normalized))
}

export async function agentErrorMessage(reason: unknown): Promise<string> {
  const failure = reason as { response?: { data?: unknown }; message?: string }
  let data = failure.response?.data
  if (data instanceof Blob) {
    try { data = JSON.parse(await data.text()) } catch { return '파일을 준비하지 못했습니다. 서버 연결과 설치 파일 설정을 확인해 주세요.' }
  }
  if (data && typeof data === 'object') {
    const detail = (data as { detail?: unknown; error?: unknown }).detail ?? (data as { error?: unknown }).error
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return '입력한 값이 올바르지 않습니다. 기기와 네트워크 설정을 확인해 주세요.'
  }
  return '서버에 연결하지 못했습니다. 마지막 확인 정보가 표시됩니다.'
}

async function refresh() {
  if (inFlight || document.hidden || !subscribers) return
  inFlight = true
  try {
    const { data } = await api.get<DeviceAgentListResponse>('/agents', { skipGlobalLoading: true, timeout: 10000 })
    if (!Array.isArray(data.items)) throw new Error('Invalid agent response')
    agents.value = data.items
    lastUpdated.value = data.server_time
    lastReceivedAt = performance.now()
    loaded.value = true
    stale.value = false
    error.value = ''
  } catch (reason) {
    stale.value = true
    error.value = await agentErrorMessage(reason)
  } finally { inFlight = false }
}

function onVisibility() {
  if (document.hidden) return
  if (loaded.value && performance.now() - lastReceivedAt > 15000) { stale.value = true; error.value = '연결 상태를 다시 확인하고 있습니다.' }
  void refresh()
}
function onOffline() { stale.value = true; error.value = '서버 연결이 끊겼습니다. 현재 PC 상태를 확인할 수 없습니다.' }

export function useDeviceAgentPresence() {
  onMounted(() => {
    subscribers += 1
    if (subscribers === 1) {
      document.addEventListener('visibilitychange', onVisibility)
      window.addEventListener('online', onVisibility)
      window.addEventListener('offline', onOffline)
      timer = setInterval(() => { void refresh() }, 5000)
    }
    void refresh()
  })
  onBeforeUnmount(() => {
    subscribers = Math.max(0, subscribers - 1)
    if (!subscribers) {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('online', onVisibility)
      window.removeEventListener('offline', onOffline)
    }
  })
  const byDevice = computed(() => new Map(agents.value.map(agent => [agent.device_id, agent])))
  return { agents, byDevice, loaded, stale, lastUpdated, error, refresh }
}
