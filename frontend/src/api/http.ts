import axios, { AxiosError } from 'axios'

import type { ApiResponse } from '../types/api'

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 15_000,
  withCredentials: true,
})

http.interceptors.request.use((config) => {
  const identity = localStorage.getItem('marketflow_employee')
  if (identity) {
    try {
      const employee = JSON.parse(identity) as { id?: number; store_id?: number | null }
      const saved = localStorage.getItem(`marketflow_selected_store_${employee.id}`)
      const selected = saved ? Number(saved) : employee.store_id
      if (!config.headers.has('X-Store-ID') && selected && Number.isInteger(selected)) {
        config.headers.set('X-Store-ID', String(selected))
      }
    } catch {
      // 无效的本地展示数据不作为权限凭据，服务端始终重新验证登录状态。
    }
  }
  const csrf = document.cookie.split('; ').find((part) => part.startsWith('marketflow_csrf='))
  if (csrf) config.headers['X-CSRF-Token'] = decodeURIComponent(csrf.split('=')[1] || '')
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiResponse<unknown>>) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('marketflow_employee')
      if (window.location.pathname !== '/login') {
        window.location.assign('/login')
      }
    }
    return Promise.reject(error)
  },
)

export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError<ApiResponse<unknown>>(error)) {
    const detail = error.response?.data as unknown as { detail?: string }
    return detail?.detail || error.response?.data?.message || '请求失败，请稍后重试'
  }
  return '发生未知错误，请稍后重试'
}

export function unwrap<T>(response: ApiResponse<T>): T {
  if (response.data === null) {
    throw new Error(response.message || '接口未返回数据')
  }
  return response.data
}
