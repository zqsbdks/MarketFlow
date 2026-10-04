import { http, unwrap } from './http'
import type { ApiResponse, PageResult } from '../types/api'

export type DiscardReason = 'expired' | 'damaged' | 'spoiled' | 'contaminated' | 'other'
export interface DiscardItem {
  batch_id: number
  batch_no: string
  expiration_date: string | null
  quantity: number
  unit_cost: string
  total_cost: string
  before_quantity: number
  after_quantity: number
}
export interface DiscardStock {
  product_id: number
  product_no: string
  product_name: string
  department_id: number
  department_name: string
  available_quantity: number
  batches: { batch_id: number; batch_no: string; expiration_date: string | null; remaining_quantity: number; unit_cost: string }[]
}
export interface DiscardPlan {
  product_id: number
  product_name: string
  quantity: number
  total_cost: string
  items: DiscardItem[]
}
export interface DiscardRecord extends DiscardPlan {
  id: number
  store_id: number
  product_no: string
  department_id: number
  department_name: string
  employee_id: number | null
  employee_name: string | null
  reason_code: DiscardReason
  note: string | null
  created_at: string
}
export interface DiscardPayload {
  product_id: number
  quantity: number
  batch_id?: number
  reason_code: Exclude<DiscardReason, 'expired'>
  note?: string
  request_id: string
}
export interface DiscardPage extends PageResult<DiscardRecord> {
  total_quantity: number
  total_cost: string
}
export async function getDiscardRecords(params: Record<string, unknown>, allStores = false) {
  return unwrap((await http.get<ApiResponse<DiscardPage>>('/inventory-discards/list', {
    params, ...(allStores ? { headers: { 'X-Store-ID': 'all' } } : {}),
  })).data)
}
export async function getDiscardStock(productId: number) {
  return unwrap((await http.get<ApiResponse<DiscardStock>>(`/inventory-discards/products/${productId}/stock`)).data)
}
export async function previewDiscard(payload: Pick<DiscardPayload, 'product_id' | 'quantity' | 'batch_id'>) {
  return unwrap((await http.post<ApiResponse<DiscardPlan>>('/inventory-discards/preview', payload)).data)
}
export async function createDiscard(payload: DiscardPayload) {
  return unwrap((await http.post<ApiResponse<DiscardRecord>>('/inventory-discards', payload)).data)
}
