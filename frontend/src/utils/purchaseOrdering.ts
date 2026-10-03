/** Each arrival day closes two days earlier at noon in Japan. */
export function isPurchaseDayLocked(arrivalDate: string, now: Date): boolean {
  const cutoff = Date.parse(`${arrivalDate}T12:00:00+09:00`) - 2 * 24 * 60 * 60 * 1000
  return now.getTime() >= cutoff
}
