import assert from 'node:assert/strict'
import { test } from 'vitest'
import { isPurchaseDayLocked } from '../src/utils/purchaseOrdering.ts'

test('October 6 closes at noon October 4 in Japan', () => {
  assert.equal(isPurchaseDayLocked('2026-10-06', new Date('2026-10-04T11:59:59+09:00')), false)
  assert.equal(isPurchaseDayLocked('2026-10-06', new Date('2026-10-04T12:00:00+09:00')), true)
  assert.equal(isPurchaseDayLocked('2026-10-06', new Date('2026-10-04T13:00:00+09:00')), true)
  assert.equal(isPurchaseDayLocked('2026-10-07', new Date('2026-10-04T13:00:00+09:00')), false)
})

test('cutoff uses Japan time even with a UTC browser clock and crosses months', () => {
  assert.equal(isPurchaseDayLocked('2026-10-06', new Date('2026-10-04T03:00:00Z')), true)
  assert.equal(isPurchaseDayLocked('2027-01-02', new Date('2026-12-31T12:00:00+09:00')), true)
})
