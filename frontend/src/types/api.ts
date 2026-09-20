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
  batch_stock_quantity: number
  total_stock_quantity: number
  saleable_stock_quantity: number
  near_expiry_stock_quantity: number
  near_expiry_batch_count: number
  expired_stock_quantity: number
  expired_batch_count: number
  stock_difference: number
  is_stock_consistent: boolean
  low_stock_threshold: number | null
  is_low_stock: boolean
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
  expiry_warning_days?: number | null
  low_stock_threshold: number | null
  status: ProductStatus
}

export type InventoryBatchStatus = 'available' | 'near_expiry' | 'expired' | 'sold_out'

export interface InventoryBatchListItem {
  id: number
  batch_no: string
  product_no: string
  product_name: string
  department_name: string
  initial_quantity: number
  remaining_quantity: number
  production_date: string | null
  expiration_date: string | null
  status: InventoryBatchStatus
  arrived_at: string
}

export interface InventoryBatchDetail extends InventoryBatchListItem {
  product_id: number
  department_id: number
  category_id: number
  category_name: string
  supplier_name: string
  purchase_no: string
  purchase_item_id: number
  unit_cost: string
  created_at: string
  updated_at: string
}

export type InventoryMovementAction =
  | 'create_batch'
  | 'sale_deduction'
  | 'update_quantity'
  | 'discard_expired'

export interface InventoryMovement {
  id: number
  batch_id: number
  batch_no: string | null
  product_id: number | null
  product_no: string | null
  product_name: string | null
  employee_id: number | null
  employee_name: string
  action: InventoryMovementAction
  action_name: string
  before_quantity: number | null
  change_quantity: number | null
  after_quantity: number | null
  reason: string | null
  created_at: string
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

export interface CreateSaleItem {
  product_id: number
  quantity: number
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

export interface Supplier {
  id: number
  supplier_no: string
  name: string
  contact_name: string | null
  phone: string | null
  address: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface SupplierProduct {
  id: number
  supplier_id: number
  supplier_name: string
  category_id: number | null
  category_name: string | null
  name: string
  unit_cost: string
  shelf_life_days: number | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export type PurchaseStatus = 'pending' | 'arrived'

export interface PurchaseItem {
  id: number
  supplier_product_id: number
  product_id: number | null
  supplier_id: number
  product_no: string | null
  product_name: string
  supplier_name: string
  quantity: number
  unit_cost: string
  subtotal: string
  production_date: string | null
  expiration_date: string | null
}

export interface Purchase {
  id: number
  purchase_no: string
  department_id: number
  department_name: string
  created_by: number
  created_by_name: string
  received_by: number | null
  received_by_name: string | null
  ordered_at: string
  expected_arrival_at: string
  arrived_at: string | null
  total_amount: string
  status: PurchaseStatus
  item_count: number
  total_quantity: number
  created_at: string
  updated_at: string
  items?: PurchaseItem[]
}
