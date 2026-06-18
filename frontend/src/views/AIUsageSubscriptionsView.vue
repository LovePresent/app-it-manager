<template>
  <div>
    <div class="page-header">
      <div>
        <h1>AI 사용 구독</h1>
        <p class="page-subtitle">AI 서비스, 모델, 계정, 부서, 비용과 토큰 사용량을 관리합니다.</p>
      </div>
      <Button label="AI 구독 추가" icon="pi pi-plus" @click="openCreate" />
    </div>

    <div class="summary-strip">
      <div class="summary-item"><span>전체</span><strong>{{ total }}</strong></div>
      <div class="summary-item"><span>사용 중</span><strong>{{ activeCount }}</strong></div>
      <div class="summary-item"><span>월 비용</span><strong>{{ currency(totalMonthlyCost) }}</strong></div>
      <div class="summary-item"><span>토큰 사용률</span><strong>{{ tokenUsageRate }}%</strong></div>
    </div>

    <div class="filters-row">
      <IconField>
        <InputIcon class="pi pi-search" />
        <InputText v-model="search" placeholder="서비스, 공급자, 모델, 사용자, 부서 검색" @keyup.enter="load" />
      </IconField>
      <Select v-model="filterStatus" :options="statusOptions" optionLabel="label" optionValue="value" placeholder="상태" showClear @change="load" />
      <Select v-model="groupField" :options="groupOptions" optionLabel="label" optionValue="value" placeholder="그룹핑" showClear @change="onGroupChange" />
      <Button label="검색" icon="pi pi-search" @click="load" />
    </div>

    <div class="card">
      <DataTable
        :value="displayItems"
        :loading="loading"
        :rowGroupMode="groupField ? 'subheader' : undefined"
        :groupRowsBy="groupField || undefined"
        sortMode="single"
        :sortField="groupField || undefined"
        :sortOrder="1"
        stripedRows
        size="small"
      >
        <template #groupheader="{ data }">
          <div class="group-header">
            <span>{{ groupHeader(data) }}</span>
            <strong>{{ groupCount(data) }}건</strong>
          </div>
        </template>
        <Column header="서비스" style="min-width:170px">
          <template #body="{ data }">
            <div class="identity-cell">
              <strong>{{ data.service_name }}</strong>
              <span>{{ [data.provider, data.plan_name].filter(Boolean).join(' · ') || '-' }}</span>
            </div>
          </template>
        </Column>
        <Column field="model_name" header="모델" />
        <Column header="사용자" style="min-width:140px">
          <template #body="{ data }">
            <div class="stack-cell">
              <strong>{{ data.owner_name || '-' }}</strong>
              <small>{{ data.employee_number || '사번 미등록' }}</small>
            </div>
          </template>
        </Column>
        <Column field="department" header="부서">
          <template #body="{ data }">
            <div class="stack-cell">
              <strong>{{ data.department || '부서 미등록' }}</strong>
            </div>
          </template>
        </Column>
        <Column field="account_email" header="계정">
          <template #body="{ data }">{{ data.account_email || '-' }}</template>
        </Column>
        <Column header="비용">
          <template #body="{ data }">{{ currency(data.monthly_cost) }} / 월</template>
        </Column>
        <Column header="토큰">
          <template #body="{ data }">{{ tokenText(data) }}</template>
        </Column>
        <Column field="renewal_date" header="갱신일" sortable>
          <template #body="{ data }">{{ data.renewal_date || '-' }}</template>
        </Column>
        <Column field="status" header="상태">
          <template #body="{ data }"><Tag :value="statusLabel(data.status)" :severity="statusSeverity(data.status)" /></template>
        </Column>
        <Column style="width:90px">
          <template #body="{ data }">
            <Button icon="pi pi-pencil" text rounded size="small" @click="openEdit(data)" />
            <Button icon="pi pi-trash" text rounded size="small" severity="danger" @click="remove(data.id)" />
          </template>
        </Column>
      </DataTable>
      <Paginator v-if="!groupField" :rows="size" :totalRecords="total" :first="(page - 1) * size" @page="onPage" />
      <div v-else class="group-footer">그룹핑 보기: {{ displayItems.length }}건 표시</div>
    </div>

    <Dialog v-model:visible="showDialog" :header="editId !== null ? 'AI 구독 수정' : 'AI 구독 추가'" :modal="true" style="width:860px">
      <div class="form-grid three">
        <div class="field"><label>서비스명 *</label><InputText v-model="form.service_name" fluid /></div>
        <div class="field"><label>공급자</label><InputText v-model="form.provider" placeholder="OpenAI, Microsoft, Anthropic" fluid /></div>
        <div class="field"><label>모델</label><InputText v-model="form.model_name" placeholder="GPT-4.1, Copilot" fluid /></div>
        <div class="field"><label>플랜</label><InputText v-model="form.plan_name" fluid /></div>
        <div class="field"><label>계정 이메일</label><InputText v-model="form.account_email" fluid /></div>
        <div class="field"><label>사용자</label><InputText v-model="form.owner_name" fluid /></div>
        <div class="field"><label>사번</label><InputText v-model="form.employee_number" fluid /></div>
        <div class="field"><label>부서</label><InputText v-model="form.department" fluid /></div>
        <div class="field"><label>과금 주기</label><Select v-model="form.billing_cycle" :options="billingOptions" optionLabel="label" optionValue="value" showClear fluid /></div>
        <div class="field"><label>월 비용</label><InputNumber v-model="form.monthly_cost" mode="currency" currency="KRW" locale="ko-KR" fluid /></div>
        <div class="field"><label>토큰 한도</label><InputNumber v-model="form.token_limit" :useGrouping="true" fluid /></div>
        <div class="field"><label>사용 토큰</label><InputNumber v-model="form.used_tokens" :useGrouping="true" fluid /></div>
        <div class="field"><label>갱신일</label><InputText v-model="form.renewal_date" type="date" fluid /></div>
        <div class="field"><label>상태</label><Select v-model="form.status" :options="statusOptions" optionLabel="label" optionValue="value" fluid /></div>
        <label class="check-field"><Checkbox v-model="form.auto_renew" binary /><span>자동 갱신</span></label>
        <div class="field full"><label>사용 목적</label><Textarea v-model="form.usage_purpose" rows="2" fluid /></div>
        <div class="field full"><label>비고</label><Textarea v-model="form.notes" rows="2" fluid /></div>
      </div>
      <template #footer>
        <Button label="취소" severity="secondary" @click="showDialog = false" />
        <Button :label="editId !== null ? '수정' : '저장'" @click="save" />
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import Paginator from 'primevue/paginator'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import Textarea from 'primevue/textarea'
import { useToast } from 'primevue/usetoast'
import api from '@/api'
import type { AIUsageSubscription } from '@/types'
import { countGroup, groupValue, sortByGroup, type GroupOption } from '@/utils/grouping'

const toast = useToast()
const items = ref<AIUsageSubscription[]>([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)
const search = ref('')
const filterStatus = ref<string | null>(null)
const groupField = ref<string | null>(null)
const showDialog = ref(false)
const editId = ref<number | null>(null)

const statusOptions = [
  { label: '사용 중', value: 'active' },
  { label: '중지', value: 'inactive' },
  { label: '해지', value: 'cancelled' },
]
const billingOptions = [
  { label: '월간', value: 'monthly' },
  { label: '연간', value: 'yearly' },
  { label: '사용량 기반', value: 'usage' },
]
const groupOptions: GroupOption[] = [
  { label: '서비스 기준', value: 'service_name' },
  { label: '공급자 기준', value: 'provider' },
  { label: '모델 기준', value: 'model_name' },
  { label: '사용자 기준', value: 'owner_name' },
  { label: '사번 기준', value: 'employee_number' },
  { label: '부서 기준', value: 'department' },
  { label: '상태 기준', value: 'status', type: 'status' },
  { label: '과금 주기 기준', value: 'billing_cycle' },
  { label: '갱신일 기준', value: 'renewal_date' },
]

const form = ref<any>(emptyForm())
const currentGroupOption = computed(() => groupOptions.find((item) => item.value === groupField.value) ?? null)
const displayItems = computed(() => sortByGroup(items.value as unknown as Record<string, unknown>[], currentGroupOption.value, { status: statusLabel }) as unknown as AIUsageSubscription[])
const activeCount = computed(() => items.value.filter((item) => item.status === 'active').length)
const totalMonthlyCost = computed(() => items.value.reduce((sum, item) => sum + (item.monthly_cost || 0), 0))
const tokenUsageRate = computed(() => {
  const limit = items.value.reduce((sum, item) => sum + (item.token_limit || 0), 0)
  const used = items.value.reduce((sum, item) => sum + (item.used_tokens || 0), 0)
  if (!limit) return 0
  return Math.round((used / limit) * 100)
})

function emptyForm() {
  return {
    service_name: '',
    provider: '',
    model_name: '',
    plan_name: '',
    account_email: '',
    owner_name: '',
    employee_number: '',
    department: '',
    billing_cycle: 'monthly',
    monthly_cost: null,
    token_limit: null,
    used_tokens: null,
    renewal_date: '',
    auto_renew: false,
    status: 'active',
    usage_purpose: '',
    notes: '',
  }
}

async function load() {
  loading.value = true
  try {
    const params: any = { page: groupField.value ? 1 : page.value, size: groupField.value ? 1000 : size.value }
    if (search.value) params.search = search.value
    if (filterStatus.value) params.status = filterStatus.value
    const { data } = await api.get('/ai-subscriptions', { params })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function onPage(e: any) {
  page.value = e.page + 1
  void load()
}

function onGroupChange() {
  page.value = 1
  void load()
}

function openCreate() {
  editId.value = null
  form.value = emptyForm()
  showDialog.value = true
}

function openEdit(item: AIUsageSubscription) {
  editId.value = item.id
  form.value = { ...item }
  showDialog.value = true
}

async function save() {
  try {
    const payload = normalizePayload(form.value)
    if (editId.value !== null) await api.put(`/ai-subscriptions/${editId.value}`, payload)
    else await api.post('/ai-subscriptions', payload)
    toast.add({ severity: 'success', summary: '저장 완료', life: 3000 })
    showDialog.value = false
    editId.value = null
    void load()
  } catch (err: any) {
    toast.add({ severity: 'error', summary: '오류', detail: err.response?.data?.detail ?? '저장 실패', life: 5000 })
  }
}

async function remove(id: number) {
  await api.delete(`/ai-subscriptions/${id}`)
  void load()
}

function normalizePayload(source: Record<string, any>) {
  const payload = { ...source }
  Object.keys(payload).forEach((key) => {
    if (payload[key] === '') payload[key] = null
  })
  return payload
}

function statusLabel(value: string) {
  return statusOptions.find((item) => item.value === value)?.label ?? value
}

function statusSeverity(value: string): any {
  return { active: 'success', inactive: 'warn', cancelled: 'secondary' }[value] ?? 'secondary'
}

function currency(value: number | null | undefined) {
  if (!value) return '₩0'
  return `₩${value.toLocaleString('ko-KR')}`
}

function tokenText(item: AIUsageSubscription) {
  if (!item.token_limit && !item.used_tokens) return '-'
  return `${(item.used_tokens || 0).toLocaleString('ko-KR')} / ${(item.token_limit || 0).toLocaleString('ko-KR')}`
}

function groupHeader(item: AIUsageSubscription) {
  const option = currentGroupOption.value
  if (!option) return ''
  return `${option.label}: ${groupValue(item as unknown as Record<string, unknown>, option, { status: statusLabel })}`
}

function groupCount(item: AIUsageSubscription) {
  return countGroup(displayItems.value as unknown as Record<string, unknown>[], item as unknown as Record<string, unknown>, currentGroupOption.value, { status: statusLabel })
}

onMounted(load)
</script>

<style scoped>
.page-subtitle{margin-top:0.25rem;color:#64748b;font-size:0.9rem}
.summary-strip{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:0.75rem;margin-bottom:1rem}
.summary-item{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:0.85rem 1rem;display:flex;align-items:center;justify-content:space-between}
.summary-item span{color:#64748b;font-size:0.85rem;font-weight:600}.summary-item strong{color:#0f172a;font-size:1.15rem}
.identity-cell{display:flex;flex-direction:column;gap:0.2rem}.identity-cell strong{font-size:0.9rem;color:#0f172a}.identity-cell span{font-size:0.78rem;color:#64748b}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.form-grid.three{grid-template-columns:repeat(3,1fr)}.field{display:flex;flex-direction:column;gap:0.25rem}.field.full{grid-column:1/-1}.field label{font-size:0.85rem;font-weight:600;color:#475569}
.check-field{display:flex;align-items:center;gap:0.5rem;padding:0.65rem;border:1px solid #e2e8f0;border-radius:8px;font-size:0.9rem}
.group-header{width:100%;display:flex;align-items:center;justify-content:space-between;padding:0.45rem 0.25rem;color:#0f172a}.group-header span{font-weight:700}.group-header strong,.group-footer{color:#64748b;font-size:0.82rem}.group-footer{padding:0.85rem 0.25rem 0;text-align:right}
@media (max-width:900px){.summary-strip,.form-grid,.form-grid.three{grid-template-columns:1fr}}
</style>
