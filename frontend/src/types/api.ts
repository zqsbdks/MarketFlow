export type EmployeeRole = '店长' | '正式员工' | '契约工'
export type ProductStatus = 'on_sale' | 'stopped'
export type RankingGroupBy = 'product' | 'category'
export type RankingSortBy = 'quantity' | 'amount'
export type SortOrder = 'asc' | 'desc'

export interface ApiResponse<T> {
  code: number
  message: string
  data: T | null
}

export interface Department {
  id: number
  name: string
}

export interface EmployeeIdentity {
  id: number
  employee_no: string
  name: string
  role: EmployeeRole
  department: Department | null
  must_change_password?: boolean
  is_active?: boolean
}

export interface LoginResult {
  access_token: string
  token_type: 'bearer'
  employee: EmployeeIdentity
}

export interface OverviewReport {
  revenue: string
  sales_cost: string
  gross_profit: string
  sales_quantity: number
  sale_count: number
}

export interface DepartmentReport {
  department_id: number
  department_name: string
  revenue: string
  gross_profit: string
  sales_quantity: number
}

export interface RankingItem {
  rank: number
  id: number
  name: string
  quantity: number
  amount: string
}

export interface RankingsResult extends PageResult<RankingItem> {}

export interface ProductListItem {
  id: number
  product_no: string
  name: string
  department_name: string
  category_name: string
  purchase_price: string
  sale_price: string
  stock_quantity: number
  status: ProductStatus
}

export interface ProductDetail {
  id: number
  product_no: string
  name: string
  department: Department
  category: Department
  purchase_price: string
  sale_price: string
  stock_quantity: number
  status: ProductStatus
}

export interface SaleListItem {
  sale_no: string
  sold_at: string
  total_amount: string
  total_quantity: number
  item_count: number
}

export interface SaleDetailItem {
  product_name: string
  quantity: number
  unit_price: string
  subtotal: string
}

export interface SaleDetail {
  sale_no: string
  sold_at: string
  total_amount: string
  items: SaleDetailItem[]
}

export interface EmployeeListItem {
  id: number
  employee_no: string
  name: string
  role: EmployeeRole
  department_name: string | null
  is_active: boolean
}

export interface PageResult<T> {
  items: T[]
  page: number
  page_size: number
  total: number
  total_pages: number
}

export interface Category {
  id: number
  name: string
  department_id?: number
}

export interface CreatedEmployee {
  id: number
  employee_no?: string
  temporary_password: string
  must_change_password: boolean
}
