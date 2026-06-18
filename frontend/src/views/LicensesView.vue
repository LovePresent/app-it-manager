<template>
  <div>
    <div class="page-header">
      <h1>소프트웨어 라이센스</h1>
      <Button label="라이센스 추가" icon="pi pi-plus" @click="openCreate" />
    </div>
    <div class="filters-row">
      <IconField><InputIcon class="pi pi-search" /><InputText v-model="search" placeholder="검색" @keyup.enter="load" /></IconField>
    </div>
    <div class="card">
      <DataTable :value="items" :loading="loading" stripedRows size="small">
        <Column header="자산">
          <template #body="{ data }">{{ data.asset_name || data.asset_tag || `#${data.asset_id}` }}</template>
        </Column>
        <Column field="vendor_name" header="벤더" />
        <Column field="license_type" header="유형" />
        <Column header="사용량"><template #body="{ data }">{{ data.seats_used ?? 0 }}/{{ data.seats_total ?? '-' }}</template></Column>
        <Column field="expiry_date" header="만료일" sortable />
        <Column style="width:80px">
          <template #body="{ data }">
            <Button icon="pi pi-pencil" text rounded size="small" @click="startEdit(data)" />
            <Button icon="pi pi-trash" text rounded size="small" severity="danger" @click="remove(data.id)" />
          </template>
        </Column>
      </DataTable>
      <Paginator :rows="size" :totalRecords="total" :first="(page-1)*size" @page="onPage" />
    </div>

    <Dialog v-model:visible="showCreate" :header="editId !== null ? '라이센스 수정' : '라이센스 추가'" :modal="true" style="width:550px">
      <div class="form-grid">
        <div class="field"><label>자산 ID *</label><InputNumber v-model="form.asset_id" fluid /></div>
        <div class="field"><label>벤더 ID</label><InputNumber v-model="form.vendor_id" fluid /></div>
        <div class="field"><label>라이센스 키</label><InputText v-model="form.license_key" fluid /></div>
        <div class="field"><label>유형</label><InputText v-model="form.license_type" fluid /></div>
        <div class="field"><label>총 좌석수</label><InputNumber v-model="form.seats_total" fluid /></div>
        <div class="field"><label>사용 좌석수</label><InputNumber v-model="form.seats_used" fluid /></div>
        <div class="field"><label>만료일</label><InputText v-model="form.expiry_date" type="date" fluid /></div>
        <div class="field full"><label>비고</label><Textarea v-model="form.notes" rows="2" fluid /></div>
      </div>
      <template #footer>
        <Button label="취소" severity="secondary" @click="showCreate = false" />
        <Button :label="editId !== null ? '수정' : '저장'" @click="save" />
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Paginator from 'primevue/paginator'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Textarea from 'primevue/textarea'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'
import api from '@/api'
import type { SoftwareLicense } from '@/types'

const toast = useToast()
const items = ref<SoftwareLicense[]>([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)
const search = ref('')
const showCreate = ref(false)
const editId = ref<number | null>(null)
const form = ref<any>(emptyForm())

async function load() {
  loading.value = true
  try {
    const params: any = { page: page.value, size: size.value }
    if (search.value) params.search = search.value
    const { data } = await api.get('/licenses', { params })
    items.value = data.items; total.value = data.total
  } finally { loading.value = false }
}
function onPage(e: any) { page.value = e.page + 1; load() }
function emptyForm() { return { asset_id: null, vendor_id: null, license_key: '', license_type: '', seats_total: 1, seats_used: 0, expiry_date: '', notes: '' } }
function openCreate() { editId.value = null; form.value = emptyForm(); showCreate.value = true }
function startEdit(item: any) { editId.value = item.id; form.value = { ...item }; showCreate.value = true }
function payload() {
  const base: any = {
    license_key: form.value.license_key,
    license_type: form.value.license_type,
    seats_total: form.value.seats_total,
    seats_used: form.value.seats_used,
    expiry_date: form.value.expiry_date || null,
    vendor_id: form.value.vendor_id,
    notes: form.value.notes,
  }
  if (editId.value === null) base.asset_id = form.value.asset_id
  return base
}
async function save() {
  try {
    if (editId.value !== null) { await api.put(`/licenses/${editId.value}`, payload()) }
    else { await api.post('/licenses', payload()) }
    toast.add({ severity: 'success', summary: '저장 완료', life: 3000 })
    showCreate.value = false; editId.value = null
    form.value = emptyForm()
    load()
  } catch (err: any) { toast.add({ severity: 'error', summary: '오류', detail: err.response?.data?.detail ?? '실패', life: 5000 }) }
}
async function remove(id: number) { await api.delete(`/licenses/${id}`); load() }
onMounted(load)
</script>
<style scoped>
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
.field{display:flex;flex-direction:column;gap:0.25rem}
.field.full{grid-column:1/-1}
.field label{font-size:0.85rem;font-weight:500;color:#475569}
</style>
