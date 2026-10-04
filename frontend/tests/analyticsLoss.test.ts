import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, test, vi } from 'vitest'
import AnalyticsView from '../src/views/AnalyticsView.vue'
const api = vi.hoisted(() => ({ getDepartments: vi.fn().mockResolvedValue([]), getReportAnalytics: vi.fn() }))
vi.mock('../src/api', () => api)
vi.mock('../src/stores/auth', () => ({ useAuthStore: () => ({ isHeadquarters: true }) }))
vi.mock('echarts/core', () => ({ use: vi.fn(), init: () => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() }) }))
beforeEach(() => {
  const data: Record<string, unknown> = { revenue: '100.00', loss_cost: '12.00', loss_revenue_ratio: '12.00', discard_quantity: 3, discard_count: 1 }
  api.getReportAnalytics.mockReset().mockImplementation(async (params: { metrics: string[] }) => Object.fromEntries(params.metrics.filter(key => key in data).map(key => [key, data[key]])))
})
test('loss metrics are checkbox options on the same analytics request', async () => {
  const wrapper = mount(AnalyticsView); await flushPromises()
  expect(wrapper.find('[role=tablist]').exists()).toBe(false)
  for (const label of ['损耗金额', '损耗占营业额比例', '废弃数量', '废弃记录数']) {
    expect(wrapper.findAll('label').some(e => e.text() === label)).toBe(true)
  }
  const company = wrapper.findAll('input[type=checkbox]').find(e => e.element.parentElement?.textContent?.includes('全公司汇总'))!
  await company.setValue(true)
  await wrapper.findAll('button').find(e => e.text() === '生成分析')!.trigger('click'); await flushPromises()
  expect(api.getReportAnalytics).toHaveBeenCalledTimes(1)
  expect(api.getReportAnalytics.mock.calls[0]![1]).toBe(true)
  expect(api.getReportAnalytics.mock.calls[0]![0].metrics).toEqual(expect.arrayContaining(['loss_cost', 'loss_revenue_ratio', 'discard_quantity', 'discard_count']))
  expect(wrapper.text()).toContain('12.00%')
  wrapper.unmount()
})
test('only checked loss metrics are sent and shown', async () => {
  const wrapper = mount(AnalyticsView); await flushPromises()
  await wrapper.findAll('button').find(e => e.text() === '反选')!.trigger('click')
  const cost = wrapper.findAll('label').find(e => e.text() === '损耗金额')!
  await cost.get('input').setValue(true)
  await wrapper.findAll('button').find(e => e.text() === '生成分析')!.trigger('click'); await flushPromises()
  expect(api.getReportAnalytics.mock.calls[0]![0].metrics).toEqual(['loss_cost'])
  expect(wrapper.get('.metric-results').text()).toContain('损耗金额')
  expect(wrapper.get('.metric-results').text()).not.toContain('营业额')
  expect(wrapper.find('.loss-groups').exists()).toBe(false)
  wrapper.unmount()
})
test('failed refreshed analytics clear old results', async () => {
  const wrapper = mount(AnalyticsView); await flushPromises()
  const generate = wrapper.findAll('button').find(e => e.text() === '生成分析')!
  await generate.trigger('click'); await flushPromises()
  expect(wrapper.find('.metric-results').exists()).toBe(true)
  api.getReportAnalytics.mockRejectedValueOnce(new Error('network'))
  await generate.trigger('click'); await flushPromises()
  expect(wrapper.find('.metric-results').exists()).toBe(false)
  wrapper.unmount()
})
