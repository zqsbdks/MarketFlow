export function formatMoney(value: string | number): string {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 2,
  }).format(Number(value))
}

export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

export function toLocalInput(date: Date): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

export function createDefaultRange(days = 7) {
  const end = new Date()
  end.setHours(21, 0, 0, 0)
  const start = new Date(end)
  start.setDate(start.getDate() - days + 1)
  start.setHours(9, 0, 0, 0)
  return { start: toLocalInput(start), end: toLocalInput(end) }
}

export function apiDateTime(value: string): string | undefined {
  if (!value) return undefined

  // datetime-local 已经是门店当地时间，直接补齐秒数后提交。
  // 不使用 toISOString()，避免将 09:00 转换成 UTC 的 00:00。
  return value.length === 16 ? `${value}:00` : value
}
