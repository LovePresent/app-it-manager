<template><Tag :value="label" :severity="severity" :title="hint" /></template>
<script setup lang="ts">
import { computed } from 'vue'
import Tag from 'primevue/tag'
import type { DeviceAgent } from '@/types/deviceAgent'
import { formatAgentDate } from './deviceAgentState'
const props = withDefaults(defineProps<{ agent?: DeviceAgent | null; stale?: boolean; loaded?: boolean }>(), { loaded: true, stale: false })
const label = computed(() => props.stale ? '상태 확인 불가' : !props.loaded ? '연결 확인 중' : !props.agent ? '에이전트 미등록' : ({ online: '켜져 있음', offline: '연결 끊김', pending: '설치 / 연결 대기', revoked: '연결 해제', uninstalled: '프로그램 삭제됨', worker_missing: '프로그램 파일 없음', worker_stopped: '프로세스 중지' }[props.agent.status] || '상태 미확인'))
const severity = computed<'success' | 'warn' | 'secondary' | 'danger'>(() => props.stale || !props.loaded ? 'secondary' : props.agent?.status === 'online' ? 'success' : props.agent && ['uninstalled', 'worker_missing', 'worker_stopped'].includes(props.agent.status) ? 'danger' : props.agent?.status === 'pending' ? 'warn' : 'secondary')
const hint = computed(() => {
  if (props.stale) return '서버 연결을 확인할 수 없어 현재 상태를 판단할 수 없습니다.'
  const status = props.agent?.status
  if (status === 'uninstalled') return `프로그램 제거 완료를 확인했습니다. ${formatAgentDate(props.agent?.uninstalled_at)}`
  if (status === 'worker_missing') return '실행 중인 서비스가 작업 프로그램 파일이 없음을 확인했습니다.'
  if (status === 'worker_stopped') return '실행 중인 서비스가 작업 프로세스 중지를 확인했습니다.'
  if (status === 'offline') return `마지막 연결: ${formatAgentDate(props.agent?.last_seen_at)} · 연결 끊김만으로 전원 종료나 프로그램 삭제를 판단하지 않습니다.`
  return props.agent?.last_seen_at ? `마지막 연결: ${formatAgentDate(props.agent.last_seen_at)} (한국 표준시)` : '에이전트 연결 신호로 PC 상태를 확인합니다.'
})
</script>
