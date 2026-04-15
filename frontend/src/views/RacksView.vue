<template>
  <div>
    <div class="page-header">
      <h1>서버 랙 관리</h1>
      <Button label="랙 추가" icon="pi pi-plus" @click="showCreate = true" />
    </div>
    <div class="card">
      <DataTable :value="items" :loading="loading" stripedRows size="small">
        <Column field="name" header="이름" sortable />
        <Column field="location" header="위치" />
        <Column header="사용률">
          <template #body="{data}">
            <div style="display:flex;align-items:center;gap:0.5rem">
              <ProgressBar :value="Math.round(data.used_units/data.total_units*100)" style="width:100px;height:8px" />
              <span>{{ data.used_units }}/{{ data.total_units }}U</span>
            </div>
          </template>
        </Column>
        <Column field="power_capacity" header="전원 용량" />
        <Column style="width:80px">
          <template #body="{data}">
            <Button icon="pi pi-pencil" text rounded size="small" @click="startEdit(data)" />
            <Button icon="pi pi-trash" text rounded size="small" severity="danger" @click="remove(data.id)" />
          </template>
        </Column>
      </DataTable>
    </div>
    <Dialog v-model:visible="showCreate" :header="editId?'수정':'추가'" :modal="true" style="width:450px">
      <div class="form-grid">
        <div class="field"><label>이름 *</label><InputText v-model="form.name" fluid /></div>
        <div class="field"><label>위치</label><InputText v-model="form.location" fluid /></div>
        <div class="field"><label>총 유닛 수</label><InputNumber v-model="form.total_units" fluid /></div>
        <div class="field"><label>전원 용량</label><InputText v-model="form.power_capacity" fluid /></div>
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
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Textarea from 'primevue/textarea'
import ProgressBar from 'primevue/progressbar'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'
import api from '@/api'

const toast=useToast()
const items=ref<any[]>([]);const loading=ref(false)
const showCreate=ref(false);const editId=ref<number|null>(null)
const form=ref<any>({name:'',location:'',total_units:42,power_capacity:'',notes:''})

async function load(){loading.value=true;try{const{data}=await api.get('/racks');items.value=data}finally{loading.value=false}}
function startEdit(item:any){editId.value=item.id;form.value={...item};showCreate.value=true}
async function save(){try{if(editId.value){await api.put(`/racks/${editId.value}`,form.value)}else{await api.post('/racks',form.value)}toast.add({severity:'success',summary:'저장 완료',life:3000});showCreate.value=false;editId.value=null;load()}catch(err:any){toast.add({severity:'error',summary:'오류',detail:err.response?.data?.detail??'실패',life:5000})}}
async function remove(id:number){await api.delete(`/racks/${id}`);load()}
onMounted(load)
</script>
<style scoped>.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.field{display:flex;flex-direction:column;gap:0.25rem}.field.full{grid-column:1/-1}.field label{font-size:0.85rem;font-weight:500;color:#475569}</style>
