const actionLabels: Record<string, string> = {
  create: '등록', update: '수정', delete: '삭제', assign: '할당', return: '반납',
  enroll: '에이전트 등록', auto_enroll: 'PC 자동 등록', issue_installer: '설치 파일 발급',
  installer: '설치 파일 발급', revoke: '에이전트 연결 해제', heartbeat_state_change: '수집 정보 / 연결 변화',
  ip_baseline_recorded: '최초 IP 기준 기록', ip_mismatch_detected: 'IP 불일치 감지',
  ip_restored: '기존 기준 IP 복구 확인', ip_monitoring_reference_changed: 'IP 비교 기준 변경',
  ip_reference_resolved: '변경된 기준 IP 일치', ip_review_started: 'IP 점검 기록', ip_review_resolved: 'IP 점검 처리 완료',
  service_state_change: '프로그램 실행 상태 변화', uninstall_complete: '프로그램 제거 완료',
  uninstall_authorize: '프로그램 제거 승인', uninstall_code: '제거 승인 코드 발급',
  request: '전원 요청', acknowledge: '전원 요청 결과', configure_wol: 'WOL 설정 변경',
  enrollment_ticket_issued: '자동 등록 설치 파일 발급',
  installer_issue: '설치 파일 발급', uninstall_code_issue: '제거 승인 코드 발급',
  wol_update: 'WOL 설정 변경', delivered: '전원 요청 전달',
}
export function logActionLabel(action: string): string { return actionLabels[action] || action }
export const deviceLogActions = Object.entries(actionLabels).map(([value, label]) => ({ value, label }))
