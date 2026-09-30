/**
 * 把系统里的枚举值翻译成用户看得懂的说法。
 * 界面不应该出现 planning / in_progress 这类内部字段值。
 */

export const TRIP_STATUS_LABELS: Record<string, string> = {
  planning: '规划中',
  confirmed: '已确认',
  in_progress: '进行中',
  completed: '已完成',
  cancelled: '已取消',
}

export function tripStatusLabel(status?: string | null): string {
  if (!status) return '未设置'
  return TRIP_STATUS_LABELS[status] || status
}

/** 状态对应的图示色：只有「进行中」用航线品红，其余保持墨色层级 */
export function tripStatusTone(status?: string | null): 'live' | 'done' | 'idle' {
  if (status === 'in_progress') return 'live'
  if (status === 'completed' || status === 'cancelled') return 'done'
  return 'idle'
}

export const TRAVEL_STYLE_LABELS: Record<string, string> = {
  relaxed: '休闲度假',
  adventurous: '探险挑战',
  cultural: '文化探索',
  family: '亲子游',
  romantic: '蜜月 / 情侣',
  business: '商务旅行',
  foodie: '美食之旅',
  photography: '摄影采风',
}

export function travelStyleLabel(style?: string | null): string {
  if (!style) return '未设置'
  return TRAVEL_STYLE_LABELS[style] || style
}

export const RISK_LEVEL_LABELS: Record<string, string> = {
  conservative: '保守',
  moderate: '稳健',
  aggressive: '积极',
}

export function riskLevelLabel(level?: string | null): string {
  if (!level) return '稳健'
  return RISK_LEVEL_LABELS[level] || level
}

/** 中文日期：4月2日 周三 */
export function formatDateCN(dateStr?: string | null): string {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  if (Number.isNaN(d.getTime())) return dateStr
  const md = d.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })
  const weekday = d.toLocaleDateString('zh-CN', { weekday: 'short' })
  return `${md} ${weekday}`
}

/** 出行区间：2025年4月2日 – 4月6日（跨年时补上年份） */
export function formatDateRange(
  start?: string | null,
  end?: string | null,
): string {
  if (!start || !end) return '—'
  const a = new Date(start)
  const b = new Date(end)
  if (Number.isNaN(a.getTime()) || Number.isNaN(b.getTime())) return `${start} – ${end}`
  const aText = a.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
  const sameYear = a.getFullYear() === b.getFullYear()
  const bText = b.toLocaleDateString('zh-CN', {
    ...(sameYear ? {} : { year: 'numeric' }),
    month: 'long',
    day: 'numeric',
  })
  return `${aText} – ${bText}`
}

/** 只取月日：4月2日 */
export function formatMonthDay(dateStr?: string | null): string {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  if (Number.isNaN(d.getTime())) return dateStr
  return d.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })
}

/** 行程天数（含首尾） */
export function tripDays(start?: string | null, end?: string | null): number | null {
  if (!start || !end) return null
  const a = new Date(start)
  const b = new Date(end)
  if (Number.isNaN(a.getTime()) || Number.isNaN(b.getTime())) return null
  return Math.round((b.getTime() - a.getTime()) / 86400000) + 1
}
