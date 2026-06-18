<template>
  <div class="login-page">
    <div class="login-card">
      <h1>IT 자산 관리</h1>
      <p>Authentik SSO를 통해 로그인하세요.</p>
      <div class="login-actions">
        <Button label="SSO 로그인" icon="pi pi-sign-in" @click="login" size="large" />
        <Button
          v-if="localLoginEnabled"
          :label="`로컬 로그인 (${localLoginEmail})`"
          icon="pi pi-desktop"
          severity="secondary"
          outlined
          :loading="localLoading"
          @click="localLogin"
        />
      </div>
      <p v-if="localError" class="login-error">{{ localError }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import Button from 'primevue/button'
import api from '@/api'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const localLoginEnabled = import.meta.env.VITE_LOCAL_LOGIN_ENABLED === 'true'
const localLoginEmail = import.meta.env.VITE_LOCAL_LOGIN_EMAIL ?? 'it.j@cqv.kr'
const localLoading = ref(false)
const localError = ref('')

function login() {
  window.location.href = '/api/v1/auth/login'
}

async function localLogin() {
  localLoading.value = true
  localError.value = ''
  try {
    const { data } = await api.post('/auth/local-login')
    authStore.setToken(data.access_token)
    await authStore.fetchUser()
    await router.replace('/')
  } catch {
    localError.value = '로컬 로그인에 실패했습니다.'
  } finally {
    localLoading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #1e293b;
}
.login-card {
  background: #fff;
  padding: 3rem;
  border-radius: 16px;
  text-align: center;
  max-width: 400px;
  width: 100%;
}
.login-card h1 {
  margin-bottom: 0.5rem;
}
.login-card p {
  color: #64748b;
  margin-bottom: 2rem;
}
.login-actions {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.login-error {
  color: #dc2626 !important;
  margin: 1rem 0 0 !important;
}
</style>
