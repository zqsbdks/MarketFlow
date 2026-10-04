import { beforeEach, expect, test } from 'vitest'
import { http } from '../src/api/http'

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem('marketflow_employee', JSON.stringify({ id: 10, store_id: null }))
  localStorage.setItem('marketflow_selected_store_10', '2')
})

async function sentScope(headers: Record<string, string> = {}) {
  const response = await http.get('/reports/overview', {
    headers,
    adapter: async (config) => ({
      data: { scope: config.headers.get('X-Store-ID') }, status: 200, statusText: 'OK', headers: {}, config,
    }),
  })
  return response.data.scope
}

test('headquarters all-store report keeps its explicit scope', async () => {
  expect(await sentScope({ 'X-Store-ID': 'all' })).toBe('all')
})

test('explicit store scope is preserved regardless of header casing', async () => {
  expect(await sentScope({ 'x-store-id': '3' })).toBe('3')
})

test('ordinary queries default to the selected store', async () => {
  expect(await sentScope()).toBe('2')
})

test('invalid local identity is ignored', async () => {
  localStorage.setItem('marketflow_employee', '{invalid')
  expect(await sentScope()).toBeUndefined()
})
