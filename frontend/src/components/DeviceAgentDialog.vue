<template>
  <Dialog :visible="visible" @update:visible="updateVisible" :header="`PC 관리 · ${device?.serial_number || ''}`" modal :closable="!busy" :closeOnEscape="!busy" :style="{ width: '900px' }" :breakpoints="{ '960px': '94vw' }">
    <div class="agent-dialog-body">
      <div class="agent-title-row">
        <div><strong>{{ device?.user_name || '사용자 미지정' }}</strong><p>{{ device?.serial_number }} · 표시 시간: 한국 표준시</p></div>
        <div class="agent-toolbar"><DeviceAgentStatus :agent="agent" :loaded="loaded" :stale="stale" /><Button label="디바이스 로그" icon="pi pi-list" text :disabled="Boolean(busy)" @click="showLogs = true" /><Button icon="pi pi-refresh" text rounded aria-label="PC 관리 새로고침" :loading="loading" :disabled="Boolean(busy)" @click="load" /></div>
      </div>
      <Message v-if="stale" severity="warn" :closable="false">서버 연결을 확인할 수 없습니다. {{ errorMessage }}<br>마지막 확인: {{ formatAgentDate(lastSuccess) }}</Message>
      <Message v-else-if="!loaded" severity="info" :closable="false">에이전트 정보를 불러오고 있습니다.</Message>
      <Message v-if="operationError" severity="error" :closable="false">{{ operationError }}</Message>
      <p v-if="loaded && !agent" class="agent-help">이 디바이스에 연결된 에이전트가 없습니다. 관리자가 설치 파일을 발급한 뒤 대상 Windows PC에서 실행하면 상태가 표시됩니다.</p>
      <dl v-if="agent" class="agent-facts">
        <div><dt>호스트 이름</dt><dd>{{ agent.hostname || '첫 연결 대기 중' }}</dd></div>
        <div><dt>에이전트 버전</dt><dd>{{ agent.agent_version || '—' }}</dd></div>
        <div><dt>운영 체제</dt><dd>{{ agent.os_version || '—' }}</dd></div>
        <div><dt>최근 부팅</dt><dd>{{ formatAgentDate(agent.boot_time) }}</dd></div>
        <div><dt>마지막 연결</dt><dd>{{ formatAgentDate(agent.last_seen_at) }}</dd></div>
        <div><dt>서버에서 본 연결 IP</dt><dd>{{ agent.observed_ip || '—' }}</dd></div>
      </dl>
      <p class="agent-help">15초마다 연결 신호를 확인하며, 60초 동안 신호가 없으면 연결 끊김으로 표시됩니다. 전원 종료·절전·네트워크 장애·에이전트 중지로 연결이 끊길 수 있습니다.</p>
      <Message v-if="!stale && agent?.status === 'uninstalled'" severity="warn" :closable="false">프로그램 제거 완료가 확인되었습니다. 제거 확인 시각: {{ formatAgentDate(agent.uninstalled_at) }}. 다시 연결하려면 아래 EXE를 설치해 주세요.</Message>
      <Message v-else-if="!stale && agent?.status === 'worker_missing'" severity="error" :closable="false">PC의 서비스가 작업 프로그램 파일이 없음을 확인했습니다. 설치 폴더와 보안 프로그램의 격리 여부를 점검하고 EXE로 복구 설치해 주세요.</Message>
      <Message v-else-if="!stale && agent?.status === 'worker_stopped'" severity="warn" :closable="false">PC의 서비스가 작업 프로세스 중지를 확인했습니다. 자동 복구 후 연결 상태를 다시 확인하고, 계속되면 EXE로 복구 설치해 주세요.</Message>
      <p v-if="agent?.status === 'offline'" class="agent-help">연결 끊김만으로 프로그램 삭제 여부는 알 수 없습니다. 제거 완료나 실행 중인 서비스의 보고가 있을 때만 별도 표시합니다.</p>

      <DeviceIpMonitor v-if="device && agent" :device="device" :agent="agent" :stale="stale" :disabled="Boolean(busy)" @busy="busy = $event ? 'review' : ''" @changed="refreshAfterReview" />

      <section v-if="isAdmin" class="agent-section">
        <h3>에이전트 설치 / 업데이트</h3>
        <p v-if="latestVersion" class="agent-help">제공 버전: {{ latestVersion }} · 현재 설치: {{ agent?.agent_version || '미확인' }}</p>
        <div class="agent-toolbar"><Button :label="installerLabel" icon="pi pi-download" :loading="busy === 'installer'" :disabled="Boolean(busy) || stale || !loaded || !exeAvailable" @click="downloadInstaller" /><Button v-if="downloadedInstaller" label="다시 다운로드" icon="pi pi-download" severity="secondary" :disabled="Boolean(busy)" @click="saveDownloadedInstaller" /></div>
        <p class="agent-help">처음 설치할 파일은 발급 후 15분 안에 대상 PC에서 실행하세요. 이 디바이스 전용 파일이며 다른 PC에 재사용하지 마세요. 같은 디바이스의 업데이트는 기존 설치 설정을 유지합니다.</p>
        <p v-if="agent?.status === 'pending' && agent.enrollment_expires_at" class="agent-help">등록 유효 시간: {{ formatAgentDate(agent.enrollment_expires_at) }}</p>
        <Message v-if="downloadedInstaller" severity="info" :closable="false">대상 PC에서 EXE 설치 파일을 더블클릭하고 관리자 실행을 승인한 뒤 설치하세요. 다운로드만으로 설치가 완료되지는 않습니다. 설치 후 내려받은 파일을 삭제하세요.</Message>
      </section>
      <p v-else class="agent-help">조회 권한으로 접속 중입니다. 설치 파일 발급·전원 제어·WOL 설정 변경은 관리자만 할 수 있습니다.</p>

      <section class="agent-section">
        <h3>전원 제어</h3>
        <div v-if="isAdmin" class="agent-toolbar"><Button label="재시작" icon="pi pi-refresh" severity="secondary" :disabled="Boolean(powerReason)" @click="openConfirmation('restart')" /><Button label="종료" icon="pi pi-power-off" severity="danger" outlined :disabled="Boolean(powerReason)" @click="openConfirmation('shutdown')" /><Button label="켜기 (WOL)" icon="pi pi-bolt" severity="secondary" :disabled="Boolean(wakeReason)" @click="openConfirmation('wake')" /></div>
        <p v-if="isAdmin" class="agent-help">{{ powerReason || '재시작·종료 전에 대상 PC와 저장되지 않은 작업을 확인합니다.' }}</p>
        <p v-if="isAdmin" class="agent-help">{{ wakeReason || '항상 켜져 있는 중계 PC에 WOL 전송을 요청합니다. 실제 켜짐은 연결 상태로 확인하세요.' }}</p>
      </section>

      <section class="agent-section">
        <div class="agent-section-header"><h3>수집된 네트워크</h3><span>마지막 수집 {{ formatAgentDate(agent?.network_updated_at) }}</span></div>
        <DataTable :value="agent?.network_adapters || []" size="small" stripedRows scrollable>
          <Column field="name" header="어댑터" style="min-width:140px" />
          <Column field="macAddress" header="MAC" style="min-width:150px" />
          <Column header="IPv4 / 서브넷 마스크" style="min-width:220px"><template #body="{ data }"><div v-for="entry in data.ipv4 || []" :key="entry.address" class="agent-network-value">{{ entry.address }}<small>{{ entry.netmask }}</small></div><span v-if="!data.ipv4?.length">—</span></template></Column>
          <Column header="IPv6" style="min-width:200px"><template #body="{ data }"><div v-for="address in data.ipv6 || []" :key="address" class="agent-network-value">{{ address }}</div><span v-if="!data.ipv6?.length">—</span></template></Column>
          <template #empty>아직 수집된 네트워크 정보가 없습니다. 최신 에이전트를 설치하고 연결해 주세요.</template>
        </DataTable>
        <p class="agent-help">수집된 주소는 기존 IP 대장의 수동 입력값과 별도로 표시됩니다. 서버에서 본 연결 IP는 NAT·프록시 주소일 수 있으며 공인 IP를 보장하지 않습니다.</p>
      </section>

      <section class="agent-section">
        <h3>켜기 (WOL) 설정</h3>
        <p class="agent-help">대상 PC와 같은 LAN에 항상 켜져 있는 다른 등록 PC가 필요합니다. 해당 PC는 WOL 중계 기능을 지원하고 온라인 상태여야 합니다. 대상 PC의 BIOS·네트워크 어댑터가 WOL을 지원해야 하며, 전원 연결이 끊긴 PC는 켤 수 없습니다.</p>
        <p v-if="agent?.wol" class="agent-saved-wol">저장된 설정: {{ agent.wol.macAddress }} · 중계 디바이스 #{{ agent.wol.relayDeviceId }} · {{ agent.wol.sourceAddress }} → {{ agent.wol.broadcastAddress }}:{{ agent.wol.port }}</p>
        <p v-else class="agent-help">아직 저장된 WOL 설정이 없습니다.</p>
        <form v-if="isAdmin && agent && !['revoked', 'uninstalled'].includes(agent.status)" @submit.prevent="saveWol">
          <div class="agent-form-grid">
            <div><label for="agent-adapter-mac">수집된 MAC 주소 선택</label><Select inputId="agent-adapter-mac" :modelValue="wolMac" :options="macOptions" optionLabel="label" optionValue="value" placeholder="직접 입력하거나 어댑터 선택" showClear fluid :disabled="Boolean(busy) || stale" @update:modelValue="wolMac = $event || ''" /></div>
            <div><label for="agent-wol-mac">대상 PC MAC 주소</label><InputText id="agent-wol-mac" v-model="wolMac" placeholder="AA:BB:CC:DD:EE:FF" maxlength="17" fluid :disabled="Boolean(busy) || stale" /></div>
            <div><label for="agent-wol-relay">항상 켜져 있는 중계 PC</label><Select inputId="agent-wol-relay" v-model="wolRelayId" :options="relayOptions" optionLabel="label" optionValue="value" placeholder="온라인 중계 PC 선택" fluid :disabled="Boolean(busy) || stale" @update:modelValue="wolSource = ''" /></div>
            <div><label for="agent-wol-source">중계 PC의 송신 네트워크</label><Select inputId="agent-wol-source" v-model="wolSource" :options="sourceOptions" optionLabel="label" optionValue="value" placeholder="대상 PC와 같은 LAN 선택" fluid :disabled="Boolean(busy) || stale || !selectedRelay" /></div>
          </div>
          <p v-if="!relayOptions.length" class="agent-help">사용 가능한 중계 PC가 없습니다. 다른 PC에 최신 에이전트를 설치하고 켜 두세요.</p>
          <div class="agent-form-actions"><Button label="WOL 설정 저장" icon="pi pi-save" severity="secondary" type="submit" :loading="busy === 'wol'" :disabled="Boolean(busy) || stale || !selectedRelay || !wolSource" /></div>
        </form>
      </section>

      <section class="agent-section">
        <h3>최근 전원 요청</h3>
        <p class="agent-help">‘에이전트 수신’은 실행 완료가 아닙니다. ‘WOL 신호 전송’은 중계 PC의 패킷 전송 결과입니다. 만료되거나 결과를 확인하지 못한 요청은 자동 재시도하지 않습니다.</p>
        <DataTable :value="commands" size="small" stripedRows scrollable>
          <Column header="요청" style="min-width:105px"><template #body="{ data }">{{ actionLabel(data.type) }}</template></Column>
          <Column header="상태" style="min-width:140px"><template #body="{ data }"><Tag :value="commandStatus(data.status)" :severity="['failed', 'expired', 'unconfirmed'].includes(data.status) ? 'warn' : 'secondary'" /></template></Column>
          <Column header="요청 시각" style="min-width:180px"><template #body="{ data }">{{ formatAgentDate(data.created_at) }}</template></Column>
          <Column header="안내" style="min-width:240px"><template #body="{ data }">{{ commandDetail(data.detail) }}<small v-if="data.expires_at" class="agent-expiry">유효 시간 {{ formatAgentDate(data.expires_at) }}</small></template></Column>
          <template #empty>아직 전원 요청 내역이 없습니다.</template>
        </DataTable>
      </section>
      <section v-if="isAdmin && agent && agent.status !== 'uninstalled'" class="agent-section">
        <h3>프로그램 제거 승인</h3>
        <div class="agent-toolbar"><Button label="제거 승인 코드 발급" icon="pi pi-key" severity="secondary" :disabled="Boolean(uninstallReason)" @click="openConfirmation('uninstall')" /><Button v-if="agent.status !== 'revoked'" label="에이전트 연결만 해제" severity="danger" text :disabled="Boolean(busy) || stale" @click="openConfirmation('revoke')" /></div>
        <p class="agent-help">Windows 설정의 설치된 앱에서 제거할 때 관리자 승인 코드와 Windows 관리자 권한(UAC)이 필요합니다. 연결 해제는 PC의 설치 프로그램을 제거하지 않습니다. 일반 사용자의 서비스 종료·파일 삭제는 제한하지만, Windows 로컬 관리자에 대한 커널 수준 변조 방지는 제공하지 않습니다.</p>
      </section>
      <div class="agent-bottom-row"><span>5초 자동 새로고침 · 마지막 확인 {{ formatAgentDate(lastSuccess) }}</span></div>
    </div>
    <template #footer><Button label="닫기" severity="secondary" :disabled="Boolean(busy)" @click="updateVisible(false)" /></template>
  </Dialog>
  <Dialog :visible="confirmation !== null" @update:visible="closeConfirmation" :header="confirmation ? `${actionLabel(confirmation.action)} 확인` : '요청 확인'" modal :closable="!busy" :closeOnEscape="!busy" :style="{ width: '490px' }" :breakpoints="{ '600px': '94vw' }">
    <p v-if="confirmation"><strong>{{ device?.user_name || '사용자 미지정' }} · {{ confirmation.serial }}</strong> PC에 {{ actionLabel(confirmation.action) }} 요청을 보냅니다.</p>
    <Message severity="warn" :closable="false">{{ confirmation?.action === 'uninstall' ? '이 PC 전용 제거 승인 코드를 발급합니다. 코드는 15분 동안 유효하며, Windows 제거 창에서 코드와 관리자 실행 승인이 필요합니다.' : confirmation?.action === 'revoke' ? '에이전트 인증과 연결을 해제합니다. 기존 디바이스 자산 정보는 삭제하지 않으며, PC에 설치된 프로그램은 별도로 제거해야 합니다.' : confirmation?.action === 'wake' ? '온라인 중계 PC에 WOL 전송을 요청합니다. 요청 접수만으로 PC가 켜졌다고 확인할 수 없습니다.' : '대상 PC의 파일을 먼저 저장하세요. 앱을 강제로 닫지 않으므로 열려 있는 앱이 종료나 재시작을 막을 수 있습니다.' }}</Message>
    <Message v-if="confirmationError" severity="error" :closable="false">{{ confirmationError }}</Message>
    <template #footer><Button label="취소" severity="secondary" :disabled="Boolean(busy)" @click="closeConfirmation(false)" /><Button :label="confirmation?.action === 'wake' ? 'WOL 전송 요청' : '요청 보내기'" severity="danger" :loading="busy === 'command'" :disabled="Boolean(busy) || Boolean(confirmReason)" @click="submitConfirmation" /></template>
  </Dialog>
  <Dialog :visible="uninstallCode !== null" @update:visible="clearUninstallCode" header="제거 승인 코드" modal :style="{ width: '490px' }" :breakpoints="{ '600px': '94vw' }">
    <template v-if="uninstallCode">
      <p><strong>{{ uninstallCode.serial }}</strong> PC 전용 코드입니다.</p>
      <div class="agent-toolbar"><InputText :modelValue="uninstallCode.code" readonly aria-label="제거 승인 코드" class="agent-uninstall-code" /><Button label="복사" icon="pi pi-copy" severity="secondary" @click="copyUninstallCode" /></div>
      <p class="agent-help">유효 시간: {{ formatAgentDate(uninstallCode.expiresAt) }} (한국 표준시)</p>
      <p class="agent-help">대상 PC에서 Windows 설정 → 앱 → 설치된 앱의 제거를 실행하고 코드를 입력하세요. Windows 관리자 권한도 필요합니다. 이 창을 닫거나 코드가 만료되면 화면에서 지워집니다.</p>
    </template>
    <template #footer><Button label="확인하고 닫기" severity="secondary" @click="clearUninstallCode(false)" /></template>
  </Dialog>
  <DeviceLogsDialog v-model:visible="showLogs" :device="device" />
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import api from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { DeviceRecord } from '@/types'
import type { DeviceAgent, DeviceAgentCommand, DeviceAgentDetailResponse } from '@/types/deviceAgent'
import DeviceAgentStatus from './DeviceAgentStatus.vue'
import DeviceIpMonitor from './DeviceIpMonitor.vue'
import DeviceLogsDialog from './DeviceLogsDialog.vue'
import { agentErrorMessage, formatAgentDate } from './deviceAgentState'

type Action = 'restart' | 'shutdown' | 'wake' | 'revoke' | 'uninstall'
const props = defineProps<{ visible: boolean; device: DeviceRecord | null }>()
const emit = defineEmits<{ 'update:visible': [visible: boolean]; changed: [] }>()
const auth = useAuthStore()
const toast = useToast()
const isAdmin = computed(() => auth.user?.role === 'admin')
const agent = ref<DeviceAgent | null>(null)
const commands = ref<DeviceAgentCommand[]>([])
const relays = ref<DeviceAgent[]>([])
const loaded = ref(false)
const loading = ref(false)
const stale = ref(false)
const lastSuccess = ref<string | null>(null)
const errorMessage = ref('')
const operationError = ref('')
const busy = ref<'' | 'installer' | 'wol' | 'command' | 'review'>('')
const showLogs = ref(false)
const exeAvailable = ref(false)
const latestVersion = ref('')
const downloadedInstaller = ref<{ blob: Blob; filename: string } | null>(null)
const wolMac = ref('')
const wolRelayId = ref<number | null>(null)
const wolSource = ref('')
const confirmation = ref<{ action: Action; deviceId: number; serial: string } | null>(null)
const confirmationError = ref('')
const uninstallCode = ref<{ code: string; expiresAt: string; serial: string } | null>(null)
const tick = ref(0)
let serverTime = 0
let receivedAt = 0
let timer: ReturnType<typeof setInterval> | undefined
let uninstallCodeTimer: ReturnType<typeof setTimeout> | undefined
let initializedId: number | null = null
let disposed = false

const installerLabel = computed(() => agent.value?.status === 'pending' ? '설치 파일 다시 받기' : agent.value?.status === 'uninstalled' ? '다시 설치할 EXE 받기' : agent.value && ['worker_missing', 'worker_stopped'].includes(agent.value.status) ? '복구 설치 EXE 받기' : agent.value && agent.value.status !== 'revoked' ? '업데이트 설치 파일 받기' : '설치 파일 받기')
const relayOptions = computed(() => relays.value.filter(item => item.device_id !== props.device?.id && item.status === 'online' && item.capabilities.includes('wol-relay-v1')).map(item => ({ value: item.device_id, label: `${item.hostname || item.serial_number || item.name} · ${item.serial_number || `#${item.device_id}`}` })))
const selectedRelay = computed(() => relays.value.find(item => item.device_id === wolRelayId.value && relayOptions.value.some(option => option.value === item.device_id)))
const sourceOptions = computed(() => (selectedRelay.value?.network_adapters || []).flatMap(adapter => adapter.ipv4.map(entry => ({ value: entry.address, label: `${adapter.name} · ${entry.address} / ${entry.netmask}` }))))
const macOptions = computed(() => (agent.value?.network_adapters || []).flatMap(adapter => adapter.macAddress ? [{ value: adapter.macAddress, label: `${adapter.name} · ${adapter.macAddress}` }] : []))
const serverNow = computed(() => { void tick.value; return serverTime ? serverTime + Math.max(0, performance.now() - receivedAt) : 0 })
const activeCommand = computed(() => commands.value.some(command => command.type !== 'wake' && ['pending', 'delivered', 'accepted'].includes(command.status) && (!serverNow.value || !command.expires_at || !Number.isFinite(Date.parse(command.expires_at)) || Date.parse(command.expires_at) > serverNow.value)))
const basicReason = computed(() => !isAdmin.value ? '관리자만 요청할 수 있습니다.' : busy.value ? '요청을 처리 중입니다.' : stale.value || !loaded.value ? '서버 연결을 확인한 뒤 요청할 수 있습니다.' : !agent.value || ['revoked', 'uninstalled'].includes(agent.value.status) ? '에이전트를 먼저 연결해 주세요.' : '')
const powerReason = computed(() => basicReason.value || (agent.value?.status !== 'online' ? '연결된 PC에만 재시작·종료를 요청할 수 있습니다.' : !agent.value?.capabilities.includes('power-control-v1') ? '전원 제어를 사용하려면 최신 에이전트를 설치해 주세요.' : activeCommand.value ? '이전 전원 요청의 유효 시간이 남아 있습니다. 요청 내역을 확인해 주세요.' : ''))
const wakeReason = computed(() => {
  if (basicReason.value) return basicReason.value
  if (agent.value?.status === 'online') return '현재 연결된 PC입니다.'
  const config = agent.value?.wol
  if (!config) return 'WOL 설정을 먼저 저장해 주세요.'
  const relay = relays.value.find(item => item.device_id === config.relayDeviceId && item.status === 'online' && item.capabilities.includes('wol-relay-v1'))
  if (!relay) return '설정된 중계 PC가 연결되지 않았거나 WOL 중계를 지원하지 않습니다.'
  const matchingSource = relay.network_adapters.some(adapter => adapter.ipv4.some(entry => entry.address === config.sourceAddress && broadcastAddress(entry.address, entry.netmask) === config.broadcastAddress))
  return matchingSource ? '' : '중계 PC의 네트워크가 변경되었습니다. WOL 설정을 다시 저장해 주세요.'
})
const uninstallReason = computed(() => !isAdmin.value ? '관리자만 발급할 수 있습니다.' : busy.value ? '요청을 처리 중입니다.' : stale.value || !loaded.value ? '서버 연결을 확인해 주세요.' : !agent.value ? '등록된 에이전트가 없습니다.' : '')
const confirmReason = computed(() => confirmation.value?.action === 'uninstall' ? uninstallReason.value : confirmation.value?.action === 'wake' ? wakeReason.value : confirmation.value?.action === 'revoke' ? basicReason.value : powerReason.value)

function actionLabel(action: string) { return ({ restart: '재시작', shutdown: '종료', wake: '켜기 (WOL)', revoke: '에이전트 연결 해제', uninstall: '제거 승인 코드 발급' } as Record<string, string>)[action] || '전원 요청' }
function commandStatus(status: string) { return ({ pending: '전달 대기', delivered: '전달됨', accepted: '에이전트 수신', failed: '실패', expired: '만료', unconfirmed: '결과 미확인', sent: 'WOL 신호 전송' } as Record<string, string>)[status] || '상태 미확인' }
function commandDetail(detail: string | null) {
  const labels: Record<string, string> = { accepted: '에이전트가 수신했습니다. 실행 완료 여부는 별도 확인이 필요합니다.', expired: '유효 시간이 지났으며 자동 재시도하지 않습니다.', duplicate: '이미 처리한 요청을 다시 실행하지 않았습니다.', execution_failed: '명령을 실행하지 못했습니다. 대상 PC 상태를 확인하세요.', invalid_command: '유효하지 않거나 지원하지 않는 요청입니다.', packet_sent: 'WOL 패킷을 보냈습니다. 실제 켜짐은 연결 상태로 확인하세요.', send_failed: 'WOL 패킷을 보내지 못했습니다. 중계 PC와 네트워크를 확인하세요.' }
  return detail && Object.prototype.hasOwnProperty.call(labels, detail) ? labels[detail] : '—'
}
function broadcastAddress(address: string, mask: string): string {
  const ip = address.split('.').map(Number), netmask = mask.split('.').map(Number)
  if (ip.length !== 4 || netmask.length !== 4 || [...ip, ...netmask].some(value => !Number.isInteger(value) || value < 0 || value > 255)) return ''
  return ip.map((value, index) => (value | (255 ^ netmask[index])).toString()).join('.')
}
function normalizedMac(value: string): string | null {
  const compact = value.trim()
  if (!/^(?:[0-9a-f]{12}|(?:[0-9a-f]{2}:){5}[0-9a-f]{2}|(?:[0-9a-f]{2}-){5}[0-9a-f]{2})$/i.test(compact)) return null
  const hex = compact.replace(/[:-]/g, '').toUpperCase()
  if (/^0{12}$/.test(hex) || (parseInt(hex.slice(0, 2), 16) & 1)) return null
  return hex.match(/.{2}/g)!.join(':')
}
function updateVisible(value: boolean) { if (!busy.value) emit('update:visible', value) }
function closeConfirmation(value: boolean) { if (!value && !busy.value) { confirmation.value = null; confirmationError.value = '' } }
function clearUninstallCode(value: boolean) { if (!value) { uninstallCode.value = null; clearTimeout(uninstallCodeTimer) } }
async function copyUninstallCode() {
  if (!uninstallCode.value) return
  try { await navigator.clipboard.writeText(uninstallCode.value.code); toast.add({ severity: 'info', summary: '승인 코드를 복사했습니다.', life: 2500 }) }
  catch { toast.add({ severity: 'warn', summary: '자동 복사 실패', detail: '코드를 선택하여 직접 복사해 주세요.', life: 3500 }) }
}
function initializeWol() { wolMac.value = agent.value?.wol?.macAddress || ''; wolRelayId.value = agent.value?.wol?.relayDeviceId || null; wolSource.value = agent.value?.wol?.sourceAddress || '' }
function refreshAfterReview() { emit('changed'); void load() }

async function load() {
  if (!props.visible || !props.device || loading.value || busy.value || document.hidden || disposed) return
  const deviceId = props.device.id
  loading.value = true
  try {
    const { data } = await api.get<DeviceAgentDetailResponse>(`/devices/${deviceId}/agent`, { skipGlobalLoading: true, timeout: 10000 })
    if (disposed || !props.visible || props.device?.id !== deviceId) return
    agent.value = data.agent
    commands.value = [...(data.commands || [])].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
    relays.value = data.relay_devices || []
    exeAvailable.value = (data.installer_formats || ['exe']).includes('exe')
    latestVersion.value = data.latest_agent_version || ''
    serverTime = Date.parse(data.server_time)
    receivedAt = performance.now()
    tick.value += 1
    lastSuccess.value = data.server_time
    stale.value = false
    loaded.value = true
    errorMessage.value = ''
    if (initializedId !== deviceId) { initializeWol(); initializedId = deviceId }
  } catch (reason) {
    if (disposed || props.device?.id !== deviceId) return
    stale.value = true
    errorMessage.value = await agentErrorMessage(reason)
  } finally { loading.value = false }
}

function saveDownloadedInstaller() {
  if (!downloadedInstaller.value) return
  const url = URL.createObjectURL(downloadedInstaller.value.blob)
  const link = document.createElement('a')
  link.href = url; link.download = downloadedInstaller.value.filename
  document.body.append(link); link.click(); link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}
async function downloadInstaller() {
  if (!isAdmin.value || busy.value || stale.value || !props.device) return
  busy.value = 'installer'; operationError.value = ''
  try {
    const response = await api.post<Blob>(`/devices/${props.device.id}/agent/installer`, { format: 'exe' }, { responseType: 'blob', timeout: 60000, loadingLabel: 'PC 전용 EXE 설치 파일을 준비하는 중' })
    const disposition = String(response.headers['content-disposition'] || '')
    const extended = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1]
    const basic = /filename="?([^";]+)"?/i.exec(disposition)?.[1]
    let filename = basic || `SecurityAgent-Setup-${props.device.id}.exe`
    if (extended) { try { filename = decodeURIComponent(extended) } catch { /* Use the ordinary filename. */ } }
    filename = filename.replace(/[\\/:*?"<>|\x00-\x1F]/g, '_')
    downloadedInstaller.value = { blob: response.data, filename }
    saveDownloadedInstaller()
    toast.add({ severity: 'info', summary: '설치 파일 준비 완료', detail: '대상 Windows PC에서 설치 파일을 실행해 주세요.', life: 5000 })
    emit('changed')
  } catch (reason) { operationError.value = await agentErrorMessage(reason) }
  finally { busy.value = '' }
  await load()
}

async function saveWol() {
  if (!isAdmin.value || busy.value || stale.value || !props.device) return
  const macAddress = normalizedMac(wolMac.value)
  if (!macAddress) { operationError.value = '유효한 MAC 주소를 입력해 주세요. 예: AA:BB:CC:DD:EE:FF'; return }
  if (!selectedRelay.value || !sourceOptions.value.some(item => item.value === wolSource.value)) { operationError.value = '온라인 중계 PC와 송신 네트워크를 선택해 주세요.'; return }
  busy.value = 'wol'; operationError.value = ''
  try {
    await api.put(`/devices/${props.device.id}/agent/wol`, { macAddress, relayDeviceId: wolRelayId.value, sourceAddress: wolSource.value }, { timeout: 10000 })
    toast.add({ severity: 'success', summary: 'WOL 설정 저장', life: 3500 }); emit('changed')
  } catch (reason) { operationError.value = await agentErrorMessage(reason) }
  finally { busy.value = '' }
  await load()
}
function openConfirmation(action: Action) {
  if (!props.device || !isAdmin.value || busy.value) return
  if ((action === 'uninstall' ? uninstallReason.value : action === 'wake' ? wakeReason.value : action === 'revoke' ? basicReason.value : powerReason.value)) return
  confirmation.value = { action, deviceId: props.device.id, serial: props.device.serial_number }
  confirmationError.value = ''; operationError.value = ''
}
async function submitConfirmation() {
  if (!confirmation.value || confirmReason.value || !props.device) return
  const request = { ...confirmation.value }
  if (request.deviceId !== props.device.id || request.serial !== props.device.serial_number) { confirmationError.value = '대상 기기가 변경되었습니다. 확인창을 닫고 다시 요청하세요.'; return }
  busy.value = 'command'; confirmationError.value = ''
  try {
    const endpoint = `/devices/${request.deviceId}/agent`
    if (request.action === 'uninstall') {
      const { data } = await api.post<{ code: string; expires_at: string }>(`${endpoint}/uninstall-code`, { confirmation: request.serial }, { timeout: 10000 })
      clearUninstallCode(false)
      uninstallCode.value = { code: data.code, expiresAt: data.expires_at, serial: request.serial }
      const lifetime = Math.max(0, Math.min(15 * 60 * 1000, Date.parse(data.expires_at) - serverNow.value))
      uninstallCodeTimer = setTimeout(() => clearUninstallCode(false), Number.isFinite(lifetime) ? lifetime : 0)
    }
    else if (request.action === 'revoke') await api.delete(endpoint, { timeout: 10000 })
    else if (request.action === 'wake') await api.post(`${endpoint}/wake`, { confirmation: request.serial }, { timeout: 10000 })
    else await api.post(`${endpoint}/power`, { action: request.action, confirmation: request.serial }, { timeout: 10000 })
    confirmation.value = null
    if (request.action !== 'uninstall') toast.add({ severity: 'info', summary: request.action === 'revoke' ? '에이전트 연결 해제' : '요청 접수', detail: request.action === 'revoke' ? '디바이스 자산 정보는 유지됩니다.' : '최근 전원 요청에서 에이전트 수신·전송 상태를 확인하세요.', life: 5000 })
    emit('changed')
  } catch (reason) { confirmationError.value = `${await agentErrorMessage(reason)} 요청 결과가 불확실하면 내역을 먼저 확인해 주세요. 자동 재시도하지 않습니다.` }
  finally { busy.value = '' }
  await load()
}
function resume() { if (!document.hidden) { if (loaded.value && performance.now() - receivedAt > 15000) { stale.value = true; errorMessage.value = '연결 상태를 다시 확인하고 있습니다.' } tick.value += 1; void load() } }
function offline() { if (props.visible) { stale.value = true; errorMessage.value = '현재 PC 상태를 확인할 수 없습니다.' } }
function beforeUnload(event: BeforeUnloadEvent) { if (busy.value) { event.preventDefault(); event.returnValue = '' } }
watch(() => [props.visible, props.device?.id] as const, ([visible, id]) => {
  clearInterval(timer)
  showLogs.value = false
  if (!visible || !id) { confirmation.value = null; clearUninstallCode(false); return }
  clearUninstallCode(false)
  agent.value = null; commands.value = []; relays.value = []; loaded.value = false; stale.value = false
  lastSuccess.value = null; operationError.value = ''; errorMessage.value = ''; downloadedInstaller.value = null
  initializedId = null; serverTime = 0
  void load()
  timer = setInterval(() => { tick.value += 1; void load() }, 5000)
}, { immediate: true })
document.addEventListener('visibilitychange', resume)
window.addEventListener('online', resume)
window.addEventListener('offline', offline)
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => { disposed = true; clearInterval(timer); clearUninstallCode(false); document.removeEventListener('visibilitychange', resume); window.removeEventListener('online', resume); window.removeEventListener('offline', offline); window.removeEventListener('beforeunload', beforeUnload) })
</script>

<style scoped>
.agent-uninstall-code{font-family:Consolas,monospace;font-size:1.2rem;letter-spacing:.12em;flex:1;min-width:150px}
.agent-dialog-body{display:grid;gap:14px}.agent-title-row,.agent-section-header,.agent-bottom-row{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}.agent-title-row p{font-size:.8rem;color:#64748b;margin:6px 0 0}.agent-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.agent-facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 24px;padding:17px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:9px;margin:0}.agent-facts dt{font-size:.74rem;color:#64748b;margin-bottom:5px}.agent-facts dd{font-size:.83rem;margin:0;overflow-wrap:anywhere}.agent-help{font-size:.76rem;line-height:1.8;color:#64748b;margin:0}.agent-section{border-top:1px solid #e2e8f0;padding-top:17px;display:grid;gap:11px}.agent-section h3{font-size:.9rem;margin:0;color:#334155}.agent-section-header>span,.agent-bottom-row>span{font-size:.72rem;color:#94a3b8}.agent-form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.agent-form-grid label{display:block;font-size:.78rem;color:#475569;margin-bottom:7px}.agent-form-actions{display:flex;justify-content:flex-end;margin-top:14px}.agent-saved-wol{font-size:.76rem;overflow-wrap:anywhere;line-height:1.8;background:#f8fafc;border-radius:7px;padding:11px;margin:0}.agent-network-value{font-family:Consolas,monospace;font-size:.75rem;overflow-wrap:anywhere;white-space:normal}.agent-network-value small,.agent-expiry{display:block;font-size:.68rem;color:#94a3b8;margin-top:4px}.agent-command{display:block;white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f9;padding:10px;margin:9px 0}.agent-bottom-row{padding-top:8px}.agent-section :deep(.p-datatable){font-size:.76rem}@media(max-width:640px){.agent-form-grid,.agent-facts{grid-template-columns:1fr}.agent-toolbar{align-items:stretch}.agent-toolbar :deep(.p-select){max-width:100%;width:100%}.agent-section-header>span{width:100%}.agent-bottom-row{align-items:flex-start;flex-direction:column}}
</style>
