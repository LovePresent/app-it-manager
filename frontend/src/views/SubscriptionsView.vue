<template>
  <div>
    <div class="page-header">
      <h1>SaaS/클라우드 구독</h1>
      <Button label="구독 추가" icon="pi pi-plus" @click="showCreate = true" />
    </div>
    <div class="card">
      <DataTable :value="items" :loading="loading" stripedRows size="small">
        <Column field="service_name" header="서비스명" sortable />
        <Column field="provider" header="공급자" />
        <Column field="plan" header="플랜" />
        <Column field="monthly_cost" header="월 비용"><template #body="{ data }">{{ data.monthly_cost ? `₩${data.monthly_cost.toLocaleString()}` : '-' }}</template></Column>
        <Column field="renewal_date" header="갱신일" sortable />
        <Column field="status" header="상태"><template #body="{ data }"><Tag :value="data.status" /></template></Column>
        <Column style="width:80px">
          <template #body="{ data }">
            <Button icon="pi pi-pencil" text rounded size="small" @click="startEdit(data)" />
            <Button icon="pi pi-trash" text rounded size="small" severity="danger" @click="remove(data.id)" />
          </template>
        </Column>
      </DataTable>
      <Paginator :rows="size" :totalRecords="total" :first="(page-1)*size" @page="onPage" />
    </div>
    <Dialog v-model:visible="showCreate" :header="editId ? '구독 수정' : '구독 추가'" :modal="true" style="width:550px">
      <div class="form-grid">
        <div class="field"><label>서비스명 *</label><InputText v-model="form.service_name" fluid /></div>
        <div class="field"><label>공급자</label><InputText v-model="form.provider" fluid /></div>
        <div class="field"><label>플랜</label><InputText v-model="form.plan" fluid /></div>
        <div class="field"><label>계정 이메일</label><InputText v-model="form.account_email" fluid /></div>
        <div class="field"><label>시작일</label><InputText v-model="form.start_date" type="date" fluid /></div>
        <div class="field"><label>갱신일</label><InputText v-model="form.renewal_date" type="date" fluid /></div>
        <div class="field"><label>월 비용</label><InputNumber v-model="form.monthly_cost" mode="currency" currency="KRW" locale="ko-KR" fluid /></div>
        <div class="field"><label>연 비용</label><InputNumber v-model="form.annual_cost" mode="currency" currency="KRW" locale="ko-KR" fluid /></div>
        <div class="field"><label>상태</label><Select v-model="form.status" :options="['active','inactive','cancelled']" fluid /></div>
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
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'
import api from '@/api'

const toast = useToast()
const items = ref<any[]>([])
const loading = ref(false)
const page = ref(1); const size = ref(20); const total = ref(0)
const showCreate = ref(false); const editId = ref<number|null>(null)
const form = ref<any>({ service_name:'', provider:'', plan:'', account_email:'', start_date:'', renewal_date:'', monthly_cost:null, annual_cost:null, status:'active', notes:'' })

async function load() { loading.value=true; try { const {data}=await api.get('/subscriptions',{params:{page:page.value,size:size.value}}); items.value=data.items; total.value=data.total } finally { loading.value=false } }
function onPage(e:any){page.value=e.page+1;load()}
function startEdit(item:any){editId.value=item.id;form.value={...item};showCreate.value=true}
async function save(){try{if(editId.value){await api.put(`/subscriptions/${editId.value}`,form.value)}else{await api.post('/subscriptions',form.value)}toast.add({severity:'success',summary:'저장 완료',life:3000});showCreate.value=false;editId.value=null;load()}catch(err:any){toast.add({severity:'error',summary:'오류',detail:err.response?.data?.detail??'실패',life:5000})}}
async function remove(id:number){await api.delete(`/subscriptions/${id}`);load()}
onMounted(load)
</script>
<style scoped>
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.field{display:flex;flex-direction:column;gap:0.25rem}.field.full{grid-column:1/-1}.field label{font-size:0.85rem;font-weight:500;color:#475569}
</style>
