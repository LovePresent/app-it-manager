<template><Tag v-if="monitor" :value="label" :severity="severity" :title="hint" /></template>
<script setup lang="ts">
import { computed } from 'vue'
import Tag from 'primevue/tag'
import type { AgentNetworkMonitor } from '@/types/deviceAgent'
const props = defineProps<{ monitor?: AgentNetworkMonitor | null; stale?: boolean }>()
const unresolved = computed(() => props.monitor?.review && props.monitor.review.state !== 'resolved')
const label = computed(() => {
  if (props.monitor?.reference_error) return '기준 IP 확인 필요'
  if (props.monitor?.reference_pending) return '변경된 기준 확인 대기'
  if (props.stale || props.monitor?.stale) return unresolved.value ? 'IP 점검 미완료 · 현재 미확인' : 'IP 현재 미확인'
  if (props.monitor?.status === 'mismatch') return 'IP 불일치 · 점검 필요'
  if (unresolved.value) return props.monitor?.review?.state === 'reviewing' ? 'IP 점검 중' : 'IP 점검 확인 필요'
  return props.monitor?.status === 'normal' ? '기준 IP 일치' : 'IP 확인 대기'
})
const severity = computed<'success' | 'warn' | 'secondary' | 'danger'>(() => props.monitor?.reference_error ? 'warn' : !props.stale && !props.monitor?.stale && props.monitor?.status === 'mismatch' ? 'danger' : unresolved.value || props.monitor?.reference_pending ? 'warn' : props.stale || props.monitor?.stale || props.monitor?.status !== 'normal' ? 'secondary' : 'success')
const hint = computed(() => `기준: ${props.monitor?.expected_ipv4.join(', ') || '미설정'} / 최근 확인: ${props.monitor?.observed_ipv4.join(', ') || '없음'}. 기준 IP와 실제 관측값을 비교하며, 변경 시도나 작업자를 단정하지 않습니다.`)
</script>
