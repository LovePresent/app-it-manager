<template>
  <div>
    <div class="page-header">
      <h1>알림</h1>
      <Button label="모두 읽음 처리" icon="pi pi-check-circle" severity="secondary" @click="markAllRead" v-if="notifStore.unreadCount > 0" />
    </div>
    <div class="card">
      <div v-if="items.length === 0" style="text-align:center;padding:2rem;color:#94a3b8">알림이 없습니다.</div>
      <div v-for="n in items" :key="n.id" class="notif-item" :class="{ unread: !n.is_read }" @click="markRead(n)">
        <div class="notif-icon"><i :class="typeIcon(n.type)"></i></div>
        <div class="notif-body">
          <div class="notif-title">{{ n.title }}</div>
          <div class="notif-msg">{{ n.message }}</div>
          <div class="notif-time">{{ n.created_at }}</div>
        </div>
      </div>
      <Paginator :rows="20" :totalRecords="total" :first="(page-1)*20" @page="onPage" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import Paginator from 'primevue/paginator'
import Button from 'primevue/button'
import { useNotificationStore } from '@/stores/notification'
import type { Notification } from '@/types'

const notifStore = useNotificationStore()
const items = ref<Notification[]>([])
const page = ref(1)
const total = ref(0)

function typeIcon(t: string) {
  const map: Record<string, string> = { warning: 'pi pi-exclamation-triangle', info: 'pi pi-info-circle', error: 'pi pi-times-circle' }
  return map[t] ?? 'pi pi-bell'
}

async function load() {
  const data = await notifStore.fetchNotifications(page.value)
  items.value = notifStore.notifications
  total.value = data.total
}

async function markRead(n: Notification) {
  if (!n.is_read) await notifStore.markRead(n.id)
}

async function markAllRead() {
  await notifStore.markAllRead()
  load()
}

function onPage(e: any) { page.value = e.page + 1; load() }

onMounted(load)
</script>

<style scoped>
.notif-item { display:flex; gap:1rem; padding:1rem; border-bottom:1px solid #f1f5f9; cursor:pointer; transition:background 0.15s; }
.notif-item:hover { background:#f8fafc; }
.notif-item.unread { background:#eff6ff; }
.notif-icon { width:40px; height:40px; border-radius:50%; background:#e2e8f0; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.notif-title { font-weight:600; margin-bottom:0.25rem; }
.notif-msg { font-size:0.9rem; color:#475569; }
.notif-time { font-size:0.8rem; color:#94a3b8; margin-top:0.25rem; }
</style>
