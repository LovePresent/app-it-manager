<template>
  <div>
    <div class="page-header">
      <div>
        <h1>위치 / 부서 관리</h1>
        <p class="page-subtitle">디바이스에 등록된 위치와 부서는 자동으로 마스터에 추가되고 이름순으로 정렬됩니다.</p>
      </div>
      <Button label="새로고침" icon="pi pi-refresh" severity="secondary" @click="loadAll" />
    </div>

    <div class="two-col">
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
          <h3>위치</h3>
          <Button label="추가" icon="pi pi-plus" size="small" @click="openCreateLoc" />
        </div>
        <DataTable :value="sortedLocations" stripedRows size="small">
          <Column field="name" header="이름" />
          <Column field="type" header="구분">
            <template #body="{ data }">{{ locationTypeLabel(data.type) }}</template>
          </Column>
          <Column field="description" header="설명">
            <template #body="{ data }">{{ data.description || '-' }}</template>
          </Column>
          <Column style="width:60px"><template #body="{data}"><Button icon="pi pi-pencil" text rounded size="small" @click="editLoc(data)" /></template></Column>
        </DataTable>
      </div>
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
          <h3>부서</h3>
          <Button label="추가" icon="pi pi-plus" size="small" @click="openCreateDept" />
        </div>
        <DataTable :value="sortedDepartments" stripedRows size="small">
          <Column field="name" header="이름" />
          <Column field="code" header="코드" />
          <Column field="manager" header="관리자" />
          <Column style="width:60px"><template #body="{data}"><Button icon="pi pi-pencil" text rounded size="small" @click="editDept(data)" /></template></Column>
        </DataTable>
      </div>
    </div>

    <Dialog v-model:visible="showLocDialog" :header="locEditId !== null ? '위치 수정':'위치 추가'" :modal="true" style="width:400px">
      <div class="form-grid">
        <div class="field"><label>이름 *</label><InputText v-model="locForm.name" fluid /></div>
        <div class="field"><label>구분</label><Select v-model="locForm.type" :options="locationTypeOptions" optionLabel="label" optionValue="value" showClear fluid /></div>
        <div class="field full"><label>설명</label><InputText v-model="locForm.description" fluid /></div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <Button
            v-if="locEditId !== null"
            label="삭제"
            icon="pi pi-trash"
            severity="danger"
            :loading="deletingLoc"
            @click="deleteLoc"
          />
          <div class="dialog-actions">
            <Button label="취소" severity="secondary" @click="showLocDialog=false" />
            <Button :label="locEditId !== null ? '수정':'저장'" @click="saveLoc" />
          </div>
        </div>
      </template>
    </Dialog>

    <Dialog v-model:visible="showDeptDialog" :header="deptEditId !== null ? '부서 수정':'부서 추가'" :modal="true" style="width:400px">
      <div class="form-grid">
        <div class="field"><label>이름 *</label><InputText v-model="deptForm.name" fluid /></div>
        <div class="field"><label>코드</label><InputText v-model="deptForm.code" fluid /></div>
        <div class="field full"><label>관리자</label><InputText v-model="deptForm.manager" fluid /></div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <Button
            v-if="deptEditId !== null"
            label="삭제"
            icon="pi pi-trash"
            severity="danger"
            :loading="deletingDept"
            @click="deleteDept"
          />
          <div class="dialog-actions">
            <Button label="취소" severity="secondary" @click="showDeptDialog=false" />
            <Button :label="deptEditId !== null ? '수정':'저장'" @click="saveDept" />
          </div>
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'
import api from '@/api'
import type { Department, Location } from '@/types'

const toast=useToast()
const locations=ref<Location[]>([]);const departments=ref<Department[]>([])
const showLocDialog=ref(false);const locEditId=ref<number|null>(null);const locForm=ref<any>(emptyLocForm())
const showDeptDialog=ref(false);const deptEditId=ref<number|null>(null);const deptForm=ref<any>(emptyDeptForm())
const deletingLoc=ref(false);const deletingDept=ref(false)

const locationTypeOptions = [
  { label: '위치', value: 'device_location' },
  { label: '공장', value: 'factory' },
  { label: '건물', value: 'building' },
  { label: '층', value: 'floor' },
  { label: '호실', value: 'room' },
]

const sortedLocations = computed(() => [...locations.value].sort((a,b)=>a.name.localeCompare(b.name,'ko-KR')))
const sortedDepartments = computed(() => [...departments.value].sort((a,b)=>a.name.localeCompare(b.name,'ko-KR')))

async function loadLocs(){const{data}=await api.get('/locations');locations.value=data}
async function loadDepts(){const{data}=await api.get('/departments');departments.value=data}
function loadAll(){loadLocs();loadDepts()}
function emptyLocForm(){return {name:'',type:'device_location',description:''}}
function emptyDeptForm(){return {name:'',code:'',manager:''}}
function openCreateLoc(){locEditId.value=null;locForm.value=emptyLocForm();showLocDialog.value=true}
function openCreateDept(){deptEditId.value=null;deptForm.value=emptyDeptForm();showDeptDialog.value=true}
function editLoc(item:Location){
  if (item.id == null) {
    toast.add({severity:'error',summary:'오류',detail:'수정할 위치 ID가 없습니다.',life:5000})
    return
  }
  locEditId.value=item.id
  locForm.value={name:item.name ?? '',type:item.type ?? 'device_location',description:item.description ?? ''}
  showLocDialog.value=true
}
function editDept(item:Department){
  if (item.id == null) {
    toast.add({severity:'error',summary:'오류',detail:'수정할 부서 ID가 없습니다.',life:5000})
    return
  }
  deptEditId.value=item.id
  deptForm.value={name:item.name ?? '',code:item.code ?? '',manager:item.manager ?? ''}
  showDeptDialog.value=true
}
async function saveLoc(){try{const payload={name:locForm.value.name,type:locForm.value.type,description:locForm.value.description};if(locEditId.value !== null){await api.put(`/locations/${locEditId.value}`,payload)}else{await api.post('/locations',payload)}toast.add({severity:'success',summary:'저장 완료',life:3000});showLocDialog.value=false;locEditId.value=null;locForm.value=emptyLocForm();loadLocs()}catch(err:any){toast.add({severity:'error',summary:'오류',detail:err.response?.data?.detail??'실패',life:5000})}}
async function saveDept(){try{const payload={name:deptForm.value.name,code:deptForm.value.code,manager:deptForm.value.manager};if(deptEditId.value !== null){await api.put(`/departments/${deptEditId.value}`,payload)}else{await api.post('/departments',payload)}toast.add({severity:'success',summary:'저장 완료',life:3000});showDeptDialog.value=false;deptEditId.value=null;deptForm.value=emptyDeptForm();loadDepts()}catch(err:any){toast.add({severity:'error',summary:'오류',detail:err.response?.data?.detail??'실패',life:5000})}}
async function deleteLoc(){
  if (locEditId.value === null) return
  const name = locForm.value.name || '선택한 위치'
  if (!window.confirm(`'${name}' 위치를 삭제할까요?`)) return
  deletingLoc.value=true
  try{
    await api.delete(`/locations/${locEditId.value}`)
    toast.add({severity:'success',summary:'삭제 완료',life:3000})
    showLocDialog.value=false
    locEditId.value=null
    locForm.value=emptyLocForm()
    loadLocs()
  }catch(err:any){
    toast.add({severity:'error',summary:'오류',detail:err.response?.data?.detail??'삭제 실패',life:5000})
  }finally{
    deletingLoc.value=false
  }
}
async function deleteDept(){
  if (deptEditId.value === null) return
  const name = deptForm.value.name || '선택한 부서'
  if (!window.confirm(`'${name}' 부서를 삭제할까요?`)) return
  deletingDept.value=true
  try{
    await api.delete(`/departments/${deptEditId.value}`)
    toast.add({severity:'success',summary:'삭제 완료',life:3000})
    showDeptDialog.value=false
    deptEditId.value=null
    deptForm.value=emptyDeptForm()
    loadDepts()
  }catch(err:any){
    toast.add({severity:'error',summary:'오류',detail:err.response?.data?.detail??'삭제 실패',life:5000})
  }finally{
    deletingDept.value=false
  }
}
function locationTypeLabel(value:string|null){return locationTypeOptions.find((item)=>item.value===value)?.label ?? value ?? '-'}
onMounted(loadAll)
</script>
<style scoped>
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.field{display:flex;flex-direction:column;gap:0.25rem}.field.full{grid-column:1/-1}.field label{font-size:0.85rem;font-weight:500;color:#475569}
.dialog-footer{display:flex;align-items:center;justify-content:space-between;width:100%;gap:0.75rem}
.dialog-actions{display:flex;justify-content:flex-end;gap:0.5rem;margin-left:auto}
.page-subtitle{margin-top:0.25rem;color:#64748b;font-size:0.9rem}
</style>
