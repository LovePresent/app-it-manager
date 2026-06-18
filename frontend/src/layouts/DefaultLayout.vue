<template>
  <div class="layout">
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <router-link to="/" class="brand-link" aria-label="대시보드">
          <i class="pi pi-desktop"></i>
          <span v-if="!sidebarCollapsed">IT 자산 관리</span>
        </router-link>
        <Button
          :icon="sidebarCollapsed ? 'pi pi-angle-right' : 'pi pi-angle-left'"
          text
          rounded
          :aria-label="sidebarCollapsed ? '사이드바 펼치기' : '사이드바 접기'"
          @click="sidebarCollapsed = !sidebarCollapsed"
        />
      </div>

      <nav class="sidebar-nav" aria-label="사이드 메뉴">
        <section v-for="section in sidebarSections" :key="section.key" class="sidebar-section">
          <div v-if="!sidebarCollapsed" class="sidebar-section-label">{{ section.label }}</div>
          <router-link
            v-for="item in section.items"
            :key="item.to"
            :to="item.to"
            class="nav-item"
            :class="{ active: isNavItemActive(item) }"
            :title="sidebarCollapsed ? item.label : undefined"
            :data-search-entity="item.entity"
            :data-ai-context="item.aiContext"
          >
            <i :class="item.icon"></i>
            <span v-if="!sidebarCollapsed" class="nav-item-label">{{ item.label }}</span>
          </router-link>
        </section>
      </nav>
    </aside>

    <div class="main-area">
      <header ref="topbarRef" class="topbar">
        <div class="topbar-left">
          <nav class="menu-navbar" aria-label="상단 메뉴">
            <div v-for="group in topNavigationGroups" :key="group.key" class="menu-group">
              <button
                type="button"
                class="menu-trigger"
                :class="{ active: isGroupActive(group), open: openMenu === group.key }"
                :aria-expanded="openMenu === group.key"
                :aria-controls="`menu-${group.key}`"
                @click.stop="toggleMenu(group.key)"
              >
                <i :class="group.icon"></i>
                <span>{{ group.label }}</span>
                <i class="pi pi-angle-down menu-caret"></i>
              </button>

              <div v-if="openMenu === group.key" :id="`menu-${group.key}`" class="menu-popover">
                <div class="menu-popover-header">
                  <span><i :class="group.icon"></i>{{ group.label }}</span>
                  <small>{{ group.items.length }}개 메뉴</small>
                </div>
                <router-link
                  v-for="item in group.items"
                  :key="item.to"
                  :to="item.to"
                  class="menu-item"
                  :class="{ active: isNavItemActive(item) }"
                  :data-search-entity="item.entity"
                  :data-ai-context="item.aiContext"
                  @click="closeOverlays"
                >
                  <span class="menu-item-icon"><i :class="item.icon"></i></span>
                  <span class="menu-item-text">
                    <strong>{{ item.label }}</strong>
                    <small>{{ item.description }}</small>
                  </span>
                </router-link>
              </div>
            </div>
          </nav>

          <div class="search-shell">
            <div class="search-control">
              <IconField class="global-search-field">
                <InputIcon class="pi pi-search" />
                <InputText
                  v-model="searchQuery"
                  placeholder="자산, 디바이스, IP, 메뉴 검색"
                  aria-label="통합 검색"
                  @focus="openSearch('search')"
                  @keydown.enter.prevent="submitGlobalSearch"
                  @keydown.esc="closeOverlays"
                />
              </IconField>
              <Button
                v-if="searchQuery"
                icon="pi pi-times"
                text
                rounded
                aria-label="검색어 지우기"
                @click="clearSearch"
              />
              <Button class="ai-entry-button" icon="pi pi-bolt" label="AI" outlined severity="secondary" @click="openAiMode" />
            </div>

            <div v-if="searchOpen" class="search-popover" role="dialog" aria-label="검색">
              <div class="search-tabs" role="tablist" aria-label="검색 모드">
                <button
                  type="button"
                  class="search-tab"
                  :class="{ active: searchMode === 'search' }"
                  role="tab"
                  :aria-selected="searchMode === 'search'"
                  @click="searchMode = 'search'"
                >
                  검색
                </button>
                <button
                  type="button"
                  class="search-tab"
                  :class="{ active: searchMode === 'ai' }"
                  role="tab"
                  :aria-selected="searchMode === 'ai'"
                  @click="searchMode = 'ai'"
                >
                  AI 질의
                </button>
                <Tag v-if="totalSearchResultCount > 0 && searchMode === 'search'" :value="String(totalSearchResultCount)" severity="info" />
              </div>

              <div v-if="searchMode === 'search'" class="search-results">
                <section v-if="menuResults.length > 0" class="result-section">
                  <div class="result-section-title">{{ trimmedSearchQuery ? '메뉴' : '추천 메뉴' }}</div>
                  <button
                    v-for="item in menuResults"
                    :key="item.key"
                    type="button"
                    class="result-row"
                    :data-search-entity="item.entity"
                    :data-ai-context="item.aiContext"
                    @click="goNavigation(item)"
                  >
                    <span class="result-icon"><i :class="item.icon"></i></span>
                    <span class="result-text">
                      <strong>{{ item.label }}</strong>
                      <small>{{ item.section }} · {{ item.description }}</small>
                    </span>
                  </button>
                </section>

                <section v-if="showDeviceResults" class="result-section">
                  <div class="result-section-title">디바이스 / IP-MAC</div>
                  <div v-if="deviceSearchLoading" class="result-empty">검색 중입니다.</div>
                  <div v-else-if="deviceSearchError" class="result-empty">{{ deviceSearchError }}</div>
                  <template v-else-if="deviceResults.length > 0">
                    <button
                      v-for="device in deviceResults"
                      :key="device.id"
                      type="button"
                      class="result-row asset-result"
                      data-search-entity="device"
                      data-ai-context="device.inventory.employee_device"
                      @click="goDevice(device)"
                    >
                      <span class="result-icon"><i class="pi pi-desktop"></i></span>
                      <span class="result-text">
                        <strong>{{ device.user_name || '미지정 사용자' }}</strong>
                        <small>{{ deviceMeta(device) }}</small>
                      </span>
                      <Tag :value="statusLabel(device.status)" :severity="statusSeverity(device.status)" />
                    </button>
                  </template>
                  <div v-else class="result-empty">일치하는 디바이스가 없습니다.</div>
                </section>
              </div>

              <div v-else class="ai-panel">
                <div class="ai-panel-header">
                  <span class="ai-icon"><i class="pi pi-bolt"></i></span>
                  <div>
                    <strong>AI 질의</strong>
                    <small>{{ aiSearchContext }}</small>
                  </div>
                </div>
                <Textarea
                  v-model="aiPrompt"
                  rows="3"
                  class="ai-input"
                  placeholder="예: 재고 노트북 중 보증 만료가 가까운 항목 찾아줘"
                  autoResize
                />
                <div class="ai-actions">
                  <Button label="준비 중" icon="pi pi-bolt" disabled />
                  <Button label="검색으로 보기" icon="pi pi-search" text @click="searchMode = 'search'" />
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="topbar-right">
          <Button
            icon="pi pi-bell"
            text
            rounded
            :badge="unreadCount > 0 ? String(unreadCount) : undefined"
            badgeSeverity="danger"
            aria-label="알림"
            @click="$router.push('/notifications')"
          />
          <span class="user-name">{{ authStore.user?.display_name ?? '사용자' }}</span>
          <Button icon="pi pi-sign-out" text rounded aria-label="로그아웃" @click="authStore.logout()" />
        </div>
      </header>

      <main class="content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Button from 'primevue/button'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import InputText from 'primevue/inputtext'
import Tag from 'primevue/tag'
import Textarea from 'primevue/textarea'
import api from '@/api'
import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'
import { useCategoryStore } from '@/stores/category'
import type { DeviceRecord } from '@/types'
import {
  searchNavigation,
  sidebarSections,
  topNavigationGroups,
  type NavigationGroup,
  type NavigationItem,
} from '@/data/navigation'

type SearchMode = 'search' | 'ai'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const notifStore = useNotificationStore()
const categoryStore = useCategoryStore()

const sidebarCollapsed = ref(false)
const openMenu = ref<string | null>(null)
const searchOpen = ref(false)
const searchMode = ref<SearchMode>('search')
const searchQuery = ref('')
const aiPrompt = ref('')
const deviceResults = ref<DeviceRecord[]>([])
const deviceSearchLoading = ref(false)
const deviceSearchError = ref('')
const deviceSearchTimer = ref<number | null>(null)
const topbarRef = ref<HTMLElement | null>(null)

const unreadCount = computed(() => notifStore.unreadCount)
const trimmedSearchQuery = computed(() => searchQuery.value.trim())
const menuResults = computed(() => searchNavigation(searchQuery.value, 6))
const showDeviceResults = computed(() => trimmedSearchQuery.value.length >= 1)
const totalSearchResultCount = computed(() => menuResults.value.length + deviceResults.value.length)
const aiSearchContext = computed(() => {
  const query = trimmedSearchQuery.value
  if (!query) return '전체 자산 데이터'
  if (/^\d{1,3}(\.\d{1,3}){0,3}$/.test(query)) return 'IP/네트워크 컨텍스트'
  if (query.includes('라이센스') || query.includes('구독')) return '계약/비용 컨텍스트'
  if (query.includes('만료') || query.includes('인증서')) return '만료/보안 컨텍스트'
  return '디바이스/자산 컨텍스트'
})

const statusLabels: Record<string, string> = {
  stock: '재고',
  replaced: '교체됨',
  in_stock: '재고',
  assigned: '사용 중',
  in_maintenance: '유지보수',
  retired: '퇴역',
  disposed: '폐기',
  lost: '분실',
}

const statusSeverityMap: Record<string, string> = {
  stock: 'warn',
  replaced: 'secondary',
  in_stock: 'warn',
  assigned: 'success',
  in_maintenance: 'info',
  retired: 'secondary',
  disposed: 'contrast',
  lost: 'danger',
}

watch(searchQuery, (query) => {
  deviceSearchError.value = ''
  if (deviceSearchTimer.value !== null) {
    window.clearTimeout(deviceSearchTimer.value)
  }

  const nextQuery = query.trim()
  if (nextQuery.length < 2) {
    deviceResults.value = []
    deviceSearchLoading.value = false
    return
  }

  deviceSearchLoading.value = true
  deviceSearchTimer.value = window.setTimeout(() => {
    void fetchDeviceResults(nextQuery)
  }, 250)
})

function toggleMenu(groupKey: string) {
  openMenu.value = openMenu.value === groupKey ? null : groupKey
  searchOpen.value = false
}

function openSearch(mode: SearchMode) {
  searchMode.value = mode
  searchOpen.value = true
  openMenu.value = null
}

function openAiMode() {
  openSearch('ai')
}

function closeOverlays() {
  openMenu.value = null
  searchOpen.value = false
}

function clearSearch() {
  searchQuery.value = ''
  deviceResults.value = []
  deviceSearchError.value = ''
  searchOpen.value = true
  searchMode.value = 'search'
}

function isNavItemActive(item: NavigationItem) {
  if (item.to === '/') return route.path === '/'
  return route.path === item.to || route.path.startsWith(`${item.to}/`)
}

function isGroupActive(group: NavigationGroup) {
  return group.items.some((item) => isNavItemActive(item))
}

function goNavigation(item: NavigationItem) {
  void router.push(item.to)
  closeOverlays()
}

function goDevice(device: DeviceRecord) {
  const query = trimmedSearchQuery.value || device.employee_number || device.serial_number
  void router.push({ path: isNetworkSearch(query) ? '/ip-addresses' : '/devices', query: { search: query } })
  closeOverlays()
}

function submitGlobalSearch() {
  const query = trimmedSearchQuery.value
  if (!query) {
    searchOpen.value = true
    return
  }

  if (deviceResults.value.length > 0) {
    goDevice(deviceResults.value[0])
    return
  }

  if (menuResults.value.length > 0) {
    goNavigation(menuResults.value[0])
    return
  }

  void router.push({ path: isNetworkSearch(query) ? '/ip-addresses' : '/devices', query: { search: query } })
  closeOverlays()
}

function statusLabel(status: string) {
  return statusLabels[status] ?? status
}

function statusSeverity(status: string) {
  return statusSeverityMap[status] ?? 'secondary'
}

function deviceMeta(device: DeviceRecord) {
  return [device.employee_number, device.serial_number, device.ip_address, device.mac_address, device.device_type, device.department, device.factory]
    .filter((value): value is string => Boolean(value))
    .join(' · ')
}

function isNetworkSearch(query: string) {
  const normalized = query.trim()
  return /^\d{1,3}(?:\.\d{1,3}){1,3}$/.test(normalized)
    || /^[0-9a-f]{2}(?:[:-][0-9a-f]{2}){2,5}$/i.test(normalized)
    || normalized.toLocaleLowerCase('ko-KR').includes('mac')
}

async function fetchDeviceResults(query: string) {
  try {
    const { data } = await api.get<{ items: DeviceRecord[] }>('/devices', {
      params: { search: query, page: 1, size: 8 },
    })

    if (trimmedSearchQuery.value === query) {
      deviceResults.value = data.items
    }
  } catch {
    if (trimmedSearchQuery.value === query) {
      deviceResults.value = []
      deviceSearchError.value = '검색 결과를 불러오지 못했습니다.'
    }
  } finally {
    if (trimmedSearchQuery.value === query) {
      deviceSearchLoading.value = false
    }
  }
}

function handleDocumentClick(event: MouseEvent) {
  const target = event.target
  if (!(target instanceof Node)) return
  if (topbarRef.value?.contains(target)) return
  closeOverlays()
}

onMounted(() => {
  document.addEventListener('click', handleDocumentClick)
  void authStore.fetchUser()
  void categoryStore.fetchCategories()
  void notifStore.fetchUnreadCount()
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick)
  if (deviceSearchTimer.value !== null) {
    window.clearTimeout(deviceSearchTimer.value)
  }
})
</script>

<style scoped>
.layout {
  display: flex;
  min-height: 100vh;
  background: var(--color-page);
}

.sidebar {
  width: var(--sidebar-width);
  background: #fff;
  color: #0f172a;
  display: flex;
  flex-direction: column;
  transition: width 0.2s;
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  z-index: 100;
  overflow-y: auto;
  border-right: 1px solid #dbe3ef;
  box-shadow: 1px 0 0 rgba(15, 23, 42, 0.02);
}

.sidebar.collapsed {
  width: 64px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  min-height: 64px;
  padding: 0.9rem 0.9rem;
  border-bottom: 1px solid #e2e8f0;
}

.brand-link {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  color: #0f172a;
  text-decoration: none;
  font-weight: 800;
  font-size: 1rem;
  line-height: 1;
  white-space: nowrap;
}

.brand-link i {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: #2563eb;
  color: #fff;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  padding: 0.85rem 0.75rem 1.25rem;
  gap: 0.75rem;
}

.sidebar-section {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.sidebar-section-label {
  padding: 0.35rem 0.75rem 0.2rem;
  color: #64748b;
  font-size: 0.75rem;
  font-weight: 800;
  line-height: 1.2;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-height: 38px;
  padding: 0.55rem 0.75rem;
  border-radius: 8px;
  color: #475569;
  text-decoration: none;
  font-size: 0.9rem;
  font-weight: 650;
  line-height: 1.2;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s, box-shadow 0.15s;
}

.nav-item:hover {
  background: #f1f5f9;
  color: #0f172a;
}

.nav-item.active,
.nav-item.router-link-active,
.nav-item.router-link-exact-active {
  background: #eef4ff;
  color: #1d4ed8;
  box-shadow: inset 3px 0 0 #2563eb;
}

.nav-item i {
  font-size: 1.05rem;
  min-width: 20px;
  text-align: center;
}

.nav-item-label {
  overflow: hidden;
  text-overflow: ellipsis;
}

.main-area {
  flex: 1;
  margin-left: var(--sidebar-width);
  transition: margin-left 0.2s;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.sidebar.collapsed ~ .main-area {
  margin-left: 64px;
}

.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  min-height: 64px;
  padding: 0.75rem 1.25rem;
  background: rgba(255, 255, 255, 0.98);
  border-bottom: 1px solid #e2e8f0;
  position: sticky;
  top: 0;
  z-index: 50;
  backdrop-filter: blur(10px);
}

.topbar-left {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 1rem;
}

.menu-navbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.menu-group {
  position: relative;
}

.menu-trigger {
  height: 38px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: #334155;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0 0.7rem;
  font: inherit;
  font-size: 0.9rem;
  font-weight: 750;
  line-height: 1;
  cursor: pointer;
}

.menu-trigger:hover,
.menu-trigger.open,
.menu-trigger.active {
  background: #eef4ff;
  border-color: #bfdbfe;
  color: #1d4ed8;
}

.menu-caret {
  font-size: 0.75rem;
}

.menu-popover {
  position: absolute;
  top: calc(100% + 0.5rem);
  left: 0;
  width: 330px;
  padding: 0.55rem;
  border: 1px solid #dbe3ef;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 18px 48px rgba(15, 23, 42, 0.14);
  z-index: 90;
}

.menu-popover-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.35rem 0.45rem 0.55rem;
  border-bottom: 1px solid #eef2f7;
  margin-bottom: 0.35rem;
}

.menu-popover-header span {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  color: #0f172a;
  font-size: 0.88rem;
  font-weight: 800;
}

.menu-popover-header small {
  color: #64748b;
  font-size: 0.75rem;
  font-weight: 700;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.7rem;
  border-radius: 8px;
  color: #1e293b;
  text-decoration: none;
}

.menu-item:hover,
.menu-item.active {
  background: #f1f5f9;
}

.menu-item-icon,
.result-icon,
.ai-icon {
  width: 36px;
  height: 36px;
  flex: 0 0 36px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #e0f2fe;
  color: #0369a1;
}

.menu-item-text,
.result-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.menu-item-text strong,
.result-text strong,
.ai-panel-header strong {
  color: #0f172a;
  font-size: 0.92rem;
  font-weight: 800;
  line-height: 1.25;
}

.menu-item-text small,
.result-text small,
.ai-panel-header small {
  color: #64748b;
  font-size: 0.8rem;
  line-height: 1.4;
}

.search-shell {
  position: relative;
  flex: 1;
  min-width: 280px;
  max-width: 620px;
}

.search-control {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.global-search-field {
  flex: 1;
}

.global-search-field :deep(.p-inputtext) {
  width: 100%;
  height: 40px;
  border-radius: 8px;
  font-size: 0.92rem;
}

.ai-entry-button {
  height: 40px;
  flex-shrink: 0;
}

.search-popover {
  position: absolute;
  top: calc(100% + 0.5rem);
  left: 0;
  right: 0;
  border: 1px solid #dbe3ef;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 18px 48px rgba(15, 23, 42, 0.14);
  padding: 0.85rem;
  z-index: 90;
}

.search-tabs {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 0.65rem;
}

.search-tab {
  height: 32px;
  border: 1px solid #dbe3ef;
  border-radius: 8px;
  background: #fff;
  color: #475569;
  padding: 0 0.75rem;
  font: inherit;
  font-size: 0.85rem;
  font-weight: 700;
  cursor: pointer;
}

.search-tab.active {
  background: #0f172a;
  border-color: #0f172a;
  color: #fff;
}

.search-results {
  display: grid;
  gap: 0.75rem;
  max-height: min(540px, calc(100vh - 180px));
  overflow-y: auto;
}

.result-section {
  display: grid;
  gap: 0.3rem;
}

.result-section-title {
  color: #64748b;
  font-size: 0.78rem;
  font-weight: 800;
  line-height: 1.2;
}

.result-row {
  width: 100%;
  border: 0;
  border-radius: 8px;
  background: transparent;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.7rem;
  text-align: left;
  font: inherit;
  cursor: pointer;
}

.result-row:hover {
  background: #f1f5f9;
}

.asset-result {
  padding-right: 0.4rem;
}

.result-empty {
  border-radius: 8px;
  background: #f8fafc;
  color: #64748b;
  font-size: 0.85rem;
  padding: 0.8rem;
}

.ai-panel {
  display: grid;
  gap: 0.75rem;
}

.ai-panel-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.ai-input {
  width: 100%;
}

.ai-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.4rem;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}

.user-name {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.9rem;
  font-weight: 600;
  color: #475569;
}

.content {
  padding: 0;
  flex: 1;
  min-width: 0;
  overflow: visible;
}

@media (max-width: 1200px) {
  .topbar {
    align-items: flex-start;
  }

  .topbar-left {
    flex-direction: column;
    align-items: stretch;
  }

  .menu-navbar {
    overflow-x: auto;
    padding-bottom: 0.1rem;
  }

  .search-shell {
    max-width: none;
  }
}

@media (max-width: 760px) {
  .sidebar {
    width: 64px;
  }

  .sidebar-header {
    justify-content: center;
  }

  .sidebar-header :deep(.p-button) {
    display: none;
  }

  .sidebar-section-label,
  .brand-link span,
  .nav-item span {
    display: none;
  }

  .main-area,
  .sidebar.collapsed ~ .main-area {
    margin-left: 64px;
  }

  .topbar {
    flex-direction: column;
    align-items: stretch;
  }

  .topbar-right {
    justify-content: flex-end;
  }

  .menu-popover {
    position: fixed;
    left: 72px;
    right: 0.75rem;
    width: auto;
  }

  .search-popover {
    position: fixed;
    left: 72px;
    right: 0.75rem;
    top: 118px;
  }

  .content {
    padding: 0;
  }
}
</style>
