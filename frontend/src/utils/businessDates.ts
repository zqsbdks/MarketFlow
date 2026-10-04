/** Inclusive business-day range, independent of the browser timezone. */
export function businessDateRange(days: number, now = new Date()) {
  if (!Number.isInteger(days) || days < 1) throw new RangeError('days must be positive')
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Tokyo', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(now)
  const part = (type: string) => parts.find((item) => item.type === type)!.value
  const end = `${part('year')}-${part('month')}-${part('day')}`
  const start = new Date(`${end}T00:00:00Z`)
  start.setUTCDate(start.getUTCDate() - days + 1)
  return { start: `${start.toISOString().slice(0, 10)}T09:00`, end: `${end}T21:00` }
}
