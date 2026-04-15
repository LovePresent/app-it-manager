<template>
  <div>
    <div class="page-header">
      <h1>유지보수 기록</h1>
      <Button label="기록 추가" icon="pi pi-plus" @click="showCreate = true" />
    </div>
    <div class="filters-row">
      <Select v-model="filterStatus" :options="['scheduled','in_progress','completed','cancelled']" placeholder="상태" showClear @change="load" />
    </div>
    <div class="card">
      <DataTable :value="items" :loading="loading" stripedRows size="small">
        <Column field="asset_name" header="자산" />
        <Column field="type" header="유형" />
        <Column field="description" header="내용" />
        <Column field="performed_by" header="담당자" />
        <Column field="performed_date" header="수행일" sortable />
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
    <Dialog v-model:visible="showCreate" :header="editId?'수정':'추가'" :modal="true" style="width:550px">
      <div class="form-grid">
        <div class="field"><label>자산 ID *</label><InputNumber v-model="form.asset_id" fluid /></div>
        <div class="field"><label>유형</label><InputText v-model="form.type" fluid /></div>
        <div class="field full"><label>내용</label><Textarea v-model="form.description" rows="2" fluid /></div>
        <div class="field"><label>담당자</label><InputText v-model="form.performed_by" fluid /></div>
        <div class="field"><label>수행일</label><InputText v-model="form.performed_date" type="date" fluid /></div>
        <div class="field"><label>비용</label><InputNumber v-model="form.cost" mode="currency" currency="KRW" locale="ko-KR" fluid /></div>
        <div class="field"><label>상태</label><Select v-model="form.status" :options="['scheduled','in_progress','completed','cancelled']" fluid /></div>
        <div class="field"><label>다음 유지보수일</label><InputText v-model="form.next_maintenance_date" type="date" fluid /></div>
        <div class="field full"><label>비고</label><Textarea v-model="form.notes" rows="2" fluid /></div>
      </div>
      <template #footer>
        <Button label="취소" severity="secondary" @click="showCreate=false" />
        <Button :label="editId?'수정':'저장'" @click="save" />
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
const form=ref<any>({asset_id:null,type:'',description:'',performed_by:'',performed_date:'',cost:null,status:'scheduled',next_maintenance_date:'',notes:''})

async function load(){loading.value=true;try{const params:any={page:page.value,size:size.value};if(filterStatus.value)params.status=filterStatus.value;const{data}=await api.get('/maintenance',{params});items.value=data.items;total.value=data.total}finally{loading.value=false}}
function onPage(e:any){page.value=e.page+1;load()}
function startEdit(item:any){editId.value=item.id;form.value={...item};showCreate.value=true}
async function save(){try{if(editId.value){await api.put(`/maintenance/${editId.value}`,form.value)}else{await api.post('/maintenance',form.value)}toast.add({severity:'success',summary:'저장 완료',life:3000});showCreate.value=false;editId.value=null;load()}catch(err:any){toast.add({severity:'error',summary:'오류',detail:err.response?.data?.detail??'실패',life:5000})}}
async function remove(id:number){await api.delete(`/maintenance/${id}`);load()}
onMounted(load)
</script>
<style scoped>.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.field{display:flex;flex-direction:column;gap:0.25rem}.field.full{grid-column:1/-1}.field label{font-size:0.85rem;font-weight:500;color:#475569}</style>
