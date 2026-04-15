<template>
  <div>
    <div class="page-header">
      <h1>카테고리 관리</h1>
      <Button label="카테고리 추가" icon="pi pi-plus" @click="showCreate = true" />
    </div>
    <div class="card">
      <DataTable :value="categories" stripedRows size="small">
        <Column field="sort_order" header="#" style="width:50px" />
        <Column field="icon" header="아이콘" style="width:50px"><template #body="{data}"><i :class="data.icon"></i></template></Column>
        <Column field="name" header="이름" sortable />
        <Column field="slug" header="슬러그" />
        <Column field="description" header="설명" />
        <Column field="is_active" header="활성"><template #body="{data}"><Tag :severity="data.is_active?'success':'secondary'" :value="data.is_active?'활성':'비활성'" /></template></Column>
        <Column style="width:80px">
          <template #body="{data}"><Button icon="pi pi-pencil" text rounded size="small" @click="startEdit(data)" /></template>
        </Column>
      </DataTable>
    </div>
    <Dialog v-model:visible="showCreate" :header="editId?'수정':'추가'" :modal="true" style="width:450px">
      <div class="form-grid">
        <div class="field"><label>이름 *</label><InputText v-model="form.name" fluid /></div>
        <div class="field"><label>슬러그</label><InputText v-model="form.slug" fluid /></div>
        <div class="field"><label>아이콘</label><InputText v-model="form.icon" fluid /></div>
        <div class="field"><label>정렬 순서</label><InputNumber v-model="form.sort_order" fluid /></div>
        <div class="field full"><label>설명</label><InputText v-model="form.description" fluid /></div>
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
import Tag from 'primevue/tag'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'
import api from '@/api'
import type { Category } from '@/types'

const toast=useToast()
const categories=ref<Category[]>([])
const showCreate=ref(false);const editId=ref<number|null>(null)
const form=ref<any>({name:'',slug:'',icon:'pi pi-box',description:'',sort_order:0})

async function load(){const{data}=await api.get('/categories');categories.value=data}
function startEdit(item:any){editId.value=item.id;form.value={...item};showCreate.value=true}
async function save(){try{if(editId.value){await api.put(`/categories/${editId.value}`,form.value)}else{await api.post('/categories',form.value)}toast.add({severity:'success',summary:'저장 완료',life:3000});showCreate.value=false;editId.value=null;load()}catch(err:any){toast.add({severity:'error',summary:'오류',detail:err.response?.data?.detail??'실패',life:5000})}}
onMounted(load)
</script>
<style scoped>.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.field{display:flex;flex-direction:column;gap:0.25rem}.field.full{grid-column:1/-1}.field label{font-size:0.85rem;font-weight:500;color:#475569}</style>
