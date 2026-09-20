import { http, unwrap } from './http'
import type {
  ApiResponse,
  Category,
  CreateSaleItem,
  CreatedEmployee,
  Department,
  DepartmentReport,
  EmployeeIdentity,
  EmployeeDetail,
  EmployeeDetailUpdate,
  EmployeeListItem,
  EmployeeRole,
  LoginResult,
  InventoryBatchDetail,
  InventoryBatchListItem,
  OverviewReport,
  PageResult,
  ProductDetail,
  ProductListItem,
  RankingsResult,
  ReportAnalytics,
  ReportMetric,
  RankingGroupBy,
  RankingSortBy,
  SaleDetail,
  SaleListItem,
  SortOrder,
  Supplier,
  SupplierProduct,
  Purchase,
} from '../types/api'

export async function login(employeeNo: string, password: string) {
  const response = await http.post<ApiResponse<LoginResult>>('/auth/login', {
    employee_no: employeeNo,
    password,
  })
  return unwrap(response.data)
}

export async function getMe() {
  const response = await http.get<ApiResponse<EmployeeIdentity>>('/auth/me')
  return unwrap(response.data)
}

export async function changePassword(oldPassword: string, newPassword: string) {
  await http.post('/auth/password', {
    old_password: oldPassword,
    new_password: newPassword,
    confirm_password: newPassword,
  })
}

export async function getOverview(params: Record<string, unknown> = {}) {
  const response = await http.get<ApiResponse<OverviewReport>>('/reports/overview', { params })
  return unwrap(response.data)
}

export async function getDepartmentReports(params: Record<string, unknown> = {}) {
  const response = await http.get<ApiResponse<DepartmentReport[]>>('/reports/departments', {
    params,
  })
  return unwrap(response.data)
}

export async function getRankings(params: {
  start_date?: string
  end_date?: string
  department_id?: number
  category_id?: number
  group_by?: RankingGroupBy
  sort_by?: RankingSortBy
  sort_order?: SortOrder
  page?: number
  page_size?: number
}) {
  const response = await http.get<ApiResponse<RankingsResult>>('/reports/rankings', { params })
  return unwrap(response.data)
}

export async function getReportAnalytics(params: {
  start_time: string
  end_time: string
  department_id?: number
  interval: 'hour' | 'day' | 'month' | 'year'
  metrics: ReportMetric[]
}) {
  // URLSearchParams 会把多个指标编码成 metrics=a&metrics=b，供 FastAPI 解析为列表。
  const query = new URLSearchParams()
  query.set('start_time', params.start_time)
  query.set('end_time', params.end_time)
  query.set('interval', params.interval)
  if (params.department_id !== undefined) query.set('department_id', String(params.department_id))
  for (const metric of params.metrics) query.append('metrics', metric)
  const response = await http.get<ApiResponse<ReportAnalytics>>('/reports/analytics', { params: query })
  return unwrap(response.data)
}

export async function getDepartments() {
  const response = await http.get<ApiResponse<Department[]>>('/departments')
  return unwrap(response.data)
}

export async function getCategories(departmentId?: number) {
  const response = await http.get<ApiResponse<Category[]>>('/categories/list', {
    params: { department_id: departmentId },
  })
  return unwrap(response.data)
}

export async function getProducts(params: Record<string, unknown>) {
  const response = await http.get<ApiResponse<PageResult<ProductListItem>>>('/products/list', {
    params,
  })
  return unwrap(response.data)
}

export async function getProduct(productId: number) {
  const response = await http.get<ApiResponse<ProductDetail>>(`/products/${productId}`)
  return unwrap(response.data)
}

export async function updateProduct(productId: number, payload: Record<string, unknown>) {
  const response = await http.put<ApiResponse<ProductDetail>>(`/products/${productId}`, payload)
  return unwrap(response.data)
}

export async function updateProductStatus(
  productId: number,
  status: 'on_sale' | 'stopped',
  reason?: string,
) {
  const response = await http.put<ApiResponse<ProductDetail>>(`/products/${productId}/status`, {
    status,
    reason: reason || undefined,
  })
  return unwrap(response.data)
}

export async function getInventoryBatches(params: Record<string, unknown> = {}) {
  const response = await http.get<ApiResponse<PageResult<InventoryBatchListItem>>>(
    '/inventory-batches/list',
    { params },
  )
  return unwrap(response.data)
}

export async function getInventoryBatch(batchId: number) {
  const response = await http.get<ApiResponse<InventoryBatchDetail>>(
    `/inventory-batches/${batchId}`,
  )
  return unwrap(response.data)
}

export async function updateInventoryBatchQuantity(
  batchId: number,
  remainingQuantity: number,
  reason?: string,
) {
  const response = await http.put<ApiResponse<InventoryBatchDetail>>(
    `/inventory-batches/${batchId}/quantity`,
    { remaining_quantity: remainingQuantity, reason: reason || undefined },
  )
  return unwrap(response.data)
}

export async function discardExpiredInventoryBatch(batchId: number, reason?: string) {
  const response = await http.post<ApiResponse<InventoryBatchDetail>>(
    `/inventory-batches/${batchId}/discard`,
    { reason: reason || undefined },
  )
  return unwrap(response.data)
}

export async function getSales(params: Record<string, unknown>) {
  const response = await http.get<ApiResponse<PageResult<SaleListItem>>>('/sales/list', { params })
  return unwrap(response.data)
}

export async function getSale(saleNo: string) {
  const response = await http.get<ApiResponse<SaleDetail>>(`/sales/${saleNo}`)
  return unwrap(response.data)
}

export async function createSale(items: CreateSaleItem[]) {
  const response = await http.post<ApiResponse<SaleDetail>>('/sales', { items })
  return unwrap(response.data)
}

export async function getEmployees(params: Record<string, unknown>) {
  const response = await http.get<ApiResponse<PageResult<EmployeeListItem>>>('/employees/list', {
    params,
  })
  return unwrap(response.data)
}

export async function createEmployee(payload: {
  name: string
  role: EmployeeRole
  department_id: number | null
}) {
  const response = await http.post<ApiResponse<CreatedEmployee>>('/employees/create', payload)
  return unwrap(response.data)
}

export async function updateEmployeeStatus(employeeId: number, isActive: boolean, reason?: string) {
  await http.put(`/employees/status/${employeeId}`, {
    is_active: isActive,
    reason: reason || undefined,
  })
}

export async function resetEmployeePassword(employeeId: number, reason?: string) {
  const response = await http.put<ApiResponse<CreatedEmployee>>(
    `/employees/reset-password/${employeeId}`,
    { reason: reason || undefined },
  )
  return unwrap(response.data)
}

export async function getEmployeeDetail(employeeId: number) {
  return unwrap((await http.get<ApiResponse<EmployeeDetail>>(`/employees/${employeeId}`)).data)
}

export async function updateEmployeeDetail(employeeId: number, payload: EmployeeDetailUpdate) {
  return unwrap((await http.put<ApiResponse<EmployeeDetail>>(`/employees/${employeeId}`, payload)).data)
}

export async function getSuppliers(params: Record<string, unknown> = {}) {
  return unwrap((await http.get<ApiResponse<PageResult<Supplier>>>('/suppliers/list', { params })).data)
}

export async function getSupplier(id: number) {
  return unwrap((await http.get<ApiResponse<Supplier>>(`/suppliers/${id}`)).data)
}

export async function createSupplier(payload: Record<string, unknown>) {
  return unwrap((await http.post<ApiResponse<Supplier>>('/suppliers/', payload)).data)
}

export async function updateSupplier(id: number, payload: Record<string, unknown>) {
  return unwrap((await http.put<ApiResponse<Supplier>>(`/suppliers/${id}`, payload)).data)
}

export async function updateSupplierStatus(id: number, isActive: boolean, reason?: string) {
  return unwrap(
    (
      await http.put<ApiResponse<Supplier>>(`/suppliers/${id}/status`, {
        is_active: isActive,
        reason: reason || undefined,
      })
    ).data,
  )
}

export async function getSupplierProducts(params: Record<string, unknown> = {}) {
  return unwrap((await http.get<ApiResponse<PageResult<SupplierProduct>>>('/supplier-products/list', { params })).data)
}

export async function getSupplierProduct(id: number) {
  return unwrap(
    (await http.get<ApiResponse<SupplierProduct>>(`/supplier-products/${id}`)).data,
  )
}

export async function createSupplierProduct(payload: Record<string, unknown>) {
  return unwrap((await http.post<ApiResponse<SupplierProduct>>('/supplier-products', payload)).data)
}

export async function updateSupplierProduct(id: number, payload: Record<string, unknown>) {
  return unwrap((await http.put<ApiResponse<SupplierProduct>>(`/supplier-products/${id}`, payload)).data)
}

export async function updateSupplierProductStatus(id: number, isActive: boolean, reason?: string) {
  return unwrap(
    (
      await http.put<ApiResponse<SupplierProduct>>(`/supplier-products/${id}/status`, {
        is_active: isActive,
        reason: reason || undefined,
      })
    ).data,
  )
}

export async function getPurchases(params: Record<string, unknown> = {}) {
  return unwrap((await http.get<ApiResponse<PageResult<Purchase>>>('/purchases/list', { params })).data)
}

export async function getPurchase(id: number) {
  return unwrap((await http.get<ApiResponse<Purchase>>(`/purchases/${id}`)).data)
}

export async function createPurchase(payload: Record<string, unknown>) {
  return unwrap((await http.post<ApiResponse<Purchase>>('/purchases/', payload)).data)
}

export async function autoReceivePurchases() {
  return unwrap((await http.put<ApiResponse<Purchase[]>>('/purchases/auto-receive')).data)
}
