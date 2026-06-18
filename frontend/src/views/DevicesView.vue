<template>
  <div class="device-page">
    <div class="page-header">
      <div>
        <h1>디바이스</h1>
        <p class="page-subtitle">사번 기준으로 사용자, 장비 사양, 라이센스, 보안 설정을 함께 확인합니다.</p>
      </div>
      <div class="header-actions">
        <Button label="일괄 변경" icon="pi pi-pencil" severity="secondary" :disabled="selectedDevices.length === 0" @click="openBulkUpdate" />
        <Button label="디바이스 추가" icon="pi pi-plus" @click="openCreate" />
      </div>
    </div>

    <div class="summary-strip">
      <div class="summary-item"><span>전체</span><strong>{{ visibleTotal }}</strong></div>
      <div class="summary-item"><span>사용 중</span><strong>{{ assignedCount }}</strong></div>
      <div class="summary-item"><span>재고</span><strong>{{ stockCount }}</strong></div>
      <div class="summary-item"><span>교체됨</span><strong>{{ replacedCount }}</strong></div>
    </div>

    <nav class="device-type-subbar" aria-label="디바이스 종류">
      <button
        v-for="item in deviceTypeNavItems"
        :key="item.value ?? 'all'"
        type="button"
        class="device-type-tab"
        :class="{ active: filterType === item.value }"
        :style="deviceTypeToneStyle(item.tone)"
        :aria-pressed="filterType === item.value"
        @click="selectDeviceType(item.value)"
      >
        <span class="device-type-icon"><i :class="item.icon"></i></span>
        <span>{{ item.label }}</span>
      </button>
    </nav>

    <div class="filters-row">
      <IconField>
        <InputIcon class="pi pi-search" />
        <InputText v-model="search" placeholder="사용자, 사번, 시리얼, IP, MAC 검색" @keyup.enter="resetAndLoad" />
      </IconField>
      <Select v-model="filterType" :options="deviceTypeOptions" optionLabel="label" optionValue="value" placeholder="종류" showClear @change="applyDeviceTypeFilter" />
      <Select v-model="filterFactory" :options="factoryOptions" placeholder="공장" showClear @change="resetAndLoad" />
      <Select v-model="filterStatus" :options="statusOptions" optionLabel="label" optionValue="value" placeholder="상태" showClear @change="resetAndLoad" />
      <Select v-model="groupField" :options="groupOptions" optionLabel="label" optionValue="value" placeholder="그룹핑" showClear @change="onGroupChange" />
    </div>

    <section v-if="duplicateUserCandidates.length > 0" class="duplicate-panel">
      <header class="duplicate-panel-header">
        <div>
          <span><i class="pi pi-exclamation-triangle"></i> 중복 사용자 후보</span>
          <strong>같은 이름으로 나뉜 DB 정보 {{ duplicateUserCandidates.length }}건</strong>
        </div>
        <span class="duplicate-total">{{ duplicateDeviceCount }}대 확인 필요</span>
      </header>

      <div class="duplicate-name-list">
        <button
          v-for="candidate in duplicateUserCandidates"
          :key="candidate.nameKey"
          type="button"
          :class="{ active: activeDuplicate?.nameKey === candidate.nameKey }"
          @click="selectDuplicateCandidate(candidate)"
        >
          <strong>{{ candidate.displayName }}</strong>
          <span>{{ candidate.groups.length }}개 정보 / {{ candidate.deviceCount }}대</span>
        </button>
      </div>

      <div v-if="activeDuplicate" class="duplicate-merge-area">
        <label
          v-for="group in activeDuplicate.groups"
          :key="group.key"
          class="duplicate-identity-card"
          :class="{ active: mergeTargetKey === group.key }"
        >
          <input v-model="mergeTargetKey" type="radio" :value="group.key" />
          <div>
            <strong>{{ group.owner.user_name || '미지정' }}</strong>
            <span>{{ duplicateGroupLine(group) }}</span>
            <small>{{ deviceGroupSummary(group) }}</small>
          </div>
          <em>{{ group.devices.length }}대</em>
        </label>

        <div class="duplicate-merge-actions">
          <span>병합 대상 {{ mergeSourceDeviceCount }}대</span>
          <Button
            label="선택 정보로 병합"
            icon="pi pi-link"
            :disabled="!mergeTargetGroup || mergeSourceDeviceCount === 0"
            :loading="mergingDuplicate"
            @click="mergeDuplicateUser"
          />
        </div>
      </div>
    </section>

    <div v-if="selectedDevices.length > 0" class="bulk-toolbar">
      <strong>{{ selectedDevices.length }}개 선택됨</strong>
      <div>
        <Button label="선택 해제" icon="pi pi-times" text severity="secondary" @click="selectedDevices = []" />
        <Button label="일괄 변경" icon="pi pi-pencil" @click="openBulkUpdate" />
      </div>
    </div>

    <div class="device-board">
      <div v-if="loading && items.length === 0" class="device-list-state">디바이스 목록을 불러오는 중입니다.</div>
      <div v-else-if="displayGroups.length === 0" class="device-list-state">표시할 디바이스가 없습니다.</div>
      <template v-else>
        <section v-for="group in displayGroups" :key="group.key" class="device-owner-card">
          <header class="owner-card-header">
            <div class="owner-card-main">
              <Checkbox :modelValue="isGroupSelected(group)" binary @update:modelValue="(checked) => toggleGroupSelection(group, Boolean(checked))" />
              <div class="owner-avatar">{{ ownerInitial(group.owner) }}</div>
              <div class="owner-copy">
                <strong>{{ group.owner.user_name || '미지정' }}</strong>
                <span>{{ group.owner.employee_number || '사번 미등록' }}</span>
                <small>{{ group.owner.department || '부서 미등록' }}</small>
                <small>{{ ownerLocation(group.owner) }}</small>
              </div>
            </div>
            <div class="owner-card-meta">
              <span class="owner-device-summary">{{ deviceGroupSummary(group) }}</span>
              <strong>{{ group.devices.length }}대</strong>
            </div>
          </header>

          <div class="device-box-body">
            <section class="main-computer-section">
              <div class="section-title">
                <i class="pi pi-desktop"></i>
                <span>메인 컴퓨터</span>
              </div>
              <div v-if="group.mainDevices.length > 0" class="main-computer-list">
                <article v-for="device in group.mainDevices" :key="device.id" class="main-computer-card">
                  <Checkbox :modelValue="isDeviceSelected(device)" binary @update:modelValue="(checked) => toggleDeviceSelection(device, Boolean(checked))" />
                  <div class="device-summary-cell">
                    <strong>{{ device.serial_number || '시리얼 미등록' }}</strong>
                    <div class="device-meta-row">
                      <span class="device-type-chip" :style="deviceTypeBadgeStyle(device.device_type)">
                        <i :class="deviceTypeIcon(device.device_type)"></i>
                        {{ deviceTypeLabel(device.device_type) }}
                      </span>
                      <span class="status-pill" :class="`status-${device.status}`">{{ statusLabel(device.status) }}</span>
                    </div>
                  </div>
                  <div class="spec-list compact">
                    <span><b>CPU</b>{{ device.cpu || '-' }}</span>
                    <span><b>MEM</b>{{ device.memory || '-' }}</span>
                    <span><b>SSD/HDD</b>{{ device.storage || '-' }}</span>
                    <span><b>GPU</b>{{ device.gpu || '-' }}</span>
                  </div>
                  <div class="network-cell compact">
                    <strong>{{ device.os_version || '-' }}</strong>
                    <span><i class="pi pi-globe"></i>{{ device.ip_address || 'IP 미등록' }}</span>
                  </div>
                  <div class="health-stack compact">
                    <div class="health-row">
                      <span>라이센스</span>
                      <strong>{{ licenseCount(device) }}/8</strong>
                      <div class="health-track"><span :style="{ width: `${licenseScore(device)}%` }"></span></div>
                    </div>
                    <div class="health-row">
                      <span>보안 설정</span>
                      <strong>{{ settingCount(device) }}/4</strong>
                      <div class="health-track"><span :style="{ width: `${settingScore(device)}%` }"></span></div>
                    </div>
                  </div>
                  <div class="row-actions">
                    <Button icon="pi pi-history" text rounded size="small" v-tooltip="'이력'" @click="openHistory(device)" />
                    <Button icon="pi pi-sync" text rounded size="small" v-tooltip="'변경'" @click="openChange(device)" />
                    <Button icon="pi pi-pencil" text rounded size="small" v-tooltip="'수정'" @click="openEdit(device)" />
                    <Button icon="pi pi-trash" text rounded size="small" severity="danger" v-tooltip="'삭제'" @click="remove(device.id)" />
                  </div>
                </article>
              </div>
              <div v-else class="empty-main-computer">등록된 컴퓨터 없이 연결 장비만 있습니다.</div>
            </section>

            <section class="peripheral-section">
              <div class="section-title">
                <i class="pi pi-sitemap"></i>
                <span>연결 장비</span>
                <strong>{{ group.peripheralDevices.length }}</strong>
              </div>
              <div v-if="group.peripheralDevices.length > 0" class="peripheral-list">
                <article v-for="device in group.peripheralDevices" :key="device.id" class="peripheral-item">
                  <Checkbox :modelValue="isDeviceSelected(device)" binary @update:modelValue="(checked) => toggleDeviceSelection(device, Boolean(checked))" />
                  <span class="device-type-chip" :style="deviceTypeBadgeStyle(device.device_type)">
                    <i :class="deviceTypeIcon(device.device_type)"></i>
                    {{ deviceTypeLabel(device.device_type) }}
                  </span>
                  <strong>{{ device.serial_number || '시리얼 미등록' }}</strong>
                  <span>{{ device.ip_address || device.location || '위치/IP 미등록' }}</span>
                  <span class="status-pill" :class="`status-${device.status}`">{{ statusLabel(device.status) }}</span>
                  <div class="row-actions">
                    <Button icon="pi pi-history" text rounded size="small" v-tooltip="'이력'" @click="openHistory(device)" />
                    <Button icon="pi pi-sync" text rounded size="small" v-tooltip="'변경'" @click="openChange(device)" />
                    <Button icon="pi pi-pencil" text rounded size="small" v-tooltip="'수정'" @click="openEdit(device)" />
                    <Button icon="pi pi-trash" text rounded size="small" severity="danger" v-tooltip="'삭제'" @click="remove(device.id)" />
                  </div>
                </article>
              </div>
              <div v-else class="empty-peripheral">연결 장비 없음</div>
            </section>
          </div>
        </section>
      </template>
      <div v-if="!groupField" ref="scrollSentinel" class="scroll-sentinel">
        <span v-if="loading && items.length > 0">다음 항목을 불러오는 중입니다.</span>
        <span v-else-if="hasMore">아래로 스크롤하면 더 불러옵니다.</span>
        <span v-else>전체 {{ visibleTotal }}건 중 {{ displayItems.length }}건 표시</span>
      </div>
      <div v-else class="group-footer">그룹핑 보기: {{ displayGroups.length }}개 박스 / {{ displayItems.length }}건 표시</div>
    </div>

    <Dialog v-model:visible="showDeviceDialog" :header="editId !== null ? '디바이스 수정' : '디바이스 추가'" :modal="true" style="width:900px">
      <div class="form-grid three">
        <div class="field"><label>사용자</label><InputText v-model="form.user_name" fluid /></div>
        <div class="field"><label>사번</label><InputText v-model="form.employee_number" fluid /></div>
        <div class="field"><label>시리얼 번호 *</label><InputText v-model="form.serial_number" fluid /></div>
        <div class="field"><label>종류</label><Select v-model="form.device_type" :options="deviceTypeOptions" optionLabel="label" optionValue="value" fluid /></div>
        <div class="field"><label>CPU</label><InputText v-model="form.cpu" fluid /></div>
        <div class="field"><label>Memory</label><InputText v-model="form.memory" fluid /></div>
        <div class="field"><label>SSD or HDD</label><InputText v-model="form.storage" fluid /></div>
        <div class="field"><label>GPU</label><InputText v-model="form.gpu" fluid /></div>
        <div class="field"><label>OS ver</label><InputText v-model="form.os_version" fluid /></div>
        <div class="field"><label>IP</label><InputText v-model="form.ip_address" fluid /></div>
        <div class="field"><label>MAC</label><InputText v-model="form.mac_address" fluid /></div>
        <div class="field"><label>구매일</label><InputText v-model="form.purchase_date" type="date" fluid /></div>
        <div class="field"><label>생산일</label><InputText v-model="form.manufacture_date" type="date" fluid /></div>
        <div class="field"><label>장소</label><Select v-model="form.location" :options="locationOptions" optionLabel="label" optionValue="value" filter showClear fluid /></div>
        <div class="field"><label>부서</label><Select v-model="form.department" :options="departmentOptions" optionLabel="label" optionValue="value" filter showClear fluid /></div>
        <div class="field"><label>공장</label><Select v-model="form.factory" :options="factoryOptions" showClear fluid /></div>
        <div class="field"><label>상태</label><Select v-model="form.status" :options="statusOptions" optionLabel="label" optionValue="value" fluid /></div>
        <div class="field full"><label>비고</label><Textarea v-model="form.notes" rows="2" fluid /></div>
      </div>
      <template #footer>
        <Button label="취소" severity="secondary" @click="showDeviceDialog = false" />
        <Button :label="editId !== null ? '수정' : '저장'" @click="saveDevice" />
      </template>
    </Dialog>

    <Dialog v-model:visible="showChangeDialog" header="디바이스 변경" :modal="true" style="width:720px">
      <div class="change-target" v-if="selectedDevice">
        <strong>{{ selectedDevice.user_name || '미지정' }} / {{ selectedDevice.employee_number || '-' }}</strong>
        <span>{{ selectedDevice.serial_number }} · {{ deviceTypeLabel(selectedDevice.device_type) }}</span>
      </div>
      <div class="form-grid">
        <div class="field full"><label>변경 유형</label><Select v-model="changeForm.mode" :options="changeModes" optionLabel="label" optionValue="value" fluid /></div>
        <template v-if="changeForm.mode === 'transfer'">
          <div class="field"><label>새 사용자</label><InputText v-model="changeForm.user_name" fluid /></div>
          <div class="field"><label>새 사번</label><InputText v-model="changeForm.employee_number" fluid /></div>
          <div class="field"><label>부서</label><Select v-model="changeForm.department" :options="departmentOptions" optionLabel="label" optionValue="value" filter showClear fluid /></div>
          <div class="field"><label>장소</label><Select v-model="changeForm.location" :options="locationOptions" optionLabel="label" optionValue="value" filter showClear fluid /></div>
          <div class="field"><label>공장</label><Select v-model="changeForm.factory" :options="factoryOptions" showClear fluid /></div>
        </template>
        <template v-if="changeForm.mode === 'replace'">
          <div class="field"><label>새 시리얼 번호 *</label><InputText v-model="replaceForm.serial_number" fluid /></div>
          <div class="field"><label>종류</label><Select v-model="replaceForm.device_type" :options="deviceTypeOptions" optionLabel="label" optionValue="value" fluid /></div>
          <div class="field"><label>CPU</label><InputText v-model="replaceForm.cpu" fluid /></div>
          <div class="field"><label>Memory</label><InputText v-model="replaceForm.memory" fluid /></div>
          <div class="field"><label>SSD or HDD</label><InputText v-model="replaceForm.storage" fluid /></div>
          <div class="field"><label>OS ver</label><InputText v-model="replaceForm.os_version" fluid /></div>
        </template>
        <div class="field full"><label>메모</label><Textarea v-model="changeForm.notes" rows="2" fluid /></div>
      </div>
      <template #footer>
        <Button label="취소" severity="secondary" @click="showChangeDialog = false" />
        <Button label="적용" @click="submitChange" />
      </template>
    </Dialog>

    <Dialog v-model:visible="showBulkDialog" header="디바이스 일괄 변경" :modal="true" style="width:780px">
      <div class="change-target">
        <strong>{{ selectedDevices.length }}개 디바이스</strong>
      </div>
      <div class="form-grid">
        <div class="section-label full">소속 / 위치</div>
        <div class="bulk-field">
          <label class="bulk-toggle"><Checkbox v-model="bulkForm.apply_department" binary /><span>부서</span></label>
          <Select v-model="bulkForm.department" :options="departmentOptions" optionLabel="label" optionValue="value" filter showClear fluid :disabled="!bulkForm.apply_department" />
        </div>
        <div class="bulk-field">
          <label class="bulk-toggle"><Checkbox v-model="bulkForm.apply_location" binary /><span>장소</span></label>
          <Select v-model="bulkForm.location" :options="locationOptions" optionLabel="label" optionValue="value" filter showClear fluid :disabled="!bulkForm.apply_location" />
        </div>
        <div class="bulk-field">
          <label class="bulk-toggle"><Checkbox v-model="bulkForm.apply_factory" binary /><span>공장</span></label>
          <Select v-model="bulkForm.factory" :options="factoryOptions" showClear fluid :disabled="!bulkForm.apply_factory" />
        </div>
        <div class="bulk-field">
          <label class="bulk-toggle"><Checkbox v-model="bulkForm.apply_status" binary /><span>상태</span></label>
          <Select v-model="bulkForm.status" :options="statusOptions" optionLabel="label" optionValue="value" fluid :disabled="!bulkForm.apply_status" />
        </div>

        <div class="section-label full">장비 정보</div>
        <div class="bulk-field">
          <label class="bulk-toggle"><Checkbox v-model="bulkForm.apply_device_type" binary /><span>종류</span></label>
          <Select v-model="bulkForm.device_type" :options="deviceTypeOptions" optionLabel="label" optionValue="value" fluid :disabled="!bulkForm.apply_device_type" />
        </div>
        <div class="bulk-field">
          <label class="bulk-toggle"><Checkbox v-model="bulkForm.apply_cpu" binary /><span>CPU</span></label>
          <InputText v-model="bulkForm.cpu" fluid :disabled="!bulkForm.apply_cpu" />
        </div>
        <div class="bulk-field">
          <label class="bulk-toggle"><Checkbox v-model="bulkForm.apply_memory" binary /><span>Memory</span></label>
          <InputText v-model="bulkForm.memory" fluid :disabled="!bulkForm.apply_memory" />
        </div>
        <div class="bulk-field">
          <label class="bulk-toggle"><Checkbox v-model="bulkForm.apply_storage" binary /><span>SSD/HDD</span></label>
          <InputText v-model="bulkForm.storage" fluid :disabled="!bulkForm.apply_storage" />
        </div>
        <div class="bulk-field">
          <label class="bulk-toggle"><Checkbox v-model="bulkForm.apply_gpu" binary /><span>GPU</span></label>
          <InputText v-model="bulkForm.gpu" fluid :disabled="!bulkForm.apply_gpu" />
        </div>
        <div class="bulk-field">
          <label class="bulk-toggle"><Checkbox v-model="bulkForm.apply_os_version" binary /><span>OS ver</span></label>
          <InputText v-model="bulkForm.os_version" fluid :disabled="!bulkForm.apply_os_version" />
        </div>

        <div class="section-label full">보안 설정</div>
        <div class="bulk-field">
          <label class="bulk-toggle"><Checkbox v-model="bulkForm.apply_smart_app_control" binary /><span>스마트 앱 컨트롤</span></label>
          <Select v-model="bulkForm.smart_app_control" :options="booleanOptions" optionLabel="label" optionValue="value" fluid :disabled="!bulkForm.apply_smart_app_control" />
        </div>
        <div class="bulk-field">
          <label class="bulk-toggle"><Checkbox v-model="bulkForm.apply_reputation_based_protection" binary /><span>평판기반 보호</span></label>
          <Select v-model="bulkForm.reputation_based_protection" :options="booleanOptions" optionLabel="label" optionValue="value" fluid :disabled="!bulkForm.apply_reputation_based_protection" />
        </div>
        <div class="bulk-field">
          <label class="bulk-toggle"><Checkbox v-model="bulkForm.apply_exploit_protection" binary /><span>Exploit Protection</span></label>
          <Select v-model="bulkForm.exploit_protection" :options="booleanOptions" optionLabel="label" optionValue="value" fluid :disabled="!bulkForm.apply_exploit_protection" />
        </div>
        <div class="bulk-field">
          <label class="bulk-toggle"><Checkbox v-model="bulkForm.apply_core_isolation" binary /><span>장치보안 코어 격리</span></label>
          <Select v-model="bulkForm.core_isolation" :options="booleanOptions" optionLabel="label" optionValue="value" fluid :disabled="!bulkForm.apply_core_isolation" />
        </div>

        <div class="field full"><label>변경 사유</label><InputText v-model="bulkForm.reason" fluid /></div>
        <div class="field full"><label>메모</label><Textarea v-model="bulkForm.notes" rows="2" fluid /></div>
      </div>
      <template #footer>
        <Button label="취소" severity="secondary" @click="showBulkDialog = false" />
        <Button label="적용" :loading="savingBulk" @click="submitBulkUpdate" />
      </template>
    </Dialog>

    <Dialog v-model:visible="showHistoryDialog" header="사용 이력" :modal="true" style="width:760px">
      <DataTable :value="historyItems" size="small" stripedRows>
        <Column header="사용자">
          <template #body="{ data }">
            <div class="stack-cell">
              <strong>{{ data.user_name || '-' }}</strong>
              <small>{{ data.employee_number || '사번 미등록' }}</small>
            </div>
          </template>
        </Column>
        <Column field="serial_number" header="시리얼" />
        <Column field="change_reason" header="사유" />
        <Column field="started_at" header="시작" />
        <Column field="ended_at" header="종료">
          <template #body="{ data }">{{ data.ended_at || '사용 중' }}</template>
        </Column>
      </DataTable>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Textarea from 'primevue/textarea'
import { useToast } from 'primevue/usetoast'
import api from '@/api'
import type { Department, DeviceRecord, DeviceUsageHistory, Location } from '@/types'
import { sortByGroup, type GroupOption } from '@/utils/grouping'

type DeviceGroup = {
  key: string
  owner: DeviceRecord
  devices: DeviceRecord[]
  mainDevices: DeviceRecord[]
  peripheralDevices: DeviceRecord[]
}

type DuplicateUserCandidate = {
  nameKey: string
  displayName: string
  groups: DeviceGroup[]
  deviceCount: number
}

const route = useRoute()
const router = useRouter()
const toast = useToast()
const items = ref<DeviceRecord[]>([])
const historyItems = ref<DeviceUsageHistory[]>([])
const departments = ref<Department[]>([])
const locations = ref<Location[]>([])
const loading = ref(false)
const page = ref(1)
const total = ref(0)
const hasMore = ref(true)
const search = ref('')
const filterType = ref<string | null>(null)
const filterFactory = ref<string | null>(null)
const filterStatus = ref<string | null>(null)
const groupField = ref<string | null>(null)
const showDeviceDialog = ref(false)
const showChangeDialog = ref(false)
const showBulkDialog = ref(false)
const showHistoryDialog = ref(false)
const editId = ref<number | null>(null)
const selectedDevice = ref<DeviceRecord | null>(null)
const selectedDevices = ref<DeviceRecord[]>([])
const savingBulk = ref(false)
const selectedDuplicateName = ref<string | null>(null)
const mergeTargetKey = ref<string | null>(null)
const mergingDuplicate = ref(false)
const scrollSentinel = ref<HTMLElement | null>(null)
let scrollObserver: IntersectionObserver | null = null
let loadRequestId = 0

const deviceTypeOptions = [
  { label: '데스크탑', value: 'desktop' },
  { label: '랩탑', value: 'laptop' },
  { label: '모니터', value: 'monitor' },
  { label: '일체형', value: 'all_in_one' },
  { label: '빔프로젝터', value: 'projector' },
  { label: 'TV', value: 'tv' },
  { label: '프린터', value: 'printer' },
  { label: '기타', value: 'unknown' },
]
const deviceTypeIconMap: Record<string, string> = {
  desktop: 'pi pi-desktop',
  laptop: 'pi pi-desktop',
  printer: 'pi pi-print',
  monitor: 'pi pi-desktop',
  all_in_one: 'pi pi-window-maximize',
  projector: 'pi pi-video',
  tv: 'pi pi-desktop',
  unknown: 'pi pi-box',
}
const deviceTypeToneMap: Record<string, { surface: string; border: string; text: string }> = {
  all: { surface: '#f1f5f9', border: '#cbd5e1', text: '#475569' },
  desktop: { surface: '#e0f2fe', border: '#bae6fd', text: '#0369a1' },
  laptop: { surface: '#eef2ff', border: '#c7d2fe', text: '#4f46e5' },
  printer: { surface: '#ecfdf5', border: '#bbf7d0', text: '#15803d' },
  monitor: { surface: '#fff7ed', border: '#fed7aa', text: '#c2410c' },
  all_in_one: { surface: '#fdf2f8', border: '#fbcfe8', text: '#be185d' },
  projector: { surface: '#f5f3ff', border: '#ddd6fe', text: '#6d28d9' },
  tv: { surface: '#fefce8', border: '#fde68a', text: '#a16207' },
  unknown: { surface: '#f0fdfa', border: '#99f6e4', text: '#0f766e' },
}
const deviceTypeNavOrder = ['desktop', 'laptop', 'printer', 'monitor', 'all_in_one', 'projector', 'tv', 'unknown']
const computerDeviceTypes = new Set(['desktop', 'laptop', 'all_in_one'])
const factoryOptions = ['1공장', '2공장', '3공장', '본관', '연구소']
const statusOptions = [
  { label: '사용 중', value: 'assigned' },
  { label: '재고', value: 'stock' },
  { label: '교체됨', value: 'replaced' },
  { label: '퇴역', value: 'retired' },
]
const changeModes = [
  { label: '다른 사용자에게 지급', value: 'transfer' },
  { label: '퇴사 처리', value: 'resign' },
  { label: '장비 교체', value: 'replace' },
]
const booleanOptions = [
  { label: '적용', value: true },
  { label: '해제', value: false },
]
const groupOptions: GroupOption[] = [
  { label: '사용자 기준', value: 'user_name' },
  { label: '사번 기준', value: 'employee_number' },
  { label: '부서 기준', value: 'department' },
  { label: '위치 기준', value: 'location' },
  { label: '공장 기준', value: 'factory' },
  { label: '종류 기준', value: 'device_type', type: 'deviceType' },
  { label: '상태 기준', value: 'status', type: 'status' },
  { label: 'CPU 기준', value: 'cpu' },
  { label: 'Memory 기준', value: 'memory' },
  { label: 'SSD/HDD 기준', value: 'storage' },
  { label: 'GPU 기준', value: 'gpu' },
  { label: 'OS 기준', value: 'os_version' },
  { label: 'IP 기준', value: 'ip_address' },
  { label: 'MAC 기준', value: 'mac_address' },
  { label: '시리얼 기준', value: 'serial_number' },
]

const emptyForm = () => ({
  user_name: '',
  employee_number: '',
  serial_number: '',
  device_type: 'desktop',
  cpu: '',
  memory: '',
  storage: '',
  gpu: '',
  os_version: '',
  ip_address: '',
  mac_address: '',
  purchase_date: '',
  manufacture_date: '',
  location: '',
  department: '',
  factory: '',
  status: 'assigned',
  notes: '',
})

const form = ref<any>(emptyForm())
const changeForm = ref<any>({ mode: 'transfer', user_name: '', employee_number: '', location: '', department: '', factory: '', notes: '' })
const replaceForm = ref<any>(emptyForm())
const emptyBulkForm = () => ({
  apply_department: false,
  department: null,
  apply_location: false,
  location: null,
  apply_factory: false,
  factory: null,
  apply_status: false,
  status: null,
  apply_device_type: false,
  device_type: null,
  apply_cpu: false,
  cpu: '',
  apply_memory: false,
  memory: '',
  apply_storage: false,
  storage: '',
  apply_gpu: false,
  gpu: '',
  apply_os_version: false,
  os_version: '',
  apply_smart_app_control: false,
  smart_app_control: true,
  apply_reputation_based_protection: false,
  reputation_based_protection: true,
  apply_exploit_protection: false,
  exploit_protection: true,
  apply_core_isolation: false,
  core_isolation: true,
  reason: '일괄 변경',
  notes: '',
})
const bulkForm = ref<any>(emptyBulkForm())
const deviceDateFields = ['purchase_date', 'manufacture_date']
const requiredDeviceTextFields = new Set(['serial_number', 'device_type', 'status'])

const currentGroupOption = computed(() => groupOptions.find((item) => item.value === groupField.value) ?? null)
const groupFormatters = { deviceType: deviceTypeLabel, status: statusLabel }
const sortedItems = computed(() => sortByGroup(items.value as unknown as Record<string, unknown>[], currentGroupOption.value, groupFormatters) as unknown as DeviceRecord[])
const allDeviceGroups = computed(() => buildDeviceGroups(sortedItems.value))
const displayGroups = computed(() => {
  if (!filterType.value) return allDeviceGroups.value
  return allDeviceGroups.value.filter((group) => group.devices.some((device) => device.device_type === filterType.value))
})
const displayItems = computed(() => displayGroups.value.flatMap((group) => group.devices))
const visibleTotal = computed(() => displayItems.value.length)
const assignedCount = computed(() => displayItems.value.filter((item) => item.status === 'assigned').length)
const stockCount = computed(() => displayItems.value.filter((item) => item.status === 'stock').length)
const replacedCount = computed(() => displayItems.value.filter((item) => item.status === 'replaced').length)
const duplicateUserCandidates = computed(() => buildDuplicateUserCandidates(allDeviceGroups.value))
const duplicateDeviceCount = computed(() => duplicateUserCandidates.value.reduce((sum, candidate) => sum + candidate.deviceCount, 0))
const activeDuplicate = computed(() => {
  return duplicateUserCandidates.value.find((candidate) => candidate.nameKey === selectedDuplicateName.value) ?? duplicateUserCandidates.value[0] ?? null
})
const mergeTargetGroup = computed(() => {
  if (!activeDuplicate.value || !mergeTargetKey.value) return null
  return activeDuplicate.value.groups.find((group) => group.key === mergeTargetKey.value) ?? null
})
const mergeSourceGroups = computed(() => {
  if (!activeDuplicate.value || !mergeTargetGroup.value) return []
  return activeDuplicate.value.groups.filter((group) => group.key !== mergeTargetGroup.value?.key)
})
const mergeSourceDeviceCount = computed(() => mergeSourceGroups.value.reduce((sum, group) => sum + group.devices.length, 0))
const deviceTypeNavItems = computed(() => [
  { label: '전체', value: null, icon: 'pi pi-list', tone: deviceTypeToneMap.all },
  ...deviceTypeNavOrder
    .map((value) => deviceTypeOptions.find((item) => item.value === value))
    .filter((item): item is (typeof deviceTypeOptions)[number] => Boolean(item))
    .map((item) => ({
      ...item,
      icon: deviceTypeIconMap[item.value] ?? 'pi pi-box',
      tone: deviceTypeToneMap[item.value] ?? deviceTypeToneMap.unknown,
    })),
])
const departmentOptions = computed(() =>
  departments.value.map((item) => ({ label: item.name, value: item.name })),
)
const locationOptions = computed(() =>
  locations.value
    .filter((item) => item.type !== 'factory')
    .map((item) => ({ label: item.name, value: item.name })),
)

function routeSearchValue() {
  return typeof route.query.search === 'string' ? route.query.search : ''
}

function routeDeviceTypeValue() {
  const value = typeof route.query.device_type === 'string' ? route.query.device_type : null
  return deviceTypeOptions.some((item) => item.value === value) ? value : null
}

async function load(reset = true) {
  if (loading.value) return
  if (!reset && (!hasMore.value || groupField.value)) return

  const requestId = ++loadRequestId
  const nextPage = reset || groupField.value ? 1 : page.value + 1

  if (reset) {
    page.value = 1
    items.value = []
    hasMore.value = true
  }

  loading.value = true
  try {
    const params: any = { page: nextPage, size: 1000 }
    if (search.value) params.search = search.value
    if (filterFactory.value) params.factory = filterFactory.value
    if (filterStatus.value) params.status = filterStatus.value
    const { data } = await api.get('/devices', { params })

    if (requestId !== loadRequestId) return

    items.value = reset || groupField.value ? data.items : [...items.value, ...data.items]
    total.value = data.total
    page.value = nextPage
    hasMore.value = !groupField.value && items.value.length < data.total && data.items.length > 0
  } finally {
    if (requestId === loadRequestId) {
      loading.value = false
    }
  }
}

async function loadOrgOptions() {
  const [deptRes, locRes] = await Promise.all([
    api.get<Department[]>('/departments'),
    api.get<Location[]>('/locations'),
  ])
  departments.value = deptRes.data
  locations.value = locRes.data
}

function resetAndLoad() {
  selectedDevices.value = []
  void load(true)
}

function deviceTypeToneStyle(tone: { surface: string; border: string; text: string }) {
  return {
    '--device-type-surface': tone.surface,
    '--device-type-border': tone.border,
    '--device-type-text': tone.text,
  }
}

function selectDeviceType(value: string | null) {
  if (filterType.value === value && routeDeviceTypeValue() === value) return
  void updateDeviceTypeQuery(value)
}

function applyDeviceTypeFilter() {
  void updateDeviceTypeQuery(filterType.value)
}

async function updateDeviceTypeQuery(value: string | null) {
  const query = { ...route.query }
  if (value) query.device_type = value
  else delete query.device_type

  if (routeDeviceTypeValue() !== value) {
    filterType.value = value
    await router.replace({ query })
  }
  resetAndLoad()
}

function loadMore() {
  void load(false)
}

function observeScrollSentinel(el: HTMLElement | null) {
  if (!scrollObserver || !el) return
  scrollObserver.observe(el)
}

function onGroupChange() {
  resetAndLoad()
}

function openBulkUpdate() {
  if (selectedDevices.value.length === 0) {
    toast.add({ severity: 'warn', summary: '선택 필요', detail: '일괄 변경할 디바이스를 선택하세요.', life: 3000 })
    return
  }
  bulkForm.value = emptyBulkForm()
  void loadOrgOptions()
  showBulkDialog.value = true
}

function bulkTextValue(value: unknown) {
  return value === '' ? null : value
}

function buildBulkPayload() {
  const updates: Record<string, unknown> = {}
  const settings: Record<string, unknown> = {}
  const form = bulkForm.value

  if (form.apply_department) updates.department = form.department
  if (form.apply_location) updates.location = form.location
  if (form.apply_factory) updates.factory = form.factory
  if (form.apply_status) updates.status = form.status
  if (form.apply_device_type) updates.device_type = form.device_type
  if (form.apply_cpu) updates.cpu = bulkTextValue(form.cpu)
  if (form.apply_memory) updates.memory = bulkTextValue(form.memory)
  if (form.apply_storage) updates.storage = bulkTextValue(form.storage)
  if (form.apply_gpu) updates.gpu = bulkTextValue(form.gpu)
  if (form.apply_os_version) updates.os_version = bulkTextValue(form.os_version)

  if (form.apply_smart_app_control) settings.smart_app_control = form.smart_app_control
  if (form.apply_reputation_based_protection) settings.reputation_based_protection = form.reputation_based_protection
  if (form.apply_exploit_protection) settings.exploit_protection = form.exploit_protection
  if (form.apply_core_isolation) settings.core_isolation = form.core_isolation

  const payload: Record<string, unknown> = {
    device_ids: selectedDevices.value.map((item) => item.id),
    updates,
    reason: form.reason || '일괄 변경',
    notes: form.notes || null,
  }
  if (Object.keys(settings).length > 0) payload.computer_setting = settings
  return payload
}

function validateBulkForm() {
  if (bulkForm.value.apply_status && !bulkForm.value.status) return '상태를 선택하세요.'
  if (bulkForm.value.apply_device_type && !bulkForm.value.device_type) return '종류를 선택하세요.'
  return ''
}

function openCreate() {
  editId.value = null
  form.value = emptyForm()
  void loadOrgOptions()
  showDeviceDialog.value = true
}

function openEdit(item: DeviceRecord) {
  editId.value = item.id
  form.value = { ...item }
  void loadOrgOptions()
  showDeviceDialog.value = true
}

function openChange(item: DeviceRecord) {
  selectedDevice.value = item
  changeForm.value = {
    mode: 'transfer',
    user_name: '',
    employee_number: '',
    location: item.location || '',
    department: item.department || '',
    factory: item.factory || '',
    notes: '',
  }
  replaceForm.value = { ...emptyForm(), user_name: item.user_name || '', employee_number: item.employee_number || '', location: item.location || '', department: item.department || '', factory: item.factory || '' }
  void loadOrgOptions()
  showChangeDialog.value = true
}

async function openHistory(item: DeviceRecord) {
  selectedDevice.value = item
  const { data } = await api.get<DeviceUsageHistory[]>(`/devices/${item.id}/history`)
  historyItems.value = data
  showHistoryDialog.value = true
}

async function saveDevice() {
  try {
    const payload = normalizePayload(form.value, deviceDateFields)
    const validationMessage = validateDevicePayload(payload)
    if (validationMessage) {
      toast.add({ severity: 'warn', summary: '확인 필요', detail: validationMessage, life: 3000 })
      return
    }
    if (editId.value !== null) {
      await api.put(`/devices/${editId.value}`, payload)
    } else {
      await api.post('/devices', payload)
    }
    toast.add({ severity: 'success', summary: '저장 완료', life: 3000 })
    showDeviceDialog.value = false
    resetAndLoad()
  } catch (err: any) {
    toast.add({ severity: 'error', summary: '오류', detail: err.response?.data?.detail ?? '저장 실패', life: 5000 })
  }
}

async function submitChange() {
  if (!selectedDevice.value) return
  try {
    if (changeForm.value.mode === 'replace') {
      const payload = normalizePayload(replaceForm.value, deviceDateFields)
      const validationMessage = validateDevicePayload(payload)
      if (validationMessage) {
        toast.add({ severity: 'warn', summary: '확인 필요', detail: validationMessage, life: 3000 })
        return
      }
      await api.post(`/devices/${selectedDevice.value.id}/replace`, {
        ...payload,
        replacement_reason: '교체',
      })
    } else {
      const isResign = changeForm.value.mode === 'resign'
      await api.post(`/devices/${selectedDevice.value.id}/reassign`, {
        user_name: isResign ? null : changeForm.value.user_name,
        employee_number: isResign ? null : changeForm.value.employee_number,
        location: changeForm.value.location,
        department: changeForm.value.department,
        factory: changeForm.value.factory,
        reason: isResign ? '퇴사' : '사용자 변경',
        notes: changeForm.value.notes,
      })
    }
    toast.add({ severity: 'success', summary: '변경 완료', life: 3000 })
    showChangeDialog.value = false
    resetAndLoad()
  } catch (err: any) {
    toast.add({ severity: 'error', summary: '오류', detail: err.response?.data?.detail ?? '변경 실패', life: 5000 })
  }
}

async function submitBulkUpdate() {
  const validationMessage = validateBulkForm()
  if (validationMessage) {
    toast.add({ severity: 'warn', summary: '확인 필요', detail: validationMessage, life: 3000 })
    return
  }

  const payload = buildBulkPayload()
  const hasDeviceUpdates = Object.keys(payload.updates as Record<string, unknown>).length > 0
  const hasSettingUpdates = Boolean(payload.computer_setting)
  if (!hasDeviceUpdates && !hasSettingUpdates) {
    toast.add({ severity: 'warn', summary: '확인 필요', detail: '변경할 항목을 선택하세요.', life: 3000 })
    return
  }

  savingBulk.value = true
  try {
    const { data } = await api.post('/devices/bulk-update', payload)
    toast.add({ severity: 'success', summary: '일괄 변경 완료', detail: `${data.updated ?? selectedDevices.value.length}개 디바이스가 변경되었습니다.`, life: 3000 })
    showBulkDialog.value = false
    selectedDevices.value = []
    resetAndLoad()
  } catch (err: any) {
    toast.add({ severity: 'error', summary: '오류', detail: err.response?.data?.detail ?? '일괄 변경 실패', life: 5000 })
  } finally {
    savingBulk.value = false
  }
}

async function remove(id: number) {
  await api.delete(`/devices/${id}`)
  resetAndLoad()
}

function textOrNull(value: string | null | undefined) {
  const text = (value ?? '').trim()
  return text || null
}

function normalizedUserName(value: string | null) {
  return (value ?? '').trim().replace(/\s+/g, '').toLocaleLowerCase()
}

function buildDuplicateUserCandidates(groups: DeviceGroup[]): DuplicateUserCandidate[] {
  const buckets = new Map<string, DeviceGroup[]>()
  groups.forEach((group) => {
    const nameKey = normalizedUserName(group.owner.user_name)
    if (!nameKey) return
    const existing = buckets.get(nameKey)
    if (existing) existing.push(group)
    else buckets.set(nameKey, [group])
  })

  return Array.from(buckets.entries())
    .map(([nameKey, matchedGroups]) => {
      const distinctGroups = matchedGroups.filter(
        (group, index, source) => source.findIndex((item) => item.key === group.key) === index,
      )
      return {
        nameKey,
        displayName: distinctGroups[0]?.owner.user_name || nameKey,
        groups: distinctGroups,
        deviceCount: distinctGroups.reduce((sum, group) => sum + group.devices.length, 0),
      }
    })
    .filter((candidate) => candidate.groups.length > 1)
    .sort((a, b) => b.deviceCount - a.deviceCount || a.displayName.localeCompare(b.displayName))
}

function selectDuplicateCandidate(candidate: DuplicateUserCandidate) {
  selectedDuplicateName.value = candidate.nameKey
  mergeTargetKey.value = candidate.groups[0]?.key ?? null
}

function duplicateGroupLine(group: DeviceGroup) {
  return [
    group.owner.employee_number || '사번 미등록',
    group.owner.department || '부서 미등록',
    ownerLocation(group.owner),
  ].join(' · ')
}

async function mergeDuplicateUser() {
  const duplicate = activeDuplicate.value
  const targetGroup = mergeTargetGroup.value
  if (!duplicate || !targetGroup) {
    toast.add({ severity: 'warn', summary: '확인 필요', detail: '병합 기준 정보를 선택하세요.', life: 3000 })
    return
  }

  const sourceDeviceIds = mergeSourceGroups.value.flatMap((group) => group.devices.map((device) => device.id))
  if (sourceDeviceIds.length === 0) {
    toast.add({ severity: 'warn', summary: '확인 필요', detail: '병합할 대상 디바이스가 없습니다.', life: 3000 })
    return
  }

  mergingDuplicate.value = true
  try {
    const target = {
      user_name: textOrNull(targetGroup.owner.user_name),
      employee_number: textOrNull(targetGroup.owner.employee_number),
      department: textOrNull(targetGroup.owner.department),
      location: textOrNull(targetGroup.owner.location),
      factory: textOrNull(targetGroup.owner.factory),
    }
    const { data } = await api.post('/devices/merge-users', {
      device_ids: sourceDeviceIds,
      target,
      reason: '중복 사용자 정보 병합',
      notes: `${duplicate.displayName} 중복 정보를 ${duplicateGroupLine(targetGroup)} 기준으로 병합`,
    })
    toast.add({ severity: 'success', summary: '병합 완료', detail: `${data.updated ?? sourceDeviceIds.length}개 디바이스 정보가 정리되었습니다.`, life: 3000 })
    selectedDuplicateName.value = null
    mergeTargetKey.value = null
    resetAndLoad()
  } catch (err: any) {
    toast.add({ severity: 'error', summary: '오류', detail: err.response?.data?.detail ?? '병합 실패', life: 5000 })
  } finally {
    mergingDuplicate.value = false
  }
}

function deviceTypeLabel(value: string) {
  return deviceTypeOptions.find((item) => item.value === value)?.label ?? value
}

function deviceTypeIcon(value: string) {
  return deviceTypeIconMap[value] ?? 'pi pi-box'
}

function deviceTypeBadgeStyle(value: string) {
  return deviceTypeToneStyle(deviceTypeToneMap[value] ?? deviceTypeToneMap.unknown)
}

function statusLabel(value: string) {
  return statusOptions.find((item) => item.value === value)?.label ?? value
}

function ownerInitial(item: DeviceRecord) {
  return (item.user_name || item.department || '?').trim().slice(0, 1) || '?'
}

function ownerLocation(item: DeviceRecord) {
  return [item.factory, item.location].filter(Boolean).join(' · ') || '위치 미등록'
}

function scorePercent(value: number, max: number) {
  return Math.min(100, Math.max(0, Math.round((value / max) * 100)))
}

function licenseScore(item: DeviceRecord) {
  return scorePercent(licenseCount(item), 8)
}

function settingScore(item: DeviceRecord) {
  return scorePercent(settingCount(item), 4)
}

function ownerGroupKey(item: DeviceRecord) {
  return [item.department || '', item.employee_number || '', item.user_name || ''].join('|')
}

function isComputerDevice(item: DeviceRecord) {
  return computerDeviceTypes.has(item.device_type)
}

function buildDeviceGroups(devices: DeviceRecord[]): DeviceGroup[] {
  const groups = new Map<string, DeviceGroup>()
  devices.forEach((device) => {
    const key = ownerGroupKey(device)
    const existing = groups.get(key)
    if (existing) {
      existing.devices.push(device)
    } else {
      groups.set(key, {
        key,
        owner: device,
        devices: [device],
        mainDevices: [],
        peripheralDevices: [],
      })
    }
  })

  return Array.from(groups.values()).map((group) => {
    const mainDevices = group.devices.filter(isComputerDevice)
    const peripheralDevices = group.devices.filter((device) => !isComputerDevice(device))
    return { ...group, mainDevices, peripheralDevices }
  })
}

function deviceGroupSummary(group: DeviceGroup) {
  const computerCount = group.mainDevices.length
  const monitorCount = group.devices.filter((entry) => entry.device_type === 'monitor').length
  const printerCount = group.devices.filter((entry) => entry.device_type === 'printer').length
  const etcCount = group.devices.length - computerCount - monitorCount - printerCount
  return [
    computerCount ? `컴퓨터 ${computerCount}` : '',
    monitorCount ? `모니터 ${monitorCount}` : '',
    printerCount ? `프린터 ${printerCount}` : '',
    etcCount ? `기타 ${etcCount}` : '',
  ].filter(Boolean).join(' · ') || '장비 1'
}

function isDeviceSelected(device: DeviceRecord) {
  return selectedDevices.value.some((item) => item.id === device.id)
}

function toggleDeviceSelection(device: DeviceRecord, checked: boolean) {
  if (checked) {
    if (!isDeviceSelected(device)) selectedDevices.value = [...selectedDevices.value, device]
    return
  }
  selectedDevices.value = selectedDevices.value.filter((item) => item.id !== device.id)
}

function isGroupSelected(group: DeviceGroup) {
  return group.devices.length > 0 && group.devices.every(isDeviceSelected)
}

function toggleGroupSelection(group: DeviceGroup, checked: boolean) {
  if (checked) {
    const selectedIds = new Set(selectedDevices.value.map((item) => item.id))
    selectedDevices.value = [...selectedDevices.value, ...group.devices.filter((device) => !selectedIds.has(device.id))]
    return
  }
  const groupIds = new Set(group.devices.map((device) => device.id))
  selectedDevices.value = selectedDevices.value.filter((device) => !groupIds.has(device.id))
}

function licenseCount(item: DeviceRecord) {
  const license = item.license_summary
  if (!license) return 0
  return ['hangul', 'ms_office', 'cad', 'windows_security', 'pc_manager', 'dlp', 'av', 'edr'].filter((key) => Boolean((license as any)[key])).length
}

function settingCount(item: DeviceRecord) {
  const setting = item.computer_setting_summary
  if (!setting) return 0
  return ['smart_app_control', 'reputation_based_protection', 'exploit_protection', 'core_isolation'].filter((key) => Boolean((setting as any)[key])).length
}

function normalizePayload(source: Record<string, any>, dateFields: string[]) {
  const payload = { ...source }
  Object.keys(payload).forEach((field) => {
    if (typeof payload[field] === 'string') {
      const value = payload[field].trim()
      payload[field] = value === '' && !requiredDeviceTextFields.has(field) ? null : value
    }
  })
  dateFields.forEach((field) => {
    if (payload[field] === '') payload[field] = null
  })
  return payload
}

function validateDevicePayload(payload: Record<string, any>) {
  if (!payload.serial_number) return '시리얼 번호를 입력하세요.'
  return ''
}

watch(duplicateUserCandidates, (candidates) => {
  const active = candidates.find((candidate) => candidate.nameKey === selectedDuplicateName.value) ?? candidates[0] ?? null
  selectedDuplicateName.value = active?.nameKey ?? null
  if (!active) {
    mergeTargetKey.value = null
    return
  }
  if (!active.groups.some((group) => group.key === mergeTargetKey.value)) {
    mergeTargetKey.value = active.groups[0]?.key ?? null
  }
})

watch(
  () => [route.query.search, route.query.device_type],
  () => {
    const nextSearch = routeSearchValue()
    const nextType = routeDeviceTypeValue()
    let shouldReload = false
    if (nextSearch !== search.value) {
      search.value = nextSearch
      shouldReload = true
    }
    if (nextType !== filterType.value) {
      filterType.value = nextType
      shouldReload = true
    }
    if (shouldReload) resetAndLoad()
  },
)

watch(scrollSentinel, (next, previous) => {
  if (previous) {
    scrollObserver?.unobserve(previous)
  }
  observeScrollSentinel(next)
})

onMounted(() => {
  search.value = routeSearchValue()
  filterType.value = routeDeviceTypeValue()
  void loadOrgOptions()
  resetAndLoad()
  scrollObserver = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        loadMore()
      }
    },
    { root: null, rootMargin: '800px 0px', threshold: 0.01 },
  )

  if (scrollSentinel.value) {
    observeScrollSentinel(scrollSentinel.value)
  }
})

onBeforeUnmount(() => {
  scrollObserver?.disconnect()
})
</script>

<style scoped>
.device-page {
  width: 100%;
  min-width: 1180px;
  padding: 0;
}

.device-page :deep(.page-header) {
  margin: 0;
  padding: 0.75rem;
}

.device-page .filters-row {
  margin: 0;
  padding: 0 0.75rem 0.75rem;
}

.device-page .summary-strip {
  margin: 0;
  padding: 0.75rem;
}

.device-type-subbar {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  margin: 0;
  padding: 0 0.75rem 0.75rem;
  overflow-x: auto;
  border-bottom: 1px solid #e2e8f0;
}

.device-type-tab {
  min-height: 38px;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.72rem 0.35rem 0.45rem;
  border: 1px solid #dbe3ef;
  border-radius: 8px;
  background: #fff;
  color: #334155;
  font: inherit;
  font-size: 0.86rem;
  font-weight: 800;
  letter-spacing: 0;
  white-space: nowrap;
  cursor: pointer;
}

.device-type-tab:hover {
  border-color: var(--device-type-border);
  background: var(--device-type-surface);
  color: var(--device-type-text);
}

.device-type-tab.active {
  border-color: var(--device-type-border);
  background: var(--device-type-surface);
  color: var(--device-type-text);
}

.device-type-icon {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 24px;
  border: 1px solid var(--device-type-border);
  border-radius: 6px;
  background: var(--device-type-surface);
  color: var(--device-type-text);
}

.device-type-icon i {
  font-size: 0.95rem;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.duplicate-panel {
  margin: 0 0.75rem 0.75rem;
  border: 1px solid #fed7aa;
  border-radius: 8px;
  background: #fffaf5;
  overflow: hidden;
}

.duplicate-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.75rem 0.85rem;
  border-bottom: 1px solid #fed7aa;
}

.duplicate-panel-header > div {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-width: 0;
}

.duplicate-panel-header span {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  color: #c2410c;
  font-size: 0.75rem;
  font-weight: 900;
}

.duplicate-panel-header strong {
  color: #0f172a;
  font-size: 0.9rem;
  font-weight: 900;
  overflow-wrap: anywhere;
}

.duplicate-total {
  flex: 0 0 auto;
  padding: 0.2rem 0.5rem;
  border-radius: 6px;
  background: #ffedd5;
  color: #9a3412 !important;
  font-size: 0.74rem !important;
}

.duplicate-name-list {
  display: flex;
  gap: 0.45rem;
  padding: 0.65rem 0.75rem;
  overflow-x: auto;
}

.duplicate-name-list button {
  display: inline-flex;
  flex-direction: column;
  gap: 0.12rem;
  min-width: 150px;
  padding: 0.5rem 0.65rem;
  border: 1px solid #fed7aa;
  border-radius: 8px;
  background: #fff;
  color: #334155;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.duplicate-name-list button.active {
  border-color: #fb923c;
  background: #fff7ed;
}

.duplicate-name-list strong {
  color: #0f172a;
  font-size: 0.83rem;
  font-weight: 900;
}

.duplicate-name-list span {
  color: #64748b;
  font-size: 0.72rem;
  font-weight: 800;
}

.duplicate-merge-area {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 0.55rem;
  padding: 0 0.75rem 0.75rem;
}

.duplicate-identity-card {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.6rem;
  min-width: 0;
  padding: 0.6rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
}

.duplicate-identity-card.active {
  border-color: #fb923c;
  background: #fff7ed;
}

.duplicate-identity-card > div {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.14rem;
}

.duplicate-identity-card strong {
  color: #0f172a;
  font-size: 0.82rem;
  font-weight: 900;
}

.duplicate-identity-card span,
.duplicate-identity-card small {
  color: #64748b;
  font-size: 0.72rem;
  font-weight: 750;
  line-height: 1.28;
  overflow-wrap: anywhere;
}

.duplicate-identity-card em {
  color: #c2410c;
  font-size: 0.74rem;
  font-style: normal;
  font-weight: 900;
}

.duplicate-merge-actions {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.65rem;
  padding-top: 0.1rem;
}

.duplicate-merge-actions span {
  color: #64748b;
  font-size: 0.8rem;
  font-weight: 850;
}

.bulk-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.65rem 0.75rem;
  border-top: 1px solid #e2e8f0;
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
}

.bulk-toolbar strong {
  color: #0f172a;
  font-size: 0.9rem;
}

.bulk-toolbar > div {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.device-board {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 0.75rem;
  background: #f4f7fb;
}

.device-list-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 180px;
  border: 1px solid #dbe3ef;
  border-radius: 8px;
  background: #fff;
  color: #64748b;
  font-size: 0.9rem;
  font-weight: 800;
}

.device-owner-card {
  overflow: hidden;
  border: 1px solid #dbe3ef;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.owner-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.85rem 1rem;
  border-bottom: 1px solid #e2e8f0;
  background: #fbfdff;
}

.owner-card-main {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}

.owner-card-meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.6rem;
  flex-wrap: wrap;
}

.owner-card-meta > strong {
  color: #0f172a;
  font-size: 0.9rem;
  font-weight: 900;
}

.device-box-body {
  display: grid;
  grid-template-columns: minmax(620px, 1fr) minmax(340px, 0.52fr);
  gap: 0;
}

.main-computer-section,
.peripheral-section {
  min-width: 0;
  padding: 0.85rem 1rem 1rem;
}

.peripheral-section {
  border-left: 1px solid #e2e8f0;
  background: #f8fafc;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  margin-bottom: 0.6rem;
  color: #475569;
  font-size: 0.78rem;
  font-weight: 900;
}

.section-title i {
  color: #2563eb;
  font-size: 0.82rem;
}

.section-title strong {
  margin-left: auto;
  min-width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: #e2e8f0;
  color: #475569;
  font-size: 0.72rem;
  font-weight: 900;
}

.main-computer-list,
.peripheral-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.main-computer-card {
  display: grid;
  grid-template-columns: auto minmax(180px, 1.1fr) minmax(260px, 1.3fr) minmax(160px, 0.85fr) minmax(150px, 0.75fr) auto;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
  padding: 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
}

.main-computer-card:hover,
.peripheral-item:hover {
  border-color: #bfdbfe;
  background: #f8fbff;
}

.peripheral-item {
  display: grid;
  grid-template-columns: auto auto minmax(120px, 1fr) minmax(90px, 0.85fr) auto auto;
  align-items: center;
  gap: 0.55rem;
  min-width: 0;
  padding: 0.55rem 0.65rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
}

.peripheral-item > strong,
.peripheral-item > span:not(.device-type-chip):not(.status-pill) {
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 0.78rem;
}

.peripheral-item > strong {
  color: #0f172a;
  font-weight: 900;
}

.peripheral-item > span:not(.device-type-chip):not(.status-pill) {
  color: #64748b;
  font-weight: 700;
}

.empty-main-computer,
.empty-peripheral {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 48px;
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  background: #fff;
  color: #94a3b8;
  font-size: 0.78rem;
  font-weight: 800;
}

.scroll-sentinel {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 48px;
  color: #64748b;
  font-size: 0.85rem;
  font-weight: 700;
}

.page-subtitle {
  margin-top: 0.25rem;
  color: #64748b;
  font-size: 0.9rem;
}

.summary-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 0.5rem;
}

.summary-item {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 0.85rem 1rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.summary-item span {
  color: #64748b;
  font-size: 0.85rem;
  font-weight: 600;
}

.summary-item strong {
  color: #0f172a;
  font-size: 1.35rem;
}

.owner-avatar {
  width: 36px;
  height: 36px;
  flex: 0 0 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: #e0f2fe;
  color: #0369a1;
  font-size: 0.95rem;
  font-weight: 900;
}

.owner-copy,
.device-summary-cell,
.network-cell {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.18rem;
}

.owner-copy strong,
.device-summary-cell strong,
.network-cell strong {
  color: #0f172a;
  font-size: 0.9rem;
  font-weight: 900;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.owner-copy span,
.owner-copy small,
.network-cell span {
  color: #64748b;
  font-size: 0.76rem;
  font-weight: 650;
  line-height: 1.28;
  overflow-wrap: anywhere;
}

.owner-device-summary {
  width: fit-content;
  margin: 0.05rem 0;
  padding: 0.16rem 0.45rem;
  border-radius: 6px;
  background: #eff6ff;
  color: #2563eb !important;
  font-size: 0.72rem !important;
  font-weight: 900 !important;
}

.device-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-top: 0.15rem;
}

.device-type-chip,
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  width: fit-content;
  min-height: 24px;
  padding: 0.2rem 0.5rem;
  border-radius: 7px;
  border: 1px solid var(--device-type-border, #dbe3ef);
  background: var(--device-type-surface, #f8fafc);
  color: var(--device-type-text, #475569);
  font-size: 0.74rem;
  font-weight: 850;
  white-space: nowrap;
}

.status-pill {
  border-color: #cbd5e1;
  background: #f8fafc;
  color: #475569;
}

.status-pill.status-assigned {
  border-color: #bbf7d0;
  background: #f0fdf4;
  color: #15803d;
}

.status-pill.status-stock {
  border-color: #fde68a;
  background: #fefce8;
  color: #a16207;
}

.status-pill.status-replaced,
.status-pill.status-retired {
  border-color: #e2e8f0;
  background: #f1f5f9;
  color: #64748b;
}

.spec-list {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.35rem;
}

.spec-list.compact {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.spec-list span {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  min-height: 28px;
  padding: 0.32rem 0.45rem;
  border-radius: 7px;
  background: #f8fafc;
  color: #475569;
  font-size: 0.76rem;
  font-weight: 650;
  white-space: normal;
  overflow-wrap: anywhere;
}

.spec-list b {
  color: #94a3b8;
  font-size: 0.68rem;
  font-weight: 900;
  letter-spacing: 0;
  white-space: nowrap;
}

.network-cell span {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.network-cell i {
  color: #94a3b8;
  font-size: 0.72rem;
}

.network-cell.compact strong {
  font-size: 0.82rem;
}

.network-cell.compact span {
  font-size: 0.74rem;
}

.health-stack {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.health-stack.compact {
  gap: 0.45rem;
}

.health-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.25rem 0.5rem;
  align-items: center;
}

.health-row span {
  color: #64748b;
  font-size: 0.74rem;
  font-weight: 750;
}

.health-row strong {
  color: #0f172a;
  font-size: 0.76rem;
  font-weight: 900;
}

.health-track {
  grid-column: 1 / -1;
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: #e2e8f0;
}

.health-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #60a5fa, #22c55e);
}

.row-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.15rem;
}

.group-header {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.45rem 0.25rem;
  color: #0f172a;
}

.group-header span {
  font-weight: 700;
}

.group-header strong,
.group-footer {
  color: #64748b;
  font-size: 0.82rem;
}

.group-footer {
  padding: 0.85rem 0.25rem 0;
  text-align: right;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.form-grid.three {
  grid-template-columns: repeat(3, 1fr);
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
  font-weight: 600;
  color: #475569;
}

.section-label {
  color: #0f172a;
  font-size: 0.86rem;
  font-weight: 800;
  padding-top: 0.25rem;
}

.bulk-field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.bulk-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #475569;
  font-size: 0.85rem;
  font-weight: 700;
}

.change-target {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.8rem;
  border-radius: 8px;
  background: #f8fafc;
  margin-bottom: 1rem;
}

.change-target span {
  color: #64748b;
  font-size: 0.85rem;
}

@media (max-width: 900px) {
  .summary-strip,
  .form-grid,
  .form-grid.three {
    grid-template-columns: 1fr;
  }
}
</style>
