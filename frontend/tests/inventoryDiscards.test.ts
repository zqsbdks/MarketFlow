import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, test, vi } from 'vitest'
import InventoryDiscards from '../src/components/InventoryDiscards.vue'

const api = vi.hoisted(() => ({ getDiscardRecords: vi.fn(), getDiscardStock: vi.fn(), previewDiscard: vi.fn(), createDiscard: vi.fn() }))
const identity = vi.hoisted(() => ({ isManager: true, isHeadquarters: false, employee: { role: '店长' } }))
vi.mock('../src/api/inventoryDiscards', () => api)
vi.mock('../src/api', () => ({ getDepartments: async () => [] }))
vi.mock('../src/api/http', () => ({ getErrorMessage: () => '请求失败' }))
vi.mock('../src/stores/auth', () => ({ useAuthStore: () => identity }))
vi.mock('../src/stores/storeScope', () => ({ useStoreScope: () => ({ canWriteStore: true, selectedId: 1, stores: [] }) }))

beforeEach(() => {
  vi.clearAllMocks()
  identity.isManager = true; identity.isHeadquarters = false; identity.employee.role = '店长'
  api.getDiscardRecords.mockResolvedValue({ items: [], total: 0, total_pages: 0, total_quantity: 0, total_cost: '0' })
  api.getDiscardStock.mockResolvedValue({ product_id: 1, product_name: '商品原名', department_name: '青果部', available_quantity: 10, batches: [{ batch_id: 5, batch_no: 'LOT-5', remaining_quantity: 10 }] })
  api.previewDiscard.mockResolvedValue({ product_id: 1, quantity: 1, total_cost: '3', items: [{ batch_id: 5, batch_no: 'LOT-5', quantity: 1, before_quantity: 10, after_quantity: 9 }] })
  api.createDiscard.mockResolvedValue({ id: 1 })
})
function render() {
  return mount(InventoryDiscards, { global: { stubs: { ModalPanel: { props: ['open'], template: '<div v-if="open"><slot /></div>' } } } })
}
async function button(wrapper: ReturnType<typeof render>, text: string) {
  const target = wrapper.findAll('button').find(b => b.text() === text)
  expect(target).toBeDefined()
  await target!.trigger('click'); await flushPromises()
}
async function prepare(wrapper: ReturnType<typeof render>) {
  await button(wrapper, '手动废弃')
  await wrapper.get('.discard-lookup input').setValue(1)
  await button(wrapper, '查询商品')
  await wrapper.get('.stack-form').trigger('submit'); await flushPromises()
}

test('preview does not write, and an ambiguous failed submission retries with the same request ID', async () => {
  const wrapper = render(); await flushPromises()
  await prepare(wrapper)
  expect(api.createDiscard).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('LOT-5')
  api.createDiscard.mockRejectedValueOnce(new Error('network'))
  await button(wrapper, '确认废弃')
  const first = api.createDiscard.mock.calls[0]![0]
  expect(wrapper.text()).toContain('请求失败')
  await button(wrapper, '确认废弃')
  expect(api.createDiscard.mock.calls[1]![0]).toEqual(first)
  expect(first).toMatchObject({ product_id: 1, quantity: 1, reason_code: 'damaged' })
  expect(first.request_id).toMatch(/^[0-9a-f-]{36}$/)
  expect(wrapper.emitted('changed')).toHaveLength(1)
  wrapper.unmount()
})

test('changing quantity invalidates the previous confirmation plan', async () => {
  const wrapper = render(); await flushPromises(); await prepare(wrapper)
  expect(wrapper.find('.discard-preview').exists()).toBe(true)
  await wrapper.get('.stack-form input[max]').setValue(2)
  expect(wrapper.find('.discard-preview').exists()).toBe(false)
  expect(api.createDiscard).not.toHaveBeenCalled()
  wrapper.unmount()
})

test('headquarters has company summary and no manual disposal button', async () => {
  identity.isManager = false; identity.isHeadquarters = true; identity.employee.role = '总部'
  const wrapper = render(); await flushPromises()
  expect(wrapper.findAll('button').some(b => b.text() === '手动废弃')).toBe(false)
  await wrapper.get('.discard-checkbox input').setValue(true)
  await wrapper.get('.discard-filters').trigger('submit'); await flushPromises()
  expect(api.getDiscardRecords).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1 }), true)
  wrapper.unmount()
})

test('failed pagination retains the previous page and results', async () => {
  api.getDiscardRecords.mockResolvedValue({ items: [], total: 21, total_pages: 2, total_quantity: 21, total_cost: '100' })
  const wrapper = render(); await flushPromises()
  api.getDiscardRecords.mockRejectedValueOnce(new Error('network'))
  await button(wrapper, '下一页')
  expect(wrapper.get('.pagination').text()).toContain('1 / 2')
  expect(wrapper.text()).toContain('请求失败')
  wrapper.unmount()
})
