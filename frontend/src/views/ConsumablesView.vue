<template>
  <div>
    <div class="page-header">
      <h1>소모품 관리</h1>
      <Button label="소모품 추가" icon="pi pi-plus" @click="openCreate" />
    </div>
    <div class="card">
      <DataTable :value="items" :loading="loading" stripedRows size="small">
        <Column field="asset_name" header="자산" sortable>
          <template #body="{data}">{{ data.asset_name || data.asset_tag || `#${data.asset_id}` }}</template>
        </Column>
        <Column field="qty_in_stock" header="현재 수량" />
        <Column field="min_stock_level" header="최소 수량" />
        <Column header="상태">
          <template #body="{data}">
            <Tag :severity="data.is_low_stock ? 'danger' : 'success'" :value="data.is_low_stock ? '부족' : '정상'" />
          </template>
        </Column>
        <Column field="unit" header="단위" />
        <Column style="width:140px">
          <template #body="{data}">
            <Button icon="pi pi-plus" text rounded size="small" severity="success" @click="openTx(data,'in')" v-tooltip="'입고'" />
            <Button icon="pi pi-minus" text rounded size="small" severity="warn" @click="openTx(data,'out')" v-tooltip="'출고'" />
            <Button icon="pi pi-pencil" text rounded size="small" @click="startEdit(data)" />
            <Button icon="pi pi-trash" text rounded size="small" severity="danger" @click="remove(data.id)" />
          </template>
        </Column>
      </DataTable>
      <Paginator :rows="size" :totalRecords="total" :first="(page-1)*size" @page="onPage" />
    </div>

    <Dialog v-model:visible="showCreate" :header="editId !== null ? '수정':'추가'" :modal="true" style="width:450px">
      <div class="form-grid">
        <div class="field"><label>자산 ID *</label><InputNumber v-model="form.asset_id" fluid /></div>
        <div class="field"><label>단위</label><InputText v-model="form.unit" fluid /></div>
        <div class="field"><label>현재 수량</label><InputNumber v-model="form.qty_in_stock" fluid /></div>
        <div class="field"><label>최소 수량</label><InputNumber v-model="form.min_stock_level" fluid /></div>
        <div class="field"><label>마지막 입고일</label><InputText v-model="form.last_restock_date" type="date" fluid /></div>
      </div>
      <template #footer>
        <Button label="취소" severity="secondary" @click="showCreate=false" />
        <Button :label="editId !== null ? '수정':'저장'" @click="save" />
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
import Dialog from 'primevue/dialog'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import api from '@/api'

const toast=useToast()
const items=ref<any[]>([]);const loading=ref(false);const page=ref(1);const size=ref(20);const total=ref(0)
const showCreate=ref(false);const editId=ref<number|null>(null)
const form=ref<any>(emptyForm())
const showTx=ref(false);const txType=ref('in');const txItemId=ref(0);const txQty=ref(1);const txNotes=ref('')

async function load(){loading.value=true;try{const{data}=await api.get('/consumables',{params:{page:page.value,size:size.value}});items.value=data.items;total.value=data.total}finally{loading.value=false}}
function onPage(e:any){page.value=e.page+1;load()}
function emptyForm(){return {asset_id:null,qty_in_stock:0,min_stock_level:5,unit:'개',last_restock_date:''}}
function openCreate(){editId.value=null;form.value=emptyForm();showCreate.value=true}
function startEdit(item:any){editId.value=item.id;form.value={...item};showCreate.value=true}
function payload(){
  const base:any={qty_in_stock:form.value.qty_in_stock,min_stock_level:form.value.min_stock_level,unit:form.value.unit,last_restock_date:form.value.last_restock_date || null}
  if(editId.value === null) base.asset_id=form.value.asset_id
  return base
}
async function save(){try{if(editId.value !== null){await api.put(`/consumables/${editId.value}`,payload())}else{await api.post('/consumables',payload())}toast.add({severity:'success',summary:'저장 완료',life:3000});showCreate.value=false;editId.value=null;form.value=emptyForm();load()}catch(err:any){toast.add({severity:'error',summary:'오류',detail:err.response?.data?.detail??'실패',life:5000})}}
function openTx(item:any,type:string){txItemId.value=item.id;txType.value=type;txQty.value=1;txNotes.value='';showTx.value=true}
async function submitTx(){try{await api.post(`/consumables/${txItemId.value}/transactions`,{consumable_id:txItemId.value,transaction_type:txType.value,qty_change:txQty.value,notes:txNotes.value});toast.add({severity:'success',summary:txType.value==='in'?'입고 완료':'출고 완료',life:3000});showTx.value=false;load()}catch(err:any){toast.add({severity:'error',summary:'오류',detail:err.response?.data?.detail??'실패',life:5000})}}
async function remove(id:number){await api.delete(`/consumables/${id}`);load()}
onMounted(load)
</script>
<style scoped>.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.field{display:flex;flex-direction:column;gap:0.25rem}.field.full{grid-column:1/-1}.field label{font-size:0.85rem;font-weight:500;color:#475569}</style>
