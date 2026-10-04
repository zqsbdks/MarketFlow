import { expect, test, vi } from 'vitest'
import { loadAllPages } from '../src/utils/pagination'

test('selection options include suppliers beyond the first 100', async () => {
  const fetch = vi.fn(async (page: number) => ({
    page, page_size: 100, total: 205, total_pages: 3,
    items: Array.from({ length: page === 3 ? 5 : 100 }, (_, i) => (page - 1) * 100 + i + 1),
  }))
  const options = await loadAllPages(fetch)
  expect(options).toHaveLength(205)
  expect(options.at(-1)).toBe(205)
  expect(fetch.mock.calls.map(([page]) => page)).toEqual([1, 2, 3])
})

test('failed later pages reject instead of offering incomplete options', async () => {
  const fetch = vi.fn(async (page: number) => {
    if (page === 2) throw new Error('network failure')
    return { page, page_size: 100, total: 101, total_pages: 2, items: [1] }
  })
  await expect(loadAllPages(fetch)).rejects.toThrow('network failure')
})
