<template>
  <div>
    <div class="page-header">
      <h1>SSL 인증서 / 도메인</h1>
      <Button label="인증서 추가" icon="pi pi-plus" @click="showCreate = true" />
    </div>
    <div class="card">
      <DataTable :value="items" :loading="loading" stripedRows size="small">
        <Column field="domain" header="도메인" sortable />
        <Column field="issuer" header="발급 기관" />
        <Column field="certificate_type" header="유형" />
        <Column field="expiry_date" header="만료일" sortable />
        <Column field="auto_renew" header="자동 갱신"><template #body="{data}"><Tag :severity="data.auto_renew?'success':'secondary'" :value="data.auto_renew?'예':'아니오'" /></template></Column>
        <Column field="cost" header="비용"><template #body="{data}">{{data.cost?`₩${data.cost.toLocaleString()}`:'-'}}</template></Column>
        <Column style="width:80px">
          <template #body="{data}">
            <Button icon="pi pi-pencil" text rounded size="small" @click="startEdit(data)" />
            <Button icon="pi pi-trash" text rounded size="small" severity="danger" @click="remove(data.id)" />
          </template>
        </Column>
      </DataTable>
      <Paginator :rows="size" :totalRecords="total" :first="(page-1)*size" @page="onPage" />
    </div>
    <Dialog v-model:visible="showCreate" :header="editId?'인증서 수정':'인증서 추가'" :modal="true" style="width:550px">
      <div class="form-grid">
        <div class="field"><label>도메인 *</label><InputText v-model="form.domain" fluid /></div>
        <div class="field"><label>발급 기관</label><InputText v-model="form.issuer" fluid /></div>
        <div class="field"><label>유형</label><InputText v-model="form.certificate_type" fluid /></div>
        <div class="field"><label>공급자</label><InputText v-model="form.provider" fluid /></div>
        <div class="field"><label>발급일</label><InputText v-model="form.issued_date" type="date" fluid /></div>
        <div class="field"><label>만료일</label><InputText v-model="form.expiry_date" type="date" fluid /></div>
        <div class="field"><label>비용</label><InputNumber v-model="form.cost" mode="currency" currency="KRW" locale="ko-KR" fluid /></div>
        <div class="field"><label>자동 갱신</label><Checkbox v-model="form.auto_renew" :binary="true" /></div>
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
import Checkbox from 'primevue/checkbox'
import Dialog from 'primevue/dialog'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import api from '@/api'

const toast=useToast()
const items=ref<any[]>([]);const loading=ref(false);const page=ref(1);const size=ref(20);const total=ref(0)
const showCreate=ref(false);const editId=ref<number|null>(null)
const form=ref<any>({domain:'',issuer:'',certificate_type:'',provider:'',issued_date:'',expiry_date:'',cost:null,auto_renew:false,notes:''})

async function load(){loading.value=true;try{const{data}=await api.get('/certificates',{params:{page:page.value,size:size.value}});items.value=data.items;total.value=data.total}finally{loading.value=false}}
function onPage(e:any){page.value=e.page+1;load()}
function startEdit(item:any){editId.value=item.id;form.value={...item};showCreate.value=true}
async function save(){try{if(editId.value){await api.put(`/certificates/${editId.value}`,form.value)}else{await api.post('/certificates',form.value)}toast.add({severity:'success',summary:'저장 완료',life:3000});showCreate.value=false;editId.value=null;load()}catch(err:any){toast.add({severity:'error',summary:'오류',detail:err.response?.data?.detail??'실패',life:5000})}}
async function remove(id:number){await api.delete(`/certificates/${id}`);load()}
onMounted(load)
</script>
<style scoped>.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.field{display:flex;flex-direction:column;gap:0.25rem}.field.full{grid-column:1/-1}.field label{font-size:0.85rem;font-weight:500;color:#475569}</style>
