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
const open = () => mount(PurchasePlanner, { props: { departments: [{ id: 1, name: 'Produce', code: 'D1', is_active: true }], ownDepartmentId: 1, isManager: true }, global: { stubs: { teleport: true } } })

test('loads saved plans and saves replacement quantities without creating orders', async () => {
  const wrapper = open(); await flushPromises()
  expect(wrapper.findAll('button').some(button => button.text() === '提交进货单')).toBe(false)
  const input = wrapper.get('input[type=number]')
  expect(wrapper.get('.arrival-reference').text()).toContain('10-07')
  expect(wrapper.get('td.arrival-reference').text()).toContain('25 件')
  expect(wrapper.get('td.arrival-reference').find('input').exists()).toBe(false)
  expect((input.element as HTMLInputElement).value).toBe('15')
  await input.setValue('25'); await input.trigger('blur'); await flushPromises()
  expect(api.savePurchasePlan).toHaveBeenLastCalledWith({ department_id: 1, arrival_date: '2026-10-08', supplier_product_id: 1, quantity: 25 })
  expect(wrapper.text()).toContain('订货计划已保存')
  await input.setValue('0'); await input.trigger('blur'); await flushPromises()
  expect(api.savePurchasePlan.mock.calls.at(-1)![0].quantity).toBe(0)
  wrapper.unmount()
})

test('failed saves show failure and restore the last confirmed quantity', async () => {
  api.savePurchasePlan.mockRejectedValueOnce(new Error('Offline'))
  const wrapper = open(); await flushPromises()
  await wrapper.get('input[type=number]').setValue('25'); await wrapper.get('input[type=number]').trigger('blur'); await flushPromises()
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
  await wrapper.get('.minimum-stock-cell input').setValue('10'); await wrapper.get('.minimum-stock-cell input').trigger('blur'); await flushPromises()
  expect(api.saveMinimumStock).toHaveBeenCalledWith({ department_id: 1, supplier_product_id: 1, minimum_stock: 10 })
  await wrapper.get('.restore-auto').trigger('click'); await flushPromises()
  expect(api.savePurchasePlan.mock.calls.at(-1)![0].quantity).toBe(null)
  wrapper.unmount()
})

const challenge = { confirmation_required: true, confirmation_token: 'signed-token', quantity: 500, reference: 20, previous: 15, reasons: ['far_above_reference', 'possible_extra_zero'] }

test('stepping continues across repeated digits and saves only when leaving the field', async () => {
  const wrapper = open(); await flushPromises()
  const input = wrapper.get('input[type=number]')
  for (const value of ['21', '22', '23']) {
    await input.trigger('keydown', { key: 'ArrowUp' })
    ;(input.element as HTMLInputElement).value = value
    await input.trigger('input'); await input.trigger('change'); await flushPromises()
  }
  expect(api.savePurchasePlan).not.toHaveBeenCalled()
  await input.trigger('blur'); await flushPromises()
  expect(api.savePurchasePlan.mock.calls.at(-1)![0]).toMatchObject({ quantity: 23, input_method: 'stepper' })
  wrapper.unmount()
})

test('keyboard drafts survive clock redraws including zero and clearing the field', async () => {
  const wrapper = open(); await flushPromises()
  const input = wrapper.get('input[type=number]')
  for (const value of ['5', '50', '500', '', '0']) {
    ;(input.element as HTMLInputElement).value = value
    await input.trigger('input')
    await vi.advanceTimersByTimeAsync(1100)
    expect((input.element as HTMLInputElement).value).toBe(value)
  }
  expect(api.savePurchasePlan).not.toHaveBeenCalled()
  wrapper.unmount()
})

test('minimum stock draft survives another cell save and its planning reload', async () => {
  const wrapper = open(); await flushPromises()
  const minimum = wrapper.get('.minimum-stock-cell input')
  ;(minimum.element as HTMLInputElement).value = '123'
  await minimum.trigger('input')
  await vi.advanceTimersByTimeAsync(1100)
  await wrapper.get('input[type=number]').setValue('25'); await wrapper.get('input[type=number]').trigger('blur'); await flushPromises()
  expect(api.getPurchasePlanning).toHaveBeenCalledTimes(2)
  expect((wrapper.get('.minimum-stock-cell input').element as HTMLInputElement).value).toBe('123')
  expect(api.saveMinimumStock).not.toHaveBeenCalled()
  wrapper.unmount()
})

test('typing does not save and an unusual quantity waits for explicit confirmation', async () => {
  api.savePurchasePlan.mockResolvedValueOnce(challenge)
  const wrapper = open(); await flushPromises()
  const input = wrapper.get('input[type=number]')
  ;(input.element as HTMLInputElement).value = '500'
  await input.trigger('input'); await flushPromises()
  expect(api.savePurchasePlan).not.toHaveBeenCalled()
  await input.trigger('blur'); await flushPromises()
  expect(api.savePurchasePlan).toHaveBeenCalledTimes(1)
  expect(wrapper.get('.quantity-confirmation').text()).toContain('500')
  expect(wrapper.text()).toContain('数量明显超过正常需求')
  await wrapper.get('.confirmation-actions button:last-child').trigger('click'); await flushPromises()
  expect(api.savePurchasePlan.mock.calls.at(-1)![0]).toEqual({ department_id: 1, supplier_product_id: 1, arrival_date: '2026-10-08', quantity: 500, confirmation_token: 'signed-token' })
  expect(wrapper.find('.quantity-confirmation').exists()).toBe(false)
  wrapper.unmount()
})

test('going back restores the saved quantity without confirming or saving the anomaly', async () => {
  api.savePurchasePlan.mockResolvedValueOnce({ ...challenge, quantity: 99, reasons: ['possible_repeated_key'] })
  const wrapper = open(); await flushPromises()
  await wrapper.get('input[type=number]').setValue('99'); await wrapper.get('input[type=number]').trigger('blur'); await flushPromises()
  expect(wrapper.text()).toContain('可能重复按键')
  await wrapper.get('.confirmation-actions button:first-child').trigger('click'); await flushPromises()
  expect(api.savePurchasePlan).toHaveBeenCalledTimes(1)
  expect((wrapper.get('input[type=number]').element as HTMLInputElement).value).toBe('15')
  expect(wrapper.text()).not.toContain('订货计划已保存')
  wrapper.unmount()
})

test('unusual minimum stock also requires confirmation', async () => {
  api.saveMinimumStock.mockResolvedValueOnce(challenge)
  const wrapper = open(); await flushPromises()
  await wrapper.get('.minimum-stock-cell input').setValue('500'); await wrapper.get('.minimum-stock-cell input').trigger('blur'); await flushPromises()
  expect(wrapper.get('.quantity-confirmation').text()).toContain('保底库存')
  await wrapper.get('.confirmation-actions button:last-child').trigger('click'); await flushPromises()
  expect(api.saveMinimumStock.mock.calls.at(-1)![0]).toEqual({ department_id: 1, supplier_product_id: 1, minimum_stock: 500, confirmation_token: 'signed-token' })
  wrapper.unmount()
})
