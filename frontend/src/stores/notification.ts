import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api'
import type { Notification } from '@/types'

export const useNotificationStore = defineStore('notification', () => {
  const notifications = ref<Notification[]>([])
  const unreadCount = ref(0)

  async function fetchUnreadCount() {
    try {
      const { data } = await api.get('/notifications/unread-count')
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
    await api.patch(`/notifications/${id}/read`)
    const n = notifications.value.find((n) => n.id === id)
    if (n) n.is_read = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  }

  async function markAllRead() {
    await api.patch('/notifications/read-all')
    notifications.value.forEach((n) => (n.is_read = true))
    unreadCount.value = 0
  }

  return { notifications, unreadCount, fetchUnreadCount, fetchNotifications, markRead, markAllRead }
})
