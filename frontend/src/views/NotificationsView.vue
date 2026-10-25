<template>
  <div>
    <div class="page-header">
      <div><h1>알림</h1><p class="page-subtitle">IP 관측 알림은 해당 PC의 최신 상태와 점검 기록을 함께 확인하세요.</p></div>
      <div class="notification-actions">
        <Button label="새로고침" icon="pi pi-refresh" severity="secondary" :loading="loading" @click="load" />
        <Button label="모두 읽음 처리" icon="pi pi-check-circle" severity="secondary" :loading="markingAll" @click="markAllRead" v-if="notifStore.unreadCount > 0" />
      </div>
    </div>
    <div class="card">
      <Message v-if="loadError" severity="error" :closable="false">{{ loadError }}</Message>
      <div v-if="items.length === 0 && !loadError" class="empty-state">{{ loading ? '알림을 불러오는 중입니다.' : '알림이 없습니다.' }}</div>
      <article v-for="n in items" :key="n.id" class="notif-item" :class="{ unread: !n.is_read }">
        <div class="notif-icon" :class="{ 'ip-warning': n.type === 'ip_mismatch' }"><i :class="typeIcon(n.type)" aria-hidden="true"></i></div>
        <div class="notif-body">
          <div class="notif-labels"><Tag :value="typeLabel(n.type)" :severity="typeSeverity(n.type)" /><span v-if="!n.is_read" class="unread-label">읽지 않음</span></div>
          <div class="notif-title">{{ n.title }}</div>
          <div class="notif-msg">{{ n.message }}</div>
          <small v-if="isIpNotification(n)" class="notif-context">알림은 당시 관측 기록입니다. 읽음 처리는 IP 점검의 조치 완료와 다릅니다.</small>
          <div class="notif-time">{{ notificationDate(n.created_at) }}</div>
          <div class="notification-actions notif-controls">
            <Button v-if="hasDeviceTarget(n)" :label="isIpNotification(n) ? 'PC 확인 / 점검' : 'PC 관리'" icon="pi pi-desktop" size="small" @click="openDevice(n)" />
            <Button v-if="!n.is_read" label="읽음 처리" icon="pi pi-check" size="small" severity="secondary" text :loading="readingIds.includes(n.id)" @click="markRead(n)" />
          </div>
        </div>
      </article>
      <Paginator :rows="20" :totalRecords="total" :first="(page-1)*20" @page="onPage" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import Paginator from 'primevue/paginator'
import Button from 'primevue/button'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import { useNotificationStore } from '@/stores/notification'
import { agentErrorMessage, formatAgentDate } from '@/components/deviceAgentState'
import type { Notification } from '@/types'

const notifStore = useNotificationStore()
const router = useRouter()
const toast = useToast()
const items = ref<Notification[]>([])
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const markingAll = ref(false)
const loadError = ref('')
const readingIds = ref<number[]>([])
let loadVersion = 0
const ipTypes = new Set(['ip_mismatch', 'ip_restored', 'ip_reference_resolved'])

function typeIcon(t: string) {
  const map: Record<string, string> = { warning: 'pi pi-exclamation-triangle', info: 'pi pi-info-circle', error: 'pi pi-times-circle', ip_mismatch: 'pi pi-exclamation-triangle', ip_restored: 'pi pi-check-circle', ip_reference_resolved: 'pi pi-sync' }
  return map[t] ?? 'pi pi-bell'
}

function typeLabel(type: string) {
  const labels: Record<string, string> = {
    ip_mismatch: 'IP 불일치 확인 필요', ip_restored: '기존 기준 IP 복구 확인', ip_reference_resolved: '변경된 기준 IP 일치',
    warning: '주의', info: '안내', error: '오류', license_expiry: '라이선스 만료', warranty_expiry: '보증 만료',
    cert_expiry: '인증서 만료', low_stock: '재고 부족', maintenance_due: '점검 예정',
  }
  return labels[type] ?? '알림'
}

function typeSeverity(type: string): 'warn' | 'success' | 'info' | 'danger' | 'secondary' {
  if (type === 'ip_mismatch' || type === 'warning') return 'warn'
  if (type === 'ip_restored') return 'success'
  if (type === 'ip_reference_resolved' || type === 'info') return 'info'
  return type === 'error' ? 'danger' : 'secondary'
}

function isIpNotification(item: Notification) { return ipTypes.has(item.type) }
function hasDeviceTarget(item: Notification) { return item.entity_type === 'device' && Number.isInteger(item.entity_id) && (item.entity_id ?? 0) > 0 }
function notificationDate(value: string) {
  return formatAgentDate(/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value.replace(' ', 'T')}Z`)
}

function openDevice(item: Notification) {
  if (!hasDeviceTarget(item)) return
  void markRead(item)
  void router.push({ name: 'Devices', query: { deviceId: String(item.entity_id) } })
}

async function load() {
  const version = ++loadVersion
  loading.value = true
  loadError.value = ''
  try {
    const data = await notifStore.fetchNotifications(page.value)
    if (version !== loadVersion) return
    items.value = data.items
    total.value = data.total
    void notifStore.fetchUnreadCount()
  } catch (reason) {
    if (version === loadVersion) loadError.value = await agentErrorMessage(reason)
  } finally { if (version === loadVersion) loading.value = false }
}

async function markRead(n: Notification) {
  if (n.is_read || readingIds.value.includes(n.id)) return
  readingIds.value.push(n.id)
  try { await notifStore.markRead(n.id); n.is_read = true }
  catch (reason) { toast.add({ severity: 'error', summary: '읽음 처리 실패', detail: await agentErrorMessage(reason), life: 5000 }) }
  finally { readingIds.value = readingIds.value.filter(id => id !== n.id) }
}

async function markAllRead() {
  if (markingAll.value) return
  markingAll.value = true
  try { await notifStore.markAllRead(); items.value.forEach(item => { item.is_read = true }); await load() }
  catch (reason) { toast.add({ severity: 'error', summary: '읽음 처리 실패', detail: await agentErrorMessage(reason), life: 5000 }) }
  finally { markingAll.value = false }
}

function onPage(e: any) { page.value = e.page + 1; load() }

onMounted(load)
</script>

<style scoped>
.page-subtitle { margin:.35rem 0 0;color:#64748b;font-size:.9rem; }
.notification-actions { display:flex;gap:.6rem;align-items:center;flex-wrap:wrap; }
.empty-state { text-align:center;padding:2rem;color:#64748b; }
.notif-item { display:flex; gap:1rem; padding:1rem; border-bottom:1px solid #f1f5f9; transition:background 0.15s; }
.notif-item:hover { background:#f8fafc; }
.notif-item.unread { background:#eff6ff; }
.notif-icon { width:40px; height:40px; border-radius:50%; background:#e2e8f0; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.notif-title { font-weight:600; margin-bottom:0.25rem; }
.notif-body { min-width:0;flex:1; }
.notif-labels { display:flex;align-items:center;gap:.6rem;flex-wrap:wrap;margin-bottom:.5rem; }
.unread-label { color:#1d4ed8;font-size:.75rem;font-weight:600; }
.notif-icon.ip-warning { background:#fff7ed;color:#b45309; }
.notif-msg { font-size:0.9rem; color:#475569;line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere; }
.notif-context { display:block;margin-top:.5rem;color:#64748b;line-height:1.5; }
.notif-controls { margin-top:.8rem; }
.notif-time { font-size:0.8rem; color:#94a3b8; margin-top:0.25rem; }
@media(max-width:640px) { .page-header { align-items:flex-start;flex-direction:column;gap:1rem; }.notif-item { padding:1rem .5rem;gap:.65rem; } }
</style>
