<template>
  <div>
    <div class="page-header">
      <h1>자산 목록</h1>
      <div style="display:flex;gap:0.5rem">
        <Button label="엑셀 내보내기" icon="pi pi-download" severity="secondary" @click="exportExcel" />
        <Button label="자산 추가" icon="pi pi-plus" @click="showCreate = true" />
      </div>
    </div>

    <div class="filters-row">
      <IconField>
        <InputIcon class="pi pi-search" />
        <InputText v-model="search" placeholder="검색 (이름, 태그, 시리얼)" @keyup.enter="loadAssets" />
      </IconField>
      <Select v-model="filterCategory" :options="categories" optionLabel="name" optionValue="id" placeholder="카테고리" showClear @change="loadAssets" />
      <Select v-model="filterStatus" :options="statusOptions" optionLabel="label" optionValue="value" placeholder="상태" showClear @change="loadAssets" />
    </div>

    <div class="card">
      <DataTable :value="assets" :loading="loading" stripedRows size="small" @row-click="goDetail">
        <Column field="asset_tag" header="자산 태그" sortable style="width:120px" />
        <Column field="name" header="이름" sortable />
        <Column field="category_name" header="카테고리" sortable />
        <Column field="status" header="상태">
          <template #body="{ data }">
            <Tag :severity="statusSeverity(data.status)" :value="statusLabel(data.status)" />
          </template>
        </Column>
        <Column field="assigned_to_name" header="사용자" />
        <Column field="location_name" header="위치" />
        <Column field="purchase_cost" header="취득가">
          <template #body="{ data }">{{ data.purchase_cost ? `₩${data.purchase_cost.toLocaleString()}` : '-' }}</template>
        </Column>
      </DataTable>
      <Paginator :rows="size" :totalRecords="total" :first="(page - 1) * size" @page="onPage" />
    </div>

    <Dialog v-model:visible="showCreate" header="자산 추가" :modal="true" style="width:600px">
      <div class="form-grid">
        <div class="field"><label>이름 *</label><InputText v-model="form.name" fluid /></div>
        <div class="field"><label>카테고리 *</label><Select v-model="form.category_id" :options="categories" optionLabel="name" optionValue="id" fluid /></div>
        <div class="field"><label>시리얼 번호</label><InputText v-model="form.serial_number" fluid /></div>
        <div class="field"><label>모델</label><InputText v-model="form.model" fluid /></div>
        <div class="field"><label>제조사</label><InputText v-model="form.manufacturer" fluid /></div>
        <div class="field"><label>취득일</label><InputText v-model="form.purchase_date" type="date" fluid /></div>
        <div class="field"><label>취득가</label><InputNumber v-model="form.purchase_cost" mode="currency" currency="KRW" locale="ko-KR" fluid /></div>
        <div class="field"><label>보증 만료</label><InputText v-model="form.warranty_expiry" type="date" fluid /></div>
        <div class="field full"><label>비고</label><Textarea v-model="form.notes" rows="2" fluid /></div>
      </div>
      <template #footer>
        <Button label="취소" severity="secondary" @click="showCreate = false" />
        <Button label="저장" @click="createAsset" :loading="saving" />
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Paginator from 'primevue/paginator'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Textarea from 'primevue/textarea'
import Select from 'primevue/select'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import Dialog from 'primevue/dialog'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import api from '@/api'
import { useCategoryStore } from '@/stores/category'
import type { Asset } from '@/types'

const router = useRouter()
const toast = useToast()
const categoryStore = useCategoryStore()

const assets = ref<Asset[]>([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)
const search = ref('')
const filterCategory = ref<number | null>(null)
const filterStatus = ref<string | null>(null)
const showCreate = ref(false)
const saving = ref(false)

const categories = categoryStore.categories

const statusOptions = [
  { label: '재고', value: 'in_stock' },
  { label: '사용 중', value: 'assigned' },
  { label: '유지보수', value: 'in_maintenance' },
  { label: '퇴역', value: 'retired' },
  { label: '폐기', value: 'disposed' },
  { label: '분실', value: 'lost' },
]

const form = ref<any>({ name: '', category_id: null, serial_number: '', model: '', manufacturer: '', purchase_date: '', purchase_cost: null, warranty_expiry: '', notes: '' })

function statusLabel(s: string) {
  return statusOptions.find((o) => o.value === s)?.label ?? s
}

function statusSeverity(s: string): any {
  const map: Record<string, string> = { in_stock: 'warn', assigned: 'success', in_maintenance: 'info', retired: 'secondary', disposed: 'contrast', lost: 'danger' }
  return map[s] ?? 'secondary'
}

async function loadAssets() {
  loading.value = true
  try {
    const params: any = { page: page.value, size: size.value }
    if (search.value) params.search = search.value
    if (filterCategory.value) params.category_id = filterCategory.value
    if (filterStatus.value) params.status = filterStatus.value
    const { data } = await api.get('/assets', { params })
    assets.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function onPage(e: any) {
  page.value = e.page + 1
  loadAssets()
}

function goDetail(e: any) {
  router.push(`/assets/${e.data.id}`)
}

async function createAsset() {
  saving.value = true
  try {
    await api.post('/assets', form.value)
    toast.add({ severity: 'success', summary: '성공', detail: '자산이 추가되었습니다.', life: 3000 })
    showCreate.value = false
    form.value = { name: '', category_id: null, serial_number: '', model: '', manufacturer: '', purchase_date: '', purchase_cost: null, warranty_expiry: '', notes: '' }
    loadAssets()
  } catch (err: any) {
    toast.add({ severity: 'error', summary: '오류', detail: err.response?.data?.detail ?? '저장 실패', life: 5000 })
  } finally {
    saving.value = false
  }
}

async function exportExcel() {
  const { data } = await api.get('/import-export/export', { responseType: 'blob' })
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = 'assets.xlsx'
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(() => {
  categoryStore.fetchCategories()
  loadAssets()
})
</script>

<style scoped>
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.field.full {
  grid-column: 1 / -1;
}
.field label {
  font-size: 0.85rem;
  font-weight: 500;
  color: #475569;
}
</style>
