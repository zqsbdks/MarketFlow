import axios, { AxiosError } from 'axios'

import type { ApiResponse } from '../types/api'

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 15_000,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('marketflow_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiResponse<unknown>>) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('marketflow_token')
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
