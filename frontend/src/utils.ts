import { language } from './i18n'
import { businessDateRange } from './utils/businessDates'

function displayLocale(): string {
  return language.value === 'ja' ? 'ja-JP' : language.value === 'en' ? 'en-US' : 'zh-CN'
}

export function formatMoney(value: string | number): string {
  return new Intl.NumberFormat(displayLocale(), {
    style: 'currency',
    currency: 'JPY',
    minimumFractionDigits: 2,
  }).format(Number(value))
}

export function formatDateTime(value: string): string {
  // API 的无时区 DATETIME 按门店日本时间解释，避免浏览器按本机时区偏移。
  const normalized = value.replace(' ', 'T')
  const zonedValue = /(?:Z|[+-]\d{2}:\d{2})$/u.test(normalized)
    ? normalized : `${normalized}+09:00`
  return new Intl.DateTimeFormat(displayLocale(), {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Tokyo',
  }).format(new Date(zonedValue))
}

export function toLocalInput(date: Date): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Tokyo', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(date)
  const part = (type: string) => parts.find((item) => item.type === type)?.value || '00'
  return `${part('year')}-${part('month')}-${part('day')}T${part('hour')}:${part('minute')}`
}

export function createDefaultRange(days = 7) {
  return businessDateRange(days)
}

export function apiDateTime(value: string): string | undefined {
  if (!value) return undefined

  // datetime-local 已经是门店当地时间，直接补齐秒数后提交。
  // 不使用 toISOString()，避免将 09:00 转换成 UTC 的 00:00。
  return value.length === 16 ? `${value}:00` : value
}
