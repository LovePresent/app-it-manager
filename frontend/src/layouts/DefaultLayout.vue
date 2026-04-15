<template>
  <div class="layout">
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <h2 v-if="!sidebarCollapsed">IT 자산 관리</h2>
        <Button
          :icon="sidebarCollapsed ? 'pi pi-angle-right' : 'pi pi-angle-left'"
          text
          rounded
          @click="sidebarCollapsed = !sidebarCollapsed"
        />
      </div>
      <nav class="sidebar-nav">
        <router-link v-for="item in menuItems" :key="item.to" :to="item.to" class="nav-item">
          <i :class="item.icon"></i>
          <span v-if="!sidebarCollapsed">{{ item.label }}</span>
        </router-link>
      </nav>
    </aside>

    <div class="main-area">
      <header class="topbar">
        <div class="topbar-left"></div>
        <div class="topbar-right">
          <Button
            icon="pi pi-bell"
            text
            rounded
            :badge="unreadCount > 0 ? String(unreadCount) : undefined"
            badgeSeverity="danger"
            @click="$router.push('/notifications')"
          />
          <span class="user-name">{{ authStore.user?.display_name }}</span>
          <Button icon="pi pi-sign-out" text rounded @click="authStore.logout()" />
        </div>
      </header>
      <main class="content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import Button from 'primevue/button'
import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'
import { useCategoryStore } from '@/stores/category'

const authStore = useAuthStore()
const notifStore = useNotificationStore()
const categoryStore = useCategoryStore()
const sidebarCollapsed = ref(false)

const unreadCount = computed(() => notifStore.unreadCount)

const menuItems = [
  { to: '/', icon: 'pi pi-home', label: '대시보드' },
  { to: '/assets', icon: 'pi pi-box', label: '자산 목록' },
  { to: '/licenses', icon: 'pi pi-key', label: '소프트웨어 라이센스' },
  { to: '/subscriptions', icon: 'pi pi-cloud', label: 'SaaS/구독' },
  { to: '/ip-addresses', icon: 'pi pi-globe', label: 'IP 주소' },
  { to: '/certificates', icon: 'pi pi-lock', label: 'SSL 인증서' },
  { to: '/consumables', icon: 'pi pi-shopping-bag', label: '소모품' },
  { to: '/maintenance', icon: 'pi pi-wrench', label: '유지보수' },
  { to: '/racks', icon: 'pi pi-server', label: '서버 랙' },
  { to: '/categories', icon: 'pi pi-tags', label: '카테고리 관리' },
  { to: '/locations', icon: 'pi pi-map-marker', label: '위치/부서' },
  { to: '/audit-logs', icon: 'pi pi-history', label: '감사 로그' },
  { to: '/notifications', icon: 'pi pi-bell', label: '알림' },
]

onMounted(async () => {
  await authStore.fetchUser()
  await categoryStore.fetchCategories()
  notifStore.fetchUnreadCount()
})
</script>

<style scoped>
.layout {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: var(--sidebar-width);
  background: #1e293b;
  color: #fff;
  display: flex;
  flex-direction: column;
  transition: width 0.2s;
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  z-index: 100;
  overflow-y: auto;
}

.sidebar.collapsed {
  width: 64px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem;
  border-bottom: 1px solid #334155;
}

.sidebar-header h2 {
  font-size: 1.1rem;
  white-space: nowrap;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  padding: 0.5rem;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.65rem 0.75rem;
  border-radius: 8px;
  color: #94a3b8;
  text-decoration: none;
  font-size: 0.9rem;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s;
}

.nav-item:hover {
  background: #334155;
  color: #fff;
}

.nav-item.router-link-active,
.nav-item.router-link-exact-active {
  background: #3b82f6;
  color: #fff;
}

.nav-item i {
  font-size: 1.1rem;
  min-width: 20px;
  text-align: center;
}

.main-area {
  flex: 1;
  margin-left: var(--sidebar-width);
  transition: margin-left 0.2s;
  display: flex;
  flex-direction: column;
}

.sidebar.collapsed ~ .main-area {
  margin-left: 64px;
}

.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1.5rem;
  background: #fff;
  border-bottom: 1px solid #e2e8f0;
  position: sticky;
  top: 0;
  z-index: 50;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.user-name {
  font-size: 0.9rem;
  font-weight: 500;
  color: #475569;
}

.content {
  padding: 1.5rem;
  flex: 1;
}
</style>
