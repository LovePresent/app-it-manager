import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api'
import type { User } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const isAuthenticated = ref(false)

  async function fetchUser() {
    try {
      const { data } = await api.get('/auth/me')
      user.value = data
      isAuthenticated.value = true
    } catch {
      user.value = null
      isAuthenticated.value = false
    }
  }

  function setToken(token: string) {
    localStorage.setItem('access_token', token)
    isAuthenticated.value = true
  }

  function logout() {
    localStorage.removeItem('access_token')
    user.value = null
    isAuthenticated.value = false
    window.location.href = '/login'
  }

  return { user, isAuthenticated, fetchUser, setToken, logout }
})
