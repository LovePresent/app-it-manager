<template>
  <div class="login-page">
    <div class="login-card">
      <h1>IT 자산 관리</h1>
      <p>Authentik SSO를 통해 로그인하세요.</p>
      <Button label="SSO 로그인" icon="pi pi-sign-in" @click="login" size="large" />
    </div>
  </div>
</template>

<script setup lang="ts">
import Button from 'primevue/button'

function login() {
  window.location.href = import.meta.env.BASE_URL + 'api/v1/auth/login'
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
</style>
