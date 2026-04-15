<template>
  <div v-if="asset">
    <div class="page-header">
      <div>
        <Button icon="pi pi-arrow-left" text @click="$router.back()" />
        <h1 style="display:inline;margin-left:0.5rem">{{ asset.name }}</h1>
        <Tag :severity="statusSeverity(asset.status)" :value="statusLabel(asset.status)" style="margin-left:0.75rem" />
      </div>
      <div style="display:flex;gap:0.5rem">
        <Button label="QR 코드" icon="pi pi-qrcode" severity="secondary" @click="showQR = true" />
        <Button v-if="asset.status === 'in_stock'" label="배정" icon="pi pi-user-plus" @click="showAssign = true" />
        <Button v-if="asset.status === 'assigned'" label="반납" icon="pi pi-undo" severity="warn" @click="returnAsset" />
        <Button label="수정" icon="pi pi-pencil" severity="secondary" @click="startEdit" />
      </div>
    </div>

    <div class="detail-grid">
      <div class="card info-card">
        <h3>기본 정보</h3>
        <div class="info-row"><span>자산 태그</span><strong>{{ asset.asset_tag }}</strong></div>
        <div class="info-row"><span>카테고리</span><span>{{ asset.category_name }}</span></div>
        <div class="info-row"><span>시리얼 번호</span><span>{{ asset.serial_number ?? '-' }}</span></div>
        <div class="info-row"><span>모델</span><span>{{ asset.model ?? '-' }}</span></div>
        <div class="info-row"><span>제조사</span><span>{{ asset.manufacturer ?? '-' }}</span></div>
      </div>
      <div class="card info-card">
        <h3>구매/보증</h3>
        <div class="info-row"><span>취득일</span><span>{{ asset.purchase_date ?? '-' }}</span></div>
        <div class="info-row"><span>취득가</span><span>{{ asset.purchase_cost ? `₩${asset.purchase_cost.toLocaleString()}` : '-' }}</span></div>
        <div class="info-row"><span>보증 만료</span><span>{{ asset.warranty_expiry ?? '-' }}</span></div>
        <div class="info-row"><span>위치</span><span>{{ asset.location_name ?? '-' }}</span></div>
        <div class="info-row"><span>부서</span><span>{{ asset.department_name ?? '-' }}</span></div>
        <div class="info-row"><span>사용자</span><span>{{ asset.assigned_to_name ?? '-' }}</span></div>
      </div>
    </div>

    <div class="card" style="margin-top:1.5rem" v-if="asset.notes">
      <h3>비고</h3>
      <p style="margin-top:0.5rem;white-space:pre-wrap">{{ asset.notes }}</p>
    </div>

    <div class="card" style="margin-top:1.5rem">
      <h3>배정 이력</h3>
      <DataTable :value="assignments" stripedRows size="small" style="margin-top:0.75rem">
        <Column field="user_name" header="사용자" />
        <Column field="assigned_date" header="배정일" />
        <Column field="returned_date" header="반납일">
          <template #body="{ data }">{{ data.returned_date ?? '사용 중' }}</template>
        </Column>
        <Column field="notes" header="비고" />
      </DataTable>
    </div>

    <Dialog v-model:visible="showAssign" header="자산 배정" :modal="true" style="width:400px">
      <div class="field"><label>사용자 ID</label><InputNumber v-model="assignUserId" fluid /></div>
      <div class="field"><label>비고</label><InputText v-model="assignNotes" fluid /></div>
      <template #footer>
        <Button label="취소" severity="secondary" @click="showAssign = false" />
        <Button label="배정" @click="assignAsset" />
      </template>
    </Dialog>

    <Dialog v-model:visible="showQR" header="QR 코드" :modal="true" style="width:320px;text-align:center">
      <img :src="`/api/v1/qr/${asset.id}`" alt="QR Code" style="max-width:250px" />
    </Dialog>

    <Dialog v-model:visible="showEdit" header="자산 수정" :modal="true" style="width:600px">
      <div class="form-grid">
        <div class="field"><label>이름</label><InputText v-model="editForm.name" fluid /></div>
        <div class="field"><label>시리얼 번호</label><InputText v-model="editForm.serial_number" fluid /></div>
        <div class="field"><label>모델</label><InputText v-model="editForm.model" fluid /></div>
        <div class="field"><label>제조사</label><InputText v-model="editForm.manufacturer" fluid /></div>
        <div class="field"><label>취득가</label><InputNumber v-model="editForm.purchase_cost" mode="currency" currency="KRW" locale="ko-KR" fluid /></div>
        <div class="field"><label>보증 만료</label><InputText v-model="editForm.warranty_expiry" type="date" fluid /></div>
        <div class="field full"><label>비고</label><Textarea v-model="editForm.notes" rows="2" fluid /></div>
      </div>
      <template #footer>
        <Button label="취소" severity="secondary" @click="showEdit = false" />
        <Button label="저장" @click="saveEdit" />
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Textarea from 'primevue/textarea'
import Dialog from 'primevue/dialog'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import api from '@/api'
import type { Asset, AssignmentRecord } from '@/types'

const route = useRoute()
const toast = useToast()
const id = Number(route.params.id)

const asset = ref<Asset | null>(null)
const assignments = ref<AssignmentRecord[]>([])
const showAssign = ref(false)
const showQR = ref(false)
const showEdit = ref(false)
const assignUserId = ref<number | null>(null)
const assignNotes = ref('')
const editForm = ref<any>({})

const statusMap: Record<string, string> = { in_stock: '재고', assigned: '사용 중', in_maintenance: '유지보수', retired: '퇴역', disposed: '폐기', lost: '분실' }
const severityMap: Record<string, any> = { in_stock: 'warn', assigned: 'success', in_maintenance: 'info', retired: 'secondary', disposed: 'contrast', lost: 'danger' }
function statusLabel(s: string) { return statusMap[s] ?? s }
function statusSeverity(s: string) { return severityMap[s] ?? 'secondary' }

async function loadAsset() {
  const { data } = await api.get(`/assets/${id}`)
  asset.value = data
}

async function loadAssignments() {
  const { data } = await api.get(`/assets/${id}/assignments`)
  assignments.value = data
}

async function assignAsset() {
  await api.post(`/assets/${id}/assign`, { user_id: assignUserId.value, notes: assignNotes.value })
  toast.add({ severity: 'success', summary: '배정 완료', life: 3000 })
  showAssign.value = false
  loadAsset()
  loadAssignments()
}

async function returnAsset() {
  await api.post(`/assets/${id}/return`)
  toast.add({ severity: 'success', summary: '반납 완료', life: 3000 })
  loadAsset()
  loadAssignments()
}

function startEdit() {
  editForm.value = { ...asset.value }
  showEdit.value = true
}

async function saveEdit() {
  await api.put(`/assets/${id}`, editForm.value)
  toast.add({ severity: 'success', summary: '수정 완료', life: 3000 })
  showEdit.value = false
  loadAsset()
}

onMounted(() => {
  loadAsset()
  loadAssignments()
})
</script>

<style scoped>
.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}
.info-card h3 {
  margin-bottom: 1rem;
  font-size: 1rem;
}
.info-row {
  display: flex;
  justify-content: space-between;
  padding: 0.5rem 0;
  border-bottom: 1px solid #f1f5f9;
}
.info-row span:first-child {
  color: #64748b;
  font-size: 0.9rem;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.field.full {
  grid-column: 1 / -1;
}
.field label {
  font-size: 0.85rem;
  font-weight: 500;
  color: #475569;
}
</style>
