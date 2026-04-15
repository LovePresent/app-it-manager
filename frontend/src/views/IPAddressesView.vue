<template>
  <div>
    <div class="page-header">
      <h1>IP 주소 관리</h1>
      <Button label="IP 추가" icon="pi pi-plus" @click="showCreate = true" />
    </div>
    <div class="filters-row">
      <IconField><InputIcon class="pi pi-search" /><InputText v-model="search" placeholder="검색" @keyup.enter="load" /></IconField>
      <Select v-model="filterStatus" :options="['assigned','available','reserved']" placeholder="상태" showClear @change="load" />
    </div>
    <div class="card">
      <DataTable :value="items" :loading="loading" stripedRows size="small">
        <Column field="ip_address" header="IP 주소" sortable />
        <Column field="vlan" header="VLAN" />
        <Column field="device_name" header="장비명" />
        <Column field="assigned_to" header="사용자" />
        <Column field="status" header="상태"><template #body="{data}"><Tag :severity="data.status==='available'?'success':data.status==='reserved'?'warn':'info'" :value="data.status" /></template></Column>
        <Column style="width:80px">
          <template #body="{data}">
            <Button icon="pi pi-pencil" text rounded size="small" @click="startEdit(data)" />
            <Button icon="pi pi-trash" text rounded size="small" severity="danger" @click="remove(data.id)" />
          </template>
        </Column>
      </DataTable>
      <Paginator :rows="size" :totalRecords="total" :first="(page-1)*size" @page="onPage" />
    </div>
    <Dialog v-model:visible="showCreate" :header="editId?'IP 수정':'IP 추가'" :modal="true" style="width:500px">
      <div class="form-grid">
        <div class="field"><label>IP 주소 *</label><InputText v-model="form.ip_address" fluid /></div>
        <div class="field"><label>서브넷 마스크</label><InputText v-model="form.subnet_mask" fluid /></div>
        <div class="field"><label>게이트웨이</label><InputText v-model="form.gateway" fluid /></div>
        <div class="field"><label>DNS</label><InputText v-model="form.dns" fluid /></div>
        <div class="field"><label>VLAN</label><InputText v-model="form.vlan" fluid /></div>
        <div class="field"><label>장비명</label><InputText v-model="form.device_name" fluid /></div>
        <div class="field"><label>사용자</label><InputText v-model="form.assigned_to" fluid /></div>
        <div class="field"><label>상태</label><Select v-model="form.status" :options="['available','assigned','reserved']" fluid /></div>
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
import Textarea from 'primevue/textarea'
import Select from 'primevue/select'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import Tag from 'primevue/tag'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'
import api from '@/api'

const toast=useToast()
const items=ref<any[]>([]);const loading=ref(false);const page=ref(1);const size=ref(20);const total=ref(0)
const search=ref('');const filterStatus=ref<string|null>(null)
const showCreate=ref(false);const editId=ref<number|null>(null)
const form=ref<any>({ip_address:'',subnet_mask:'',gateway:'',dns:'',vlan:'',device_name:'',assigned_to:'',status:'available',notes:''})

async function load(){loading.value=true;try{const params:any={page:page.value,size:size.value};if(search.value)params.search=search.value;if(filterStatus.value)params.status=filterStatus.value;const{data}=await api.get('/ip-addresses',{params});items.value=data.items;total.value=data.total}finally{loading.value=false}}
function onPage(e:any){page.value=e.page+1;load()}
function startEdit(item:any){editId.value=item.id;form.value={...item};showCreate.value=true}
async function save(){try{if(editId.value){await api.put(`/ip-addresses/${editId.value}`,form.value)}else{await api.post('/ip-addresses',form.value)}toast.add({severity:'success',summary:'저장 완료',life:3000});showCreate.value=false;editId.value=null;load()}catch(err:any){toast.add({severity:'error',summary:'오류',detail:err.response?.data?.detail??'실패',life:5000})}}
async function remove(id:number){await api.delete(`/ip-addresses/${id}`);load()}
onMounted(load)
</script>
<style scoped>.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.field{display:flex;flex-direction:column;gap:0.25rem}.field.full{grid-column:1/-1}.field label{font-size:0.85rem;font-weight:500;color:#475569}</style>
