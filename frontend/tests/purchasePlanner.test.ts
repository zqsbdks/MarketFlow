import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import PurchasePlanner from '../src/components/PurchasePlanner.vue'

const api = vi.hoisted(() => ({ getPurchasePlanning: vi.fn(), savePurchasePlan: vi.fn(), saveMinimumStock: vi.fn() }))
vi.mock('../src/api', () => api)

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
  vi.setSystemTime(new Date('2026-10-04T10:00:00+09:00'))
  api.getPurchasePlanning.mockReset().mockResolvedValue({ previous_arrival_date: '2026-10-07', days: ['2026-10-08'], items: [{
    previous_expected_quantity: 25, previous_received_quantity: 0,
    minimum_stock: 0,
    supplier_product_id: 1, name: 'Banana', supplier_name: 'Supplier', unit_cost: '5',
    saleable_stock: 30, near_expiry_stock_quantity: 0,
    days: [{ date: '2026-10-08', planned_quantity: 15, suggested_quantity: 12, is_manual: true, forecast_sales: 12, expected_quantity: 0, received_quantity: 0, last_week_sales: 20 }],
  }] })
  api.savePurchasePlan.mockReset().mockResolvedValue({ quantity: 25 })
  api.saveMinimumStock.mockReset().mockResolvedValue({ minimum_stock: 10 })
})
afterEach(() => vi.useRealTimers())
const open = () => mount(PurchasePlanner, { props: { departments: [{ id: 1, name: 'Produce', code: 'D1', is_active: true }], ownDepartmentId: 1, isManager: true } })

test('loads saved plans and saves replacement quantities without creating orders', async () => {
  const wrapper = open(); await flushPromises()
  expect(wrapper.findAll('button').some(button => button.text() === '提交进货单')).toBe(false)
  const input = wrapper.get('input[type=number]')
  expect(wrapper.get('.arrival-reference').text()).toContain('10-07')
  expect(wrapper.get('td.arrival-reference').text()).toContain('25 件')
  expect(wrapper.get('td.arrival-reference').find('input').exists()).toBe(false)
  expect((input.element as HTMLInputElement).value).toBe('15')
  await input.setValue('25'); await flushPromises()
  expect(api.savePurchasePlan).toHaveBeenLastCalledWith({ department_id: 1, arrival_date: '2026-10-08', supplier_product_id: 1, quantity: 25 })
  expect(wrapper.text()).toContain('订货计划已保存')
  await input.setValue('0'); await flushPromises()
  expect(api.savePurchasePlan.mock.calls.at(-1)![0].quantity).toBe(0)
  wrapper.unmount()
})

test('failed saves show failure and restore the last confirmed quantity', async () => {
  api.savePurchasePlan.mockRejectedValueOnce(new Error('Offline'))
  const wrapper = open(); await flushPromises()
  await wrapper.get('input[type=number]').setValue('25'); await flushPromises()
  expect(wrapper.text()).toContain('保存失败，请重新填写')
  expect((wrapper.get('input[type=number]').element as HTMLInputElement).value).toBe('15')
  wrapper.unmount()
})

test('closed dates cannot be edited', async () => {
  vi.setSystemTime(new Date('2026-10-06T12:00:00+09:00'))
  const wrapper = open(); await flushPromises()
  expect((wrapper.get('input[type=number]').element as HTMLInputElement).disabled).toBe(true)
  expect(api.savePurchasePlan).not.toHaveBeenCalled()
  wrapper.unmount()
})

test('floor stock saves and manual override can return to automatic calculation', async () => {
  const wrapper = open(); await flushPromises()
  await wrapper.get('.minimum-stock-cell input').setValue('10'); await flushPromises()
  expect(api.saveMinimumStock).toHaveBeenCalledWith({ department_id: 1, supplier_product_id: 1, minimum_stock: 10 })
  await wrapper.get('.restore-auto').trigger('click'); await flushPromises()
  expect(api.savePurchasePlan.mock.calls.at(-1)![0].quantity).toBe(null)
  wrapper.unmount()
})
