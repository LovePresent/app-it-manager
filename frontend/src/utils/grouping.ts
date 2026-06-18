export interface GroupOption {
  label: string
  value: string
  type?: 'text' | 'boolean' | 'deviceType' | 'status'
}

type LabelResolver = (value: string) => string

interface GroupFormatters {
  deviceType?: LabelResolver
  status?: LabelResolver
}

export function formatGroupValue(value: unknown, option: GroupOption, formatters: GroupFormatters = {}) {
  if (option.type === 'boolean') return value ? '적용' : '미적용'
  if (value === null || value === undefined || value === '') return '미지정'

  const text = String(value)
  if (option.type === 'deviceType') return formatters.deviceType?.(text) ?? text
  if (option.type === 'status') return formatters.status?.(text) ?? text
  return text
}

export function groupValue(item: Record<string, unknown>, option: GroupOption | null, formatters: GroupFormatters = {}) {
  if (!option) return ''
  return formatGroupValue(item[option.value], option, formatters)
}

export function sortByGroup<T extends Record<string, unknown>>(
  items: T[],
  option: GroupOption | null,
  formatters: GroupFormatters = {},
) {
  if (!option) return items
  return [...items].sort((a, b) => {
    const groupCompare = groupValue(a, option, formatters).localeCompare(groupValue(b, option, formatters), 'ko-KR')
    if (groupCompare !== 0) return groupCompare
    return String(a.user_name ?? '').localeCompare(String(b.user_name ?? ''), 'ko-KR')
  })
}

export function countGroup<T extends Record<string, unknown>>(
  items: T[],
  item: T,
  option: GroupOption | null,
  formatters: GroupFormatters = {},
) {
  if (!option) return 0
  const target = groupValue(item, option, formatters)
  return items.filter((entry) => groupValue(entry, option, formatters) === target).length
}
