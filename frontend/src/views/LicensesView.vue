<template>
  <div>
    <div class="page-header">
      <h1>소프트웨어 라이센스</h1>
      <Button label="라이센스 추가" icon="pi pi-plus" @click="showCreate = true" />
    </div>
    <div class="filters-row">
      <IconField><InputIcon class="pi pi-search" /><InputText v-model="search" placeholder="검색" @keyup.enter="load" /></IconField>
    </div>
    <div class="card">
      <DataTable :value="items" :loading="loading" stripedRows size="small">
        <Column field="name" header="이름" sortable />
        <Column field="vendor" header="벤더" />
        <Column field="license_type" header="유형" />
        <Column header="사용량"><template #body="{ data }">{{ data.used_seats }}/{{ data.total_seats }}</template></Column>
        <Column field="expiry_date" header="만료일" sortable />
        <Column field="cost" header="비용"><template #body="{ data }">{{ data.cost ? `₩${data.cost.toLocaleString()}` : '-' }}</template></Column>
        <Column style="width:80px">
          <template #body="{ data }">
            <Button icon="pi pi-pencil" text rounded size="small" @click="startEdit(data)" />
            <Button icon="pi pi-trash" text rounded size="small" severity="danger" @click="remove(data.id)" />
          </template>
        </Column>
      </DataTable>
      <Paginator :rows="size" :totalRecords="total" :first="(page-1)*size" @page="onPage" />
    </div>

    <Dialog v-model:visible="showCreate" :header="editId ? '라이센스 수정' : '라이센스 추가'" :modal="true" style="width:550px">
      <div class="form-grid">
        <div class="field"><label>이름 *</label><InputText v-model="form.name" fluid /></div>
        <div class="field"><label>벤더</label><InputText v-model="form.vendor" fluid /></div>
        <div class="field"><label>라이센스 키</label><InputText v-model="form.license_key" fluid /></div>
        <div class="field"><label>유형</label><InputText v-model="form.license_type" fluid /></div>
        <div class="field"><label>총 좌석수</label><InputNumber v-model="form.total_seats" fluid /></div>
        <div class="field"><label>사용 좌석수</label><InputNumber v-model="form.used_seats" fluid /></div>
        <div class="field"><label>구매일</label><InputText v-model="form.purchase_date" type="date" fluid /></div>
        <div class="field"><label>만료일</label><InputText v-model="form.expiry_date" type="date" fluid /></div>
        <div class="field"><label>비용</label><InputNumber v-model="form.cost" mode="currency" currency="KRW" locale="ko-KR" fluid /></div>
        <div class="field full"><label>비고</label><Textarea v-model="form.notes" rows="2" fluid /></div>
      </div>
      <template #footer>
        <Button label="취소" severity="secondary" @click="showCreate = false" />
        <Button :label="editId ? '수정' : '저장'" @click="save" />
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
const form = ref<any>({ name: '', vendor: '', license_key: '', license_type: '', total_seats: 1, used_seats: 0, purchase_date: '', expiry_date: '', cost: null, notes: '' })

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
function startEdit(item: any) { editId.value = item.id; form.value = { ...item }; showCreate.value = true }
async function save() {
  try {
    if (editId.value) { await api.put(`/licenses/${editId.value}`, form.value) }
    else { await api.post('/licenses', form.value) }
    toast.add({ severity: 'success', summary: '저장 완료', life: 3000 })
    showCreate.value = false; editId.value = null
    form.value = { name: '', vendor: '', license_key: '', license_type: '', total_seats: 1, used_seats: 0, purchase_date: '', expiry_date: '', cost: null, notes: '' }
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
