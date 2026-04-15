<template>
  <div>
    <div class="page-header"><h1>위치 / 부서 관리</h1></div>

    <div class="two-col">
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
          <h3>위치</h3>
          <Button label="추가" icon="pi pi-plus" size="small" @click="showLocDialog=true" />
        </div>
        <DataTable :value="locations" stripedRows size="small">
          <Column field="name" header="이름" />
          <Column field="building" header="건물" />
          <Column field="floor" header="층" />
          <Column field="room" header="호실" />
          <Column style="width:60px"><template #body="{data}"><Button icon="pi pi-pencil" text rounded size="small" @click="editLoc(data)" /></template></Column>
        </DataTable>
      </div>
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
          <h3>부서</h3>
          <Button label="추가" icon="pi pi-plus" size="small" @click="showDeptDialog=true" />
        </div>
        <DataTable :value="departments" stripedRows size="small">
          <Column field="name" header="이름" />
          <Column field="code" header="코드" />
          <Column field="manager_name" header="관리자" />
          <Column style="width:60px"><template #body="{data}"><Button icon="pi pi-pencil" text rounded size="small" @click="editDept(data)" /></template></Column>
        </DataTable>
      </div>
    </div>

    <Dialog v-model:visible="showLocDialog" :header="locEditId?'위치 수정':'위치 추가'" :modal="true" style="width:400px">
      <div class="form-grid">
        <div class="field"><label>이름 *</label><InputText v-model="locForm.name" fluid /></div>
        <div class="field"><label>건물</label><InputText v-model="locForm.building" fluid /></div>
        <div class="field"><label>층</label><InputText v-model="locForm.floor" fluid /></div>
        <div class="field"><label>호실</label><InputText v-model="locForm.room" fluid /></div>
      </div>
      <template #footer><Button label="취소" severity="secondary" @click="showLocDialog=false" /><Button :label="locEditId?'수정':'저장'" @click="saveLoc" /></template>
    </Dialog>

    <Dialog v-model:visible="showDeptDialog" :header="deptEditId?'부서 수정':'부서 추가'" :modal="true" style="width:400px">
      <div class="form-grid">
        <div class="field"><label>이름 *</label><InputText v-model="deptForm.name" fluid /></div>
        <div class="field"><label>코드</label><InputText v-model="deptForm.code" fluid /></div>
        <div class="field full"><label>관리자</label><InputText v-model="deptForm.manager_name" fluid /></div>
      </div>
      <template #footer><Button label="취소" severity="secondary" @click="showDeptDialog=false" /><Button :label="deptEditId?'수정':'저장'" @click="saveDept" /></template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'
import api from '@/api'

const toast=useToast()
const locations=ref<any[]>([]);const departments=ref<any[]>([])
const showLocDialog=ref(false);const locEditId=ref<number|null>(null);const locForm=ref<any>({name:'',building:'',floor:'',room:''})
const showDeptDialog=ref(false);const deptEditId=ref<number|null>(null);const deptForm=ref<any>({name:'',code:'',manager_name:''})

async function loadLocs(){const{data}=await api.get('/locations');locations.value=data}
async function loadDepts(){const{data}=await api.get('/departments');departments.value=data}
function editLoc(item:any){locEditId.value=item.id;locForm.value={...item};showLocDialog.value=true}
function editDept(item:any){deptEditId.value=item.id;deptForm.value={...item};showDeptDialog.value=true}
async function saveLoc(){try{if(locEditId.value){await api.put(`/locations/${locEditId.value}`,locForm.value)}else{await api.post('/locations',locForm.value)}toast.add({severity:'success',summary:'저장 완료',life:3000});showLocDialog.value=false;locEditId.value=null;loadLocs()}catch(err:any){toast.add({severity:'error',summary:'오류',detail:err.response?.data?.detail??'실패',life:5000})}}
async function saveDept(){try{if(deptEditId.value){await api.put(`/departments/${deptEditId.value}`,deptForm.value)}else{await api.post('/departments',deptForm.value)}toast.add({severity:'success',summary:'저장 완료',life:3000});showDeptDialog.value=false;deptEditId.value=null;loadDepts()}catch(err:any){toast.add({severity:'error',summary:'오류',detail:err.response?.data?.detail??'실패',life:5000})}}
onMounted(()=>{loadLocs();loadDepts()})
</script>
<style scoped>
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.field{display:flex;flex-direction:column;gap:0.25rem}.field.full{grid-column:1/-1}.field label{font-size:0.85rem;font-weight:500;color:#475569}
</style>
