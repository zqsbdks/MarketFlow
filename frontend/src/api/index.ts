import { http, unwrap } from './http'
import type {
  AiChatMessage,
  AiConversationSummary,
  AiConversationDetail,
  AiChatResult,
  AiActionExecutionResult,
  AiProvider,
  ApiResponse,
  Category,
  CreateSaleItem,
  CreatedEmployee,
  Department,
  DepartmentReport,
  DiscountComputedStatus,
  DiscountRule,
  DiscountRulePayload,
  DiscountRuleProduct,
  DiscountScheduleType,
  DiscountType,
  EmployeeIdentity,
  EmployeeDetail,
  EmployeeDetailUpdate,
  EmployeeListItem,
  EmployeeRole,
  InventoryBatchDetail,
  InventoryBatchListItem,
  InventoryMovement,
  InventoryMovementAction,
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
  SalePricePreview,
  SaleListItem,
  SortOrder,
  Supplier,
  SupplierProduct,
  Purchase,
  PurchasePlanning,
} from '../types/api'

// region AI 聊天

export async function sendAiChat(
  provider: AiProvider,
  model: string,
  messages: AiChatMessage[],
  conversationId?: number,
) {
  const response = await http.post<ApiResponse<AiChatResult>>(
    '/ai-chat',
    { provider, model: model || undefined, messages, conversation_id: conversationId },
    {
      timeout: 45_000,
    },
  )
  return unwrap(response.data)
}

export async function getAiConversations() {
  const response = await http.get<ApiResponse<AiConversationSummary[]>>('/ai-conversations')
  return unwrap(response.data)
}

export async function getAiConversation(id: number, beforeId?: number) {
  const response = await http.get<ApiResponse<AiConversationDetail>>(`/ai-conversations/${id}`, {
    params: beforeId ? { before_id: beforeId } : undefined,
  })
  return unwrap(response.data)
}

export async function getAiCredentialStatus(provider: AiProvider) {
  const response = await http.get<ApiResponse<{ configured: boolean }>>(`/ai-chat/credentials/${provider}`)
  return unwrap(response.data)
}

export async function saveAiCredential(provider: AiProvider, apiKey: string) {
  const response = await http.put<ApiResponse<{ configured: boolean }>>(
    `/ai-chat/credentials/${provider}`,
    { api_key: apiKey },
  )
  return unwrap(response.data)
}

export async function deleteAiCredential(provider: AiProvider) {
  const response = await http.delete<ApiResponse<{ configured: boolean }>>(`/ai-chat/credentials/${provider}`)
  return unwrap(response.data)
}

export async function confirmAiAction(actionId: number) {
  const response = await http.post<ApiResponse<AiActionExecutionResult>>(
    `/ai-chat/actions/${actionId}/confirm`,
  )
  return unwrap(response.data)
}

export async function cancelAiAction(actionId: number) {
  const response = await http.post<ApiResponse<AiActionExecutionResult>>(
    `/ai-chat/actions/${actionId}/cancel`,
  )
  return unwrap(response.data)
}

// endregion

export async function login(employeeNo: string, password: string) {
  const response = await http.post<ApiResponse<EmployeeIdentity>>('/auth/session', {
    employee_no: employeeNo,
    password,
  })
  return unwrap(response.data)
}

export async function logout() {
  await http.post('/auth/logout')
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
}, allStores = false) {
  // URLSearchParams 会把多个指标编码成 metrics=a&metrics=b，供 FastAPI 解析为列表。
  const query = new URLSearchParams()
  query.set('start_time', params.start_time)
  query.set('end_time', params.end_time)
  query.set('interval', params.interval)
  if (params.department_id !== undefined) query.set('department_id', String(params.department_id))
  for (const metric of params.metrics) query.append('metrics', metric)
  const response = await http.get<ApiResponse<ReportAnalytics>>('/reports/analytics', { params: query, headers: allStores ? { 'X-Store-ID': 'all' } : undefined })
  return unwrap(response.data)
}

export async function getDepartments() {
  const response = await http.get<ApiResponse<Department[]>>('/departments', {
    headers: { 'Cache-Control': 'no-cache' },
  })
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
  expectedVersion: number,
  reason?: string,
) {
  const response = await http.put<ApiResponse<ProductDetail>>(`/products/${productId}/status`, {
    status,
    expected_version: expectedVersion,
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

export async function getInventoryMovements(params: {
  page?: number
  page_size?: number
  keyword?: string
  action?: InventoryMovementAction
  batch_id?: number
  product_id?: number
  start_time?: string
  end_time?: string
}) {
  const response = await http.get<ApiResponse<PageResult<InventoryMovement>>>(
    '/operation-audit-logs/inventory-movements',
    { params },
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

export async function createSale(items: CreateSaleItem[], clientRequestId: string) {
  const response = await http.post<ApiResponse<SaleDetail>>('/sales', {
    items,
    client_request_id: clientRequestId,
  })
  return unwrap(response.data)
}

export async function previewSalePrice(items: CreateSaleItem[]) {
  const response = await http.post<ApiResponse<SalePricePreview>>('/sales/preview', { items })
  return unwrap(response.data)
}

// region 折扣规则与适用商品
export async function getDiscountRules(params: {
  page?: number
  page_size?: number
  keyword?: string
  department_id?: number
  discount_type?: DiscountType
  schedule_type?: DiscountScheduleType
  is_active?: boolean
  computed_status?: DiscountComputedStatus
}) {
  return unwrap(
    (
      await http.get<ApiResponse<PageResult<DiscountRule>>>('/discount-rules/list', {
        params,
      })
    ).data,
  )
}

export async function getDiscountRule(ruleId: number) {
  return unwrap((await http.get<ApiResponse<DiscountRule>>(`/discount-rules/${ruleId}`)).data)
}

export async function createDiscountRule(payload: DiscountRulePayload) {
  return unwrap((await http.post<ApiResponse<DiscountRule>>('/discount-rules', payload)).data)
}

export async function updateDiscountRule(ruleId: number, payload: DiscountRulePayload) {
  return unwrap(
    (await http.patch<ApiResponse<DiscountRule>>(`/discount-rules/${ruleId}`, payload)).data,
  )
}

export async function updateDiscountRuleStatus(
  ruleId: number,
  isActive: boolean,
  expectedVersion: number,
  reason?: string,
) {
  return unwrap(
    (
      await http.patch<ApiResponse<DiscountRule>>(`/discount-rules/${ruleId}/status`, {
        is_active: isActive,
        expected_version: expectedVersion,
        reason: reason || undefined,
      })
    ).data,
  )
}

export async function deleteDiscountRule(ruleId: number) {
  await http.delete(`/discount-rules/${ruleId}`)
}

export async function clearDiscountRules() {
  await http.delete('/discount-rules')
}

export async function getDiscountRuleProducts(
  ruleId: number,
  params: { page?: number; page_size?: number; keyword?: string; category_id?: number } = {},
) {
  return unwrap(
    (
      await http.get<ApiResponse<PageResult<DiscountRuleProduct>>>(
        `/discount-rules/${ruleId}/products`,
        { params },
      )
    ).data,
  )
}

export async function addDiscountRuleProducts(ruleId: number, productIds: number[]) {
  await http.post(`/discount-rules/${ruleId}/products`, { product_ids: productIds })
}

export async function deleteDiscountRuleProduct(ruleId: number, productId: number) {
  await http.delete(`/discount-rules/${ruleId}/products/${productId}`)
}

export async function clearDiscountRuleProducts(ruleId: number) {
  await http.delete(`/discount-rules/${ruleId}/products`)
}

// endregion

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

export async function getPurchasePlanning(departmentId: number, arrivalDate?: string) {
  return unwrap((await http.get<ApiResponse<PurchasePlanning>>('/purchases/planning', {
    params: { department_id: departmentId, arrival_date: arrivalDate },
  })).data)
}

export async function receivePurchase(id: number) {
  return unwrap((await http.put<ApiResponse<Purchase>>(`/purchases/${id}/receive`)).data)
}

export async function savePurchasePlan(payload: { department_id: number; arrival_date: string; supplier_product_id: number; quantity: number | null }) {
  return unwrap((await http.put<ApiResponse<{ quantity: number }>>('/purchases/planning', payload)).data)
}

export async function saveMinimumStock(payload: { department_id: number; supplier_product_id: number; minimum_stock: number }) {
  return unwrap((await http.put<ApiResponse<{ minimum_stock: number }>>('/purchases/minimum-stock', payload)).data)
}

export async function createPurchase(payload: Record<string, unknown>) {
  return unwrap((await http.post<ApiResponse<Purchase>>('/purchases/', payload)).data)
}

export async function autoReceivePurchases() {
  return unwrap((await http.put<ApiResponse<Purchase[]>>('/purchases/auto-receive')).data)
}
