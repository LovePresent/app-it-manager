<template>
  <div>
    <div class="page-header">
      <h1>SaaS/클라우드 구독</h1>
      <Button label="구독 추가" icon="pi pi-plus" @click="openCreate" />
    </div>
    <div class="card">
      <DataTable :value="items" :loading="loading" stripedRows size="small">
        <Column header="자산">
          <template #body="{ data }">{{ data.asset_name || data.asset_tag || `#${data.asset_id}` }}</template>
        </Column>
        <Column field="provider" header="공급자" />
        <Column field="plan" header="플랜" />
        <Column field="billing_cycle" header="청구 주기" />
        <Column field="monthly_cost" header="월 비용"><template #body="{ data }">{{ data.monthly_cost ? `₩${data.monthly_cost.toLocaleString()}` : '-' }}</template></Column>
        <Column field="renewal_date" header="갱신일" sortable />
        <Column field="auto_renew" header="자동 갱신"><template #body="{ data }"><Tag :severity="data.auto_renew ? 'success' : 'secondary'" :value="data.auto_renew ? '예' : '아니오'" /></template></Column>
        <Column style="width:80px">
          <template #body="{ data }">
            <Button icon="pi pi-pencil" text rounded size="small" @click="startEdit(data)" />
            <Button icon="pi pi-trash" text rounded size="small" severity="danger" @click="remove(data.id)" />
          </template>
        </Column>
      </DataTable>
      <Paginator :rows="size" :totalRecords="total" :first="(page-1)*size" @page="onPage" />
    </div>
    <Dialog v-model:visible="showCreate" :header="editId !== null ? '구독 수정' : '구독 추가'" :modal="true" style="width:550px">
      <div class="form-grid">
        <div class="field"><label>자산 ID *</label><InputNumber v-model="form.asset_id" fluid /></div>
        <div class="field"><label>공급자</label><InputText v-model="form.provider" fluid /></div>
        <div class="field"><label>플랜</label><InputText v-model="form.plan" fluid /></div>
        <div class="field"><label>청구 주기</label><Select v-model="form.billing_cycle" :options="['monthly','yearly']" fluid /></div>
        <div class="field"><label>계정 URL</label><InputText v-model="form.account_url" fluid /></div>
        <div class="field"><label>갱신일</label><InputText v-model="form.renewal_date" type="date" fluid /></div>
        <div class="field"><label>월 비용</label><InputNumber v-model="form.monthly_cost" mode="currency" currency="KRW" locale="ko-KR" fluid /></div>
        <div class="field"><label>자동 갱신</label><Checkbox v-model="form.auto_renew" :binary="true" /></div>
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
import Select from 'primevue/select'
import Checkbox from 'primevue/checkbox'
import Tag from 'primevue/tag'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'
import api from '@/api'

const toast = useToast()
const items = ref<any[]>([])
const loading = ref(false)
const page = ref(1); const size = ref(20); const total = ref(0)
const showCreate = ref(false); const editId = ref<number|null>(null)
const form = ref<any>(emptyForm())

async function load() { loading.value=true; try { const {data}=await api.get('/subscriptions',{params:{page:page.value,size:size.value}}); items.value=data.items; total.value=data.total } finally { loading.value=false } }
function onPage(e:any){page.value=e.page+1;load()}
function emptyForm(){return { asset_id:null, provider:'', plan:'', billing_cycle:'monthly', monthly_cost:null, renewal_date:'', auto_renew:false, account_url:'', notes:'' }}
function openCreate(){editId.value=null;form.value=emptyForm();showCreate.value=true}
function startEdit(item:any){editId.value=item.id;form.value={...item};showCreate.value=true}
function payload(){
  const base:any={provider:form.value.provider,plan:form.value.plan,billing_cycle:form.value.billing_cycle,monthly_cost:form.value.monthly_cost,renewal_date:form.value.renewal_date || null,auto_renew:form.value.auto_renew,account_url:form.value.account_url,notes:form.value.notes}
  if(editId.value === null) base.asset_id=form.value.asset_id
  return base
}
async function save(){try{if(editId.value !== null){await api.put(`/subscriptions/${editId.value}`,payload())}else{await api.post('/subscriptions',payload())}toast.add({severity:'success',summary:'저장 완료',life:3000});showCreate.value=false;editId.value=null;form.value=emptyForm();load()}catch(err:any){toast.add({severity:'error',summary:'오류',detail:err.response?.data?.detail??'실패',life:5000})}}
async function remove(id:number){await api.delete(`/subscriptions/${id}`);load()}
onMounted(load)
</script>
<style scoped>
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.field{display:flex;flex-direction:column;gap:0.25rem}.field.full{grid-column:1/-1}.field label{font-size:0.85rem;font-weight:500;color:#475569}
</style>
