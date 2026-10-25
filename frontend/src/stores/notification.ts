import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api'
import type { Notification } from '@/types'

export const useNotificationStore = defineStore('notification', () => {
  const notifications = ref<Notification[]>([])
  const unreadCount = ref(0)
  const pendingReads = new Map<number, Promise<void>>()

  async function fetchUnreadCount() {
    try {
      const { data } = await api.get('/notifications/unread-count', { skipGlobalLoading: true })
      unreadCount.value = data.count
    } catch {
      // silent
    }
  }

  async function fetchNotifications(page = 1) {
    const { data } = await api.get('/notifications', { params: { page, size: 20 } })
    notifications.value = data.items
    return data
  }

  async function markRead(id: number) {
    const pending = pendingReads.get(id)
    if (pending) return pending
    const known = notifications.value.find((item) => item.id === id)
    if (known?.is_read) return
    const operation = (async () => {
      await api.post('/notifications/mark-read', { ids: [id] }, { skipGlobalLoading: true })
      const item = notifications.value.find((notification) => notification.id === id)
      if (item) item.is_read = true
      // The server owns the count; another session may already have read this alert.
      await fetchUnreadCount()
    })()
    pendingReads.set(id, operation)
    try { await operation } finally { pendingReads.delete(id) }
  }

  async function markAllRead() {
    await api.post('/notifications/mark-all-read', undefined, { skipGlobalLoading: true })
    notifications.value.forEach((n) => (n.is_read = true))
    unreadCount.value = 0
  }

  return { notifications, unreadCount, fetchUnreadCount, fetchNotifications, markRead, markAllRead }
})
