export type EmployeeRole = '店长' | '正式员工' | '契约工'
export type EmployeeGender = '男' | '女' | '未填写'
export type EmploymentStatus = '在职' | '休假' | '离职' | '解雇'

export interface EmployeeDetail extends EmployeeListItem {
  department_id: number | null
  last_login_at: string | null
  gender: EmployeeGender
  birth_date: string | null
  hire_date: string
  phone: string | null
  address: string | null
  employment_status: EmploymentStatus
  separation_date: string | null
  separation_reason: string | null
  created_at: string
  updated_at: string
}

export interface EmployeeDetailUpdate {
  gender: EmployeeGender
  birth_date: string
  hire_date: string
  phone: string
  address: string
  employment_status: EmploymentStatus
  separation_date: string | null
  separation_reason: string | null
}
export type ProductStatus = 'on_sale' | 'stopped'
export type RankingGroupBy = 'product' | 'category'
export type RankingSortBy = 'quantity' | 'amount'
export type SortOrder = 'asc' | 'desc'
export type ReportMetric =
  | 'revenue'
  | 'sales_cost'
  | 'gross_profit'
  | 'sales_quantity'
  | 'sale_count'
  | 'average_sale_amount'
  | 'average_sale_quantity'
  | 'gross_profit_margin'
  | 'revenue_growth_rate'
  | 'gross_profit_growth_rate'
  | 'department_revenue_share'
  | 'sales_trend'

export interface DepartmentRevenueShare {
  department_id: number
  department_name: string
  revenue_share: string | null
}

export interface SalesTrendItem {
  start_time: string
  end_time: string
  revenue: string
  sales_cost: string
  gross_profit: string
  sales_quantity: number
  sale_count: number
  gross_profit_margin: string | null
}

export interface ReportAnalytics {
  revenue?: string | null
  sales_cost?: string | null
  gross_profit?: string | null
  sales_quantity?: number | null
  sale_count?: number | null
  average_sale_amount?: string | null
  average_sale_quantity?: string | null
  gross_profit_margin?: string | null
  revenue_growth_rate?: string | null
  gross_profit_growth_rate?: string | null
  department_revenue_share?: DepartmentRevenueShare[]
  sales_trend?: SalesTrendItem[]
}

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
