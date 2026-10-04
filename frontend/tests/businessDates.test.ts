import { expect, test } from 'vitest'
import { businessDateRange } from '../src/utils/businessDates'

test('60-day range includes exactly 60 Japan dates, including today', () => {
  const range = businessDateRange(60, new Date('2026-10-03T16:00:00Z'))
  expect(range).toEqual({ start: '2026-08-06T09:00', end: '2026-10-04T21:00' })
})

test('Japan date stays correct across year and leap-day boundaries', () => {
  expect(businessDateRange(2, new Date('2026-12-31T16:00:00Z'))).toEqual({
    start: '2026-12-31T09:00', end: '2027-01-01T21:00',
  })
  expect(businessDateRange(2, new Date('2024-02-29T16:00:00Z')).start).toBe('2024-02-29T09:00')
})
