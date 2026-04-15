<template>
  <div>
    <div class="page-header">
      <h1>대시보드</h1>
    </div>

    <div class="stat-grid">
      <div class="stat-card" v-for="s in statCards" :key="s.label">
        <div class="icon" :style="{ background: s.bg, color: s.color }">
          <i :class="s.icon"></i>
        </div>
        <div>
          <div class="value">{{ s.value }}</div>
          <div class="label">{{ s.label }}</div>
        </div>
      </div>
    </div>

    <div class="chart-row">
      <div class="card chart-card">
        <h3>카테고리별 자산</h3>
        <Doughnut v-if="categoryChartData" :data="categoryChartData" :options="chartOptions" />
      </div>
      <div class="card chart-card">
        <h3>상태별 자산</h3>
        <Doughnut v-if="statusChartData" :data="statusChartData" :options="chartOptions" />
      </div>
    </div>

    <div class="card" style="margin-top: 1.5rem" v-if="expiring.length > 0">
      <h3 style="margin-bottom: 1rem">만료 임박 항목</h3>
      <DataTable :value="expiring" :rows="10" stripedRows size="small">
        <Column field="type" header="유형" />
        <Column field="name" header="이름" />
        <Column field="expiry_date" header="만료일" />
        <Column field="days_remaining" header="남은 일수">
          <template #body="{ data }">
            <Tag :severity="data.days_remaining <= 7 ? 'danger' : 'warn'" :value="`${data.days_remaining}일`" />
          </template>
        </Column>
      </DataTable>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Doughnut } from 'vue-chartjs'
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import api from '@/api'
import type { DashboardStats } from '@/types'

ChartJS.register(ArcElement, Tooltip, Legend)

const stats = ref<DashboardStats | null>(null)
const categoryData = ref<{ name: string; count: number }[]>([])
const statusData = ref<{ status: string; count: number }[]>([])
const expiring = ref<any[]>([])

const chartOptions = { responsive: true, plugins: { legend: { position: 'bottom' as const } } }

const statCards = computed(() => {
  if (!stats.value) return []
  const s = stats.value
  return [
    { label: '전체 자산', value: s.total_assets, icon: 'pi pi-box', bg: '#eff6ff', color: '#3b82f6' },
    { label: '사용 중', value: s.assigned_assets, icon: 'pi pi-user', bg: '#f0fdf4', color: '#22c55e' },
    { label: '재고', value: s.in_stock_assets, icon: 'pi pi-inbox', bg: '#fefce8', color: '#eab308' },
    { label: '유지보수 중', value: s.in_maintenance_assets, icon: 'pi pi-wrench', bg: '#fef2f2', color: '#ef4444' },
    { label: '라이센스', value: s.total_licenses, icon: 'pi pi-key', bg: '#f5f3ff', color: '#8b5cf6' },
    { label: '만료 임박 라이센스', value: s.expiring_licenses, icon: 'pi pi-exclamation-triangle', bg: '#fff7ed', color: '#f97316' },
    { label: '월간 구독 비용', value: `₩${(s.total_monthly_cost ?? 0).toLocaleString()}`, icon: 'pi pi-won', bg: '#ecfdf5', color: '#10b981' },
    { label: '소모품 부족', value: s.low_stock_consumables, icon: 'pi pi-shopping-bag', bg: '#fef2f2', color: '#ef4444' },
  ]
})

const COLORS = ['#3b82f6', '#22c55e', '#eab308', '#ef4444', '#8b5cf6', '#f97316', '#06b6d4', '#ec4899', '#14b8a6', '#6366f1']

const categoryChartData = computed(() => {
  if (!categoryData.value.length) return null
  return {
    labels: categoryData.value.map((c) => c.name),
    datasets: [{ data: categoryData.value.map((c) => c.count), backgroundColor: COLORS }],
  }
})

const STATUS_LABELS: Record<string, string> = {
  in_stock: '재고', assigned: '사용 중', in_maintenance: '유지보수', retired: '퇴역', disposed: '폐기', lost: '분실',
}
const STATUS_COLORS: Record<string, string> = {
  in_stock: '#eab308', assigned: '#22c55e', in_maintenance: '#f97316', retired: '#94a3b8', disposed: '#64748b', lost: '#ef4444',
}

const statusChartData = computed(() => {
  if (!statusData.value.length) return null
  return {
    labels: statusData.value.map((s) => STATUS_LABELS[s.status] ?? s.status),
    datasets: [{ data: statusData.value.map((s) => s.count), backgroundColor: statusData.value.map((s) => STATUS_COLORS[s.status] ?? '#94a3b8') }],
  }
})

onMounted(async () => {
  const [statsRes, catRes, statusRes, expiringRes] = await Promise.all([
    api.get('/dashboard/stats'),
    api.get('/dashboard/by-category'),
    api.get('/dashboard/by-status'),
    api.get('/dashboard/expiring'),
  ])
  stats.value = statsRes.data
  categoryData.value = catRes.data
  statusData.value = statusRes.data
  expiring.value = expiringRes.data
})
</script>

<style scoped>
.chart-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}
.chart-card {
  padding: 1.5rem;
}
.chart-card h3 {
  margin-bottom: 1rem;
  font-size: 1rem;
}
</style>
