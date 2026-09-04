import { http, unwrap } from './http'
import type {
  ApiResponse,
  Category,
  CreatedEmployee,
  Department,
  DepartmentReport,
  EmployeeIdentity,
  EmployeeListItem,
  EmployeeRole,
  LoginResult,
  OverviewReport,
  PageResult,
  ProductDetail,
  ProductListItem,
  RankingsResult,
  RankingGroupBy,
  RankingSortBy,
  SaleDetail,
  SaleListItem,
  SortOrder,
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

export async function getSales(params: Record<string, unknown>) {
  const response = await http.get<ApiResponse<PageResult<SaleListItem>>>('/sales/list', { params })
  return unwrap(response.data)
}

export async function getSale(saleNo: string) {
  const response = await http.get<ApiResponse<SaleDetail>>(`/sales/${saleNo}`)
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

export async function updateEmployeeStatus(employeeId: number, isActive: boolean) {
  await http.put(`/employees/status/${employeeId}`, { is_active: isActive })
}

export async function resetEmployeePassword(employeeId: number) {
  const response = await http.put<ApiResponse<CreatedEmployee>>(
    `/employees/reset-password/${employeeId}`,
  )
  return unwrap(response.data)
}
