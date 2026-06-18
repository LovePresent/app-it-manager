<template>
  <div>
    <div class="page-header">
      <h1>유지보수 기록</h1>
      <Button label="기록 추가" icon="pi pi-plus" @click="openCreate" />
    </div>
    <div class="filters-row">
      <Select v-model="filterStatus" :options="['scheduled','in_progress','completed','cancelled']" placeholder="상태" showClear @change="load" />
    </div>
    <div class="card">
      <DataTable :value="items" :loading="loading" stripedRows size="small">
        <Column header="자산"><template #body="{data}">{{ data.asset_name || data.asset_tag || `#${data.asset_id}` }}</template></Column>
        <Column field="maintenance_type" header="유형" />
        <Column field="description" header="내용" />
        <Column field="technician" header="담당자" />
        <Column field="scheduled_date" header="예정일" sortable />
        <Column field="completed_date" header="완료일" sortable />
        <Column field="cost" header="비용"><template #body="{data}">{{data.cost?`₩${data.cost.toLocaleString()}`:'-'}}</template></Column>
        <Column field="status" header="상태"><template #body="{data}"><Tag :value="data.status" /></template></Column>
        <Column style="width:80px">
          <template #body="{data}">
            <Button icon="pi pi-pencil" text rounded size="small" @click="startEdit(data)" />
            <Button icon="pi pi-trash" text rounded size="small" severity="danger" @click="remove(data.id)" />
          </template>
        </Column>
      </DataTable>
      <Paginator :rows="size" :totalRecords="total" :first="(page-1)*size" @page="onPage" />
    </div>
    <Dialog v-model:visible="showCreate" :header="editId !== null ? '수정':'추가'" :modal="true" style="width:550px">
      <div class="form-grid">
        <div class="field"><label>자산 ID *</label><InputNumber v-model="form.asset_id" fluid /></div>
        <div class="field"><label>유형</label><Select v-model="form.maintenance_type" :options="['preventive','corrective','upgrade']" fluid /></div>
        <div class="field full"><label>내용</label><Textarea v-model="form.description" rows="2" fluid /></div>
        <div class="field"><label>담당자</label><InputText v-model="form.technician" fluid /></div>
        <div class="field"><label>예정일</label><InputText v-model="form.scheduled_date" type="date" fluid /></div>
        <div class="field"><label>완료일</label><InputText v-model="form.completed_date" type="date" fluid /></div>
        <div class="field"><label>비용</label><InputNumber v-model="form.cost" mode="currency" currency="KRW" locale="ko-KR" fluid /></div>
        <div class="field"><label>상태</label><Select v-model="form.status" :options="['scheduled','in_progress','completed','cancelled']" fluid /></div>
        <div class="field"><label>벤더 ID</label><InputNumber v-model="form.vendor_id" fluid /></div>
        <div class="field full"><label>비고</label><Textarea v-model="form.notes" rows="2" fluid /></div>
      </div>
      <template #footer>
        <Button label="취소" severity="secondary" @click="showCreate=false" />
        <Button :label="editId !== null ? '수정':'저장'" @click="save" />
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

const toast=useToast()
const items=ref<any[]>([]);const loading=ref(false);const page=ref(1);const size=ref(20);const total=ref(0)
const filterStatus=ref<string|null>(null)
const showCreate=ref(false);const editId=ref<number|null>(null)
const form=ref<any>(emptyForm())

async function load(){loading.value=true;try{const params:any={page:page.value,size:size.value};if(filterStatus.value)params.status=filterStatus.value;const{data}=await api.get('/maintenance',{params});items.value=data.items;total.value=data.total}finally{loading.value=false}}
function onPage(e:any){page.value=e.page+1;load()}
function emptyForm(){return {asset_id:null,maintenance_type:'preventive',description:'',cost:null,scheduled_date:'',completed_date:'',vendor_id:null,technician:'',status:'scheduled',notes:''}}
function openCreate(){editId.value=null;form.value=emptyForm();showCreate.value=true}
function startEdit(item:any){editId.value=item.id;form.value={...item};showCreate.value=true}
function payload(){
  const base:any={maintenance_type:form.value.maintenance_type,description:form.value.description,cost:form.value.cost,scheduled_date:form.value.scheduled_date || null,completed_date:form.value.completed_date || null,vendor_id:form.value.vendor_id,technician:form.value.technician,status:form.value.status,notes:form.value.notes}
  if(editId.value === null) base.asset_id=form.value.asset_id
  return base
}
async function save(){try{if(editId.value !== null){await api.put(`/maintenance/${editId.value}`,payload())}else{await api.post('/maintenance',payload())}toast.add({severity:'success',summary:'저장 완료',life:3000});showCreate.value=false;editId.value=null;form.value=emptyForm();load()}catch(err:any){toast.add({severity:'error',summary:'오류',detail:err.response?.data?.detail??'실패',life:5000})}}
async function remove(id:number){await api.delete(`/maintenance/${id}`);load()}
onMounted(load)
</script>
<style scoped>.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.field{display:flex;flex-direction:column;gap:0.25rem}.field.full{grid-column:1/-1}.field label{font-size:0.85rem;font-weight:500;color:#475569}</style>
