<template>
  <div>
    <div class="page-header">
      <h1>소모품 관리</h1>
      <Button label="소모품 추가" icon="pi pi-plus" @click="showCreate = true" />
    </div>
    <div class="card">
      <DataTable :value="items" :loading="loading" stripedRows size="small">
        <Column field="name" header="이름" sortable />
        <Column field="category" header="분류" />
        <Column field="current_qty" header="현재 수량" />
        <Column field="min_qty" header="최소 수량" />
        <Column header="상태">
          <template #body="{data}">
            <Tag :severity="data.current_qty <= data.min_qty ? 'danger' : 'success'" :value="data.current_qty <= data.min_qty ? '부족' : '정상'" />
          </template>
        </Column>
        <Column field="unit" header="단위" />
        <Column style="width:140px">
          <template #body="{data}">
            <Button icon="pi pi-plus" text rounded size="small" severity="success" @click="openTx(data,'in')" v-tooltip="'입고'" />
            <Button icon="pi pi-minus" text rounded size="small" severity="warn" @click="openTx(data,'out')" v-tooltip="'출고'" />
            <Button icon="pi pi-pencil" text rounded size="small" @click="startEdit(data)" />
          </template>
        </Column>
      </DataTable>
      <Paginator :rows="size" :totalRecords="total" :first="(page-1)*size" @page="onPage" />
    </div>

    <Dialog v-model:visible="showCreate" :header="editId?'수정':'추가'" :modal="true" style="width:450px">
      <div class="form-grid">
        <div class="field"><label>이름 *</label><InputText v-model="form.name" fluid /></div>
        <div class="field"><label>분류</label><InputText v-model="form.category" fluid /></div>
        <div class="field"><label>단위</label><InputText v-model="form.unit" fluid /></div>
        <div class="field"><label>현재 수량</label><InputNumber v-model="form.current_qty" fluid /></div>
        <div class="field"><label>최소 수량</label><InputNumber v-model="form.min_qty" fluid /></div>
        <div class="field"><label>보관 위치</label><InputText v-model="form.location" fluid /></div>
        <div class="field full"><label>비고</label><Textarea v-model="form.notes" rows="2" fluid /></div>
      </div>
      <template #footer>
        <Button label="취소" severity="secondary" @click="showCreate=false" />
        <Button :label="editId?'수정':'저장'" @click="save" />
      </template>
    </Dialog>

    <Dialog v-model:visible="showTx" :header="txType==='in'?'입고':'출고'" :modal="true" style="width:350px">
      <div class="field"><label>수량</label><InputNumber v-model="txQty" fluid /></div>
      <div class="field" style="margin-top:0.75rem"><label>비고</label><InputText v-model="txNotes" fluid /></div>
      <template #footer>
        <Button label="취소" severity="secondary" @click="showTx=false" />
        <Button :label="txType==='in'?'입고 처리':'출고 처리'" @click="submitTx" />
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
import Dialog from 'primevue/dialog'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import api from '@/api'

const toast=useToast()
const items=ref<any[]>([]);const loading=ref(false);const page=ref(1);const size=ref(20);const total=ref(0)
const showCreate=ref(false);const editId=ref<number|null>(null)
const form=ref<any>({name:'',category:'',unit:'개',current_qty:0,min_qty:5,location:'',notes:''})
const showTx=ref(false);const txType=ref('in');const txItemId=ref(0);const txQty=ref(1);const txNotes=ref('')

async function load(){loading.value=true;try{const{data}=await api.get('/consumables',{params:{page:page.value,size:size.value}});items.value=data.items;total.value=data.total}finally{loading.value=false}}
function onPage(e:any){page.value=e.page+1;load()}
function startEdit(item:any){editId.value=item.id;form.value={...item};showCreate.value=true}
async function save(){try{if(editId.value){await api.put(`/consumables/${editId.value}`,form.value)}else{await api.post('/consumables',form.value)}toast.add({severity:'success',summary:'저장 완료',life:3000});showCreate.value=false;editId.value=null;load()}catch(err:any){toast.add({severity:'error',summary:'오류',detail:err.response?.data?.detail??'실패',life:5000})}}
function openTx(item:any,type:string){txItemId.value=item.id;txType.value=type;txQty.value=1;txNotes.value='';showTx.value=true}
async function submitTx(){try{await api.post(`/consumables/${txItemId.value}/transaction`,{type:txType.value,quantity:txQty.value,notes:txNotes.value});toast.add({severity:'success',summary:txType.value==='in'?'입고 완료':'출고 완료',life:3000});showTx.value=false;load()}catch(err:any){toast.add({severity:'error',summary:'오류',detail:err.response?.data?.detail??'실패',life:5000})}}
onMounted(load)
</script>
<style scoped>.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.field{display:flex;flex-direction:column;gap:0.25rem}.field.full{grid-column:1/-1}.field label{font-size:0.85rem;font-weight:500;color:#475569}</style>
