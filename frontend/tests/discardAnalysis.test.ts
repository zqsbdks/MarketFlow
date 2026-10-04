import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, test, vi } from 'vitest'
import DiscardAnalysis from '../src/components/DiscardAnalysis.vue'

const request = vi.hoisted(() => ({ get: vi.fn() }))
const identity = vi.hoisted(() => ({ isHeadquarters: true }))
vi.mock('../src/api/http', () => ({ http: request, unwrap: (value: { data: unknown }) => value.data, getErrorMessage: () => '请求失败' }))
vi.mock('../src/api', () => ({ getDepartments: async () => [] }))
vi.mock('../src/stores/auth', () => ({ useAuthStore: () => identity }))
beforeEach(() => {
  identity.isHeadquarters = true
  request.get.mockReset().mockResolvedValue({ data: { data: { record_count: 1, quantity: 3, cost: '12.00', reasons: [{ key: 'expired', name: '过期', quantity: 3, cost: '12.00', cost_share: '100.00' }], departments: [], stores: [] } } })
})
test('headquarters requests all stores explicitly and failed queries clear old results', async () => {
  const wrapper = mount(DiscardAnalysis)
  await flushPromises()
  expect(wrapper.text()).toContain('100.00%')
  await wrapper.get('input[type=checkbox]').setValue(true)
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(request.get).toHaveBeenLastCalledWith('/reports/discard-analysis', expect.objectContaining({ headers: { 'X-Store-ID': 'all' } }))
  request.get.mockRejectedValueOnce(new Error('offline'))
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('请求失败')
  expect(wrapper.find('.loss-summary').exists()).toBe(false)
  wrapper.unmount()
})
test('store employees cannot select company scope or see store comparisons', async () => {
  identity.isHeadquarters = false
  const wrapper = mount(DiscardAnalysis); await flushPromises()
  expect(wrapper.find('input[type=checkbox]').exists()).toBe(false)
  expect(wrapper.text()).not.toContain('门店损耗对比')
  expect(request.get.mock.calls[0]![1].headers).toBeUndefined()
  wrapper.unmount()
})
