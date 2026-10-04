import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, test, vi } from 'vitest'
import ProcurementView from '../src/views/ProcurementView.vue'

const api = vi.hoisted(() => ({
  getSuppliers: vi.fn(), getSupplierProducts: vi.fn(), getPurchases: vi.fn(),
  getDepartments: vi.fn(), getCategories: vi.fn(),
  updateSupplierStatus: vi.fn(), receivePurchase: vi.fn(),
}))

vi.mock('../src/api', () => api)
vi.mock('../src/api/http', () => ({ getErrorMessage: () => '请求失败' }))
vi.mock('../src/stores/auth', () => ({ useAuthStore: () => ({ isManager: true, employee: { department: null } }) }))
vi.mock('../src/stores/storeScope', () => ({ useStoreScope: () => ({ canWriteStore: true }) }))
vi.mock('../src/i18n', () => ({
  language: { value: 'zh' }, confirmTranslated: () => true, promptTranslated: () => '',
}))

const pageResult = (page: number, total: number, items: unknown[], size = 20) => ({
  page, page_size: size, total, total_pages: Math.ceil(total / size), items,
})

beforeEach(() => {
  vi.clearAllMocks()
  api.getDepartments.mockResolvedValue([])
  api.getCategories.mockResolvedValue([])
  api.getSuppliers.mockImplementation(async ({ page, page_size }) => pageResult(page, 205,
    Array.from({ length: Math.min(page_size, 205 - (page - 1) * page_size) }, (_, i) => ({
      id: (page - 1) * page_size + i + 1, name: `supplier-${(page - 1) * page_size + i + 1}`, is_active: true,
    })), page_size))
  api.getSupplierProducts.mockImplementation(async ({ page }) => pageResult(page, 105, [{ id: page, name: `catalog-page-${page}` }]))
  api.getPurchases.mockImplementation(async ({ page }) => pageResult(page, 836, [{
    id: page, purchase_no: `purchase-page-${page}`, total_amount: '10.00', status: 'arrived',
    ordered_at: '2026-10-01T10:00:00', expected_arrival_at: '2026-10-03T12:00:00',
  }]))
})

function render() {
  return mount(ProcurementView, { global: { stubs: {
    PageHeader: { template: '<div><slot /></div>' },
    ModalPanel: { props: ['open'], template: '<div v-if="open"><slot /></div>' },
    PurchasePlanner: true,
  } } })
}

test('purchase pagination uses server totals and query resets page to one', async () => {
  const wrapper = render()
  await flushPromises()
  expect(wrapper.text()).toContain('836 张进货单')
  expect(wrapper.get('[data-testid="procurement-pagination"]').text()).toContain('1 / 42')
  await wrapper.get('[data-testid="procurement-pagination"] button:last-child').trigger('click')
  await flushPromises()
  expect(api.getPurchases).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, page_size: 20 }))
  expect(wrapper.text()).toContain('purchase-page-2')
  await wrapper.get('.purchase-filters input').setValue('P123')
  await wrapper.get('.purchase-filters button').trigger('click')
  await flushPromises()
  expect(api.getPurchases).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, purchase_no: 'P123' }))
  wrapper.unmount()
})

test('each tab has independent pagination and complete supplier selection options', async () => {
  const wrapper = render()
  await flushPromises()
  await wrapper.get('.procurement-tabs button:nth-child(2)').trigger('click')
  await wrapper.get('[data-testid="procurement-pagination"] button:last-child').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('catalog-page-2')
  await wrapper.get('.procurement-tabs button:nth-child(3)').trigger('click')
  expect(wrapper.get('[data-testid="procurement-pagination"]').text()).toContain('1 / 11')
  await wrapper.get('[data-testid="procurement-pagination"] button:last-child').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('supplier-21')
  await wrapper.get('.procurement-tabs button:nth-child(2)').trigger('click')
  expect(wrapper.get('[data-testid="procurement-pagination"]').text()).toContain('2 / 6')
  await wrapper.get('.section-bar .primary-button').trigger('click')
  await flushPromises()
  const options = wrapper.findAll('.form-grid label:first-child select option')
  expect(options).toHaveLength(206)
  expect(options.at(-1)?.text()).toBe('supplier-205')
  wrapper.unmount()
})

test('last-page row removal returns to the remaining page', async () => {
  api.getPurchases.mockImplementation(async ({ page }) => pageResult(page, 21, [{
    id: page, purchase_no: `purchase-page-${page}`, total_amount: '10', status: 'pending',
    ordered_at: '2026-10-01T10:00:00', expected_arrival_at: '2026-10-03T12:00:00',
  }]))
  const wrapper = render()
  await flushPromises()
  await wrapper.get('[data-testid="procurement-pagination"] button:last-child').trigger('click')
  await flushPromises()
  api.getPurchases.mockImplementation(async ({ page }) => pageResult(page, 20, page === 2 ? [] : [{
    id: 1, purchase_no: 'remaining-order', total_amount: '10', status: 'pending',
    ordered_at: '2026-10-01T10:00:00', expected_arrival_at: '2026-10-03T12:00:00',
  }]))
  await wrapper.get('.receive-button').trigger('click')
  await flushPromises()
  expect(wrapper.get('[data-testid="procurement-pagination"]').text()).toContain('1 / 1')
  expect(wrapper.text()).toContain('remaining-order')
  wrapper.unmount()
})

test('failed page requests retain the previous page instead of mislabeling old rows', async () => {
  const wrapper = render()
  await flushPromises()
  api.getPurchases.mockRejectedValueOnce(new Error('network failure'))
  await wrapper.get('[data-testid="procurement-pagination"] button:last-child').trigger('click')
  await flushPromises()
  expect(wrapper.get('[data-testid="procurement-pagination"]').text()).toContain('1 / 42')
  expect(wrapper.text()).toContain('purchase-page-1')
  expect(wrapper.text()).toContain('请求失败')
  wrapper.unmount()
})
