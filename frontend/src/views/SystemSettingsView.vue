<template>
  <div>
    <div class="page-header">
      <div>
        <h1>시스템 설정</h1>
        <p class="page-subtitle">DB 백업 파일을 생성하고, 검증된 백업 파일로 복원합니다.</p>
      </div>
      <Button label="새로고침" icon="pi pi-refresh" severity="secondary" :loading="infoLoading || backupsLoading" @click="refreshAll" />
    </div>

    <div class="settings-grid">
      <section class="card settings-panel">
        <div class="section-heading">
          <div>
            <h2>DB 상태</h2>
            <span>현재 연결된 데이터베이스</span>
          </div>
          <Tag v-if="databaseInfo" :value="databaseInfo.supported ? 'SQLite' : databaseInfo.dialect" :severity="databaseInfo.supported ? 'success' : 'warn'" />
        </div>

        <div v-if="databaseInfo" class="info-grid">
          <div class="info-item">
            <span>DB 파일</span>
            <strong>{{ databaseInfo.database_path || '-' }}</strong>
          </div>
          <div class="info-item">
            <span>파일 크기</span>
            <strong>{{ databaseInfo.database_size_label }}</strong>
          </div>
          <div class="info-item">
            <span>수정일</span>
            <strong>{{ formatDate(databaseInfo.modified_at) }}</strong>
          </div>
          <div class="info-item">
            <span>백업 폴더</span>
            <strong>{{ databaseInfo.backup_directory }}</strong>
          </div>
        </div>

        <div v-if="databaseInfo && !databaseInfo.supported" class="alert-box">
          앱 내 백업/복원은 파일 기반 SQLite DB에서만 사용할 수 있습니다.
        </div>

        <div class="action-row">
          <Button label="백업 생성" icon="pi pi-save" :loading="backupCreating" :disabled="!canUseDatabaseActions" @click="createBackup" />
          <Button label="현재 DB 다운로드" icon="pi pi-download" severity="secondary" :loading="downloadLoading" :disabled="!canUseDatabaseActions" @click="downloadCurrentDatabase" />
        </div>
      </section>

      <section class="card settings-panel">
        <div class="section-heading">
          <div>
            <h2>DB 복원</h2>
            <span>SQLite 백업 파일 업로드</span>
          </div>
          <Tag value="관리자" severity="danger" />
        </div>

        <input ref="fileInput" class="hidden-file" type="file" accept=".db,.sqlite,.sqlite3" @change="onRestoreFileChange" />
        <div class="restore-box">
          <div class="selected-file">
            <i class="pi pi-database" />
            <span>{{ selectedRestoreFile?.name || '선택된 파일 없음' }}</span>
          </div>
          <Button label="파일 선택" icon="pi pi-folder-open" severity="secondary" :disabled="!canUseDatabaseActions" @click="selectRestoreFile" />
        </div>

        <div class="restore-note">
          복원 전 현재 DB 백업이 자동으로 생성됩니다. 복원 후 페이지를 새로고침해 최신 데이터를 확인하세요.
        </div>

        <div class="action-row">
          <Button label="복원 실행" icon="pi pi-upload" severity="danger" :loading="restoreLoading" :disabled="!canRestore" @click="restoreDatabase" />
        </div>
      </section>
    </div>

    <section class="card backup-list-card">
      <div class="section-heading">
        <div>
          <h2>백업 파일</h2>
          <span>{{ backups.length }}개 파일</span>
        </div>
      </div>

      <DataTable :value="backups" :loading="backupsLoading" stripedRows size="small" emptyMessage="백업 파일이 없습니다.">
        <Column field="filename" header="파일명" style="min-width:260px" />
        <Column field="size_label" header="크기" style="width:120px" />
        <Column header="생성일" style="width:180px">
          <template #body="{ data }">{{ formatDate(data.created_at) }}</template>
        </Column>
        <Column style="width:90px">
          <template #body="{ data }">
            <Button icon="pi pi-download" text rounded size="small" @click="downloadBackup(data)" />
          </template>
        </Column>
      </DataTable>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import api from '@/api'

interface DatabaseInfo {
  supported: boolean
  dialect: string
  database_path: string | null
  database_size_bytes: number | null
  database_size_label: string
  modified_at: string | null
  backup_directory: string
  backup_count: number
}

interface BackupRecord {
  filename: string
  size_bytes: number
  size_label: string
  created_at: string
}

const toast = useToast()
const databaseInfo = ref<DatabaseInfo | null>(null)
const backups = ref<BackupRecord[]>([])
const selectedRestoreFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const infoLoading = ref(false)
const backupsLoading = ref(false)
const backupCreating = ref(false)
const downloadLoading = ref(false)
const restoreLoading = ref(false)

const canUseDatabaseActions = computed(() => Boolean(databaseInfo.value?.supported))
const canRestore = computed(() => canUseDatabaseActions.value && Boolean(selectedRestoreFile.value) && !restoreLoading.value)

function formatDate(value: string | null) {
  if (!value) return '-'
  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function downloadBlob(data: BlobPart, contentDisposition: string | undefined, fallbackFilename: string) {
  const match = contentDisposition?.match(/filename="?([^"]+)"?/)
  const filename = match?.[1] || fallbackFilename
  const url = window.URL.createObjectURL(new Blob([data]))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

async function loadDatabaseInfo() {
  infoLoading.value = true
  try {
    const { data } = await api.get<DatabaseInfo>('/system/database')
    databaseInfo.value = data
  } catch (err: any) {
    toast.add({ severity: 'error', summary: '오류', detail: err.response?.data?.detail ?? 'DB 상태 조회 실패', life: 5000 })
  } finally {
    infoLoading.value = false
  }
}

async function loadBackups() {
  backupsLoading.value = true
  try {
    const { data } = await api.get<{ items: BackupRecord[] }>('/system/database/backups')
    backups.value = data.items
  } catch (err: any) {
    toast.add({ severity: 'error', summary: '오류', detail: err.response?.data?.detail ?? '백업 목록 조회 실패', life: 5000 })
  } finally {
    backupsLoading.value = false
  }
}

async function refreshAll() {
  await Promise.all([loadDatabaseInfo(), loadBackups()])
}

async function createBackup() {
  backupCreating.value = true
  try {
    await api.post('/system/database/backups')
    toast.add({ severity: 'success', summary: '백업 생성 완료', life: 3000 })
    await refreshAll()
  } catch (err: any) {
    toast.add({ severity: 'error', summary: '오류', detail: err.response?.data?.detail ?? '백업 생성 실패', life: 5000 })
  } finally {
    backupCreating.value = false
  }
}

async function downloadCurrentDatabase() {
  downloadLoading.value = true
  try {
    const response = await api.get('/system/database/download', { responseType: 'blob' })
    downloadBlob(response.data, response.headers['content-disposition'], 'itam_backup.db')
    await loadBackups()
  } catch (err: any) {
    toast.add({ severity: 'error', summary: '오류', detail: err.response?.data?.detail ?? 'DB 다운로드 실패', life: 5000 })
  } finally {
    downloadLoading.value = false
  }
}

async function downloadBackup(backup: BackupRecord) {
  try {
    const filename = encodeURIComponent(backup.filename)
    const response = await api.get(`/system/database/backups/${filename}/download`, { responseType: 'blob' })
    downloadBlob(response.data, response.headers['content-disposition'], backup.filename)
  } catch (err: any) {
    toast.add({ severity: 'error', summary: '오류', detail: err.response?.data?.detail ?? '백업 다운로드 실패', life: 5000 })
  }
}

function selectRestoreFile() {
  fileInput.value?.click()
}

function onRestoreFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  selectedRestoreFile.value = input.files?.[0] ?? null
}

async function restoreDatabase() {
  if (!selectedRestoreFile.value) return
  const confirmed = window.confirm('현재 DB를 업로드한 파일로 교체합니다. 계속 진행할까요?')
  if (!confirmed) return

  restoreLoading.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedRestoreFile.value)
    formData.append('create_backup_before_restore', 'true')
    await api.post('/system/database/restore', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    toast.add({ severity: 'success', summary: '복원 완료', life: 3000 })
    selectedRestoreFile.value = null
    if (fileInput.value) fileInput.value.value = ''
    await refreshAll()
  } catch (err: any) {
    toast.add({ severity: 'error', summary: '오류', detail: err.response?.data?.detail ?? 'DB 복원 실패', life: 5000 })
  } finally {
    restoreLoading.value = false
  }
}

onMounted(refreshAll)
</script>

<style scoped>
.settings-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem;margin-bottom:1rem}
.settings-panel{display:flex;flex-direction:column;gap:1rem}
.section-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;margin-bottom:0.25rem}
.section-heading h2{font-size:1.05rem;font-weight:800;color:#0f172a;line-height:1.3}
.section-heading span{display:block;margin-top:0.15rem;color:#64748b;font-size:0.84rem}
.info-grid{display:grid;grid-template-columns:1fr 1fr;gap:0.75rem}
.info-item{min-width:0;border:1px solid #e2e8f0;border-radius:8px;padding:0.8rem;background:#f8fafc}
.info-item span{display:block;color:#64748b;font-size:0.78rem;font-weight:700;margin-bottom:0.25rem}
.info-item strong{display:block;color:#0f172a;font-size:0.88rem;font-weight:800;line-height:1.35;overflow-wrap:anywhere}
.action-row{display:flex;gap:0.5rem;flex-wrap:wrap;margin-top:auto}
.alert-box{border:1px solid #fde68a;background:#fffbeb;color:#92400e;border-radius:8px;padding:0.8rem;font-size:0.86rem;font-weight:700}
.hidden-file{display:none}
.restore-box{display:flex;gap:0.75rem;align-items:center}
.selected-file{min-width:0;flex:1;display:flex;align-items:center;gap:0.6rem;border:1px solid #dbe3ef;border-radius:8px;padding:0.75rem;background:#f8fafc;color:#334155;font-weight:700}
.selected-file i{color:#2563eb}
.selected-file span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.restore-note{border-left:3px solid #ef4444;background:#fef2f2;color:#991b1b;padding:0.75rem 0.85rem;font-size:0.84rem;font-weight:700;line-height:1.45}
.backup-list-card{margin-top:1rem}
@media (max-width:900px){.settings-grid,.info-grid{grid-template-columns:1fr}.restore-box{align-items:stretch;flex-direction:column}}
</style>
