import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import * as api from '../api'
import type { EmployeeIdentity } from '../types/api'

function readEmployee(): EmployeeIdentity | null {
  const saved = localStorage.getItem('marketflow_employee')
  if (!saved) return null
  try {
    return JSON.parse(saved) as EmployeeIdentity
  } catch {
    localStorage.removeItem('marketflow_employee')
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  // 旧版曾把 Bearer 令牌存入浏览器，升级后不再使用。
  localStorage.removeItem('marketflow_token')
  const employee = ref<EmployeeIdentity | null>(readEmployee())
  const isAuthenticated = computed(() => Boolean(employee.value))
  const isManager = computed(() => employee.value?.role === '店长')

  function saveEmployee(value: EmployeeIdentity) {
    employee.value = value
    localStorage.setItem('marketflow_employee', JSON.stringify(value))
  }

  async function signIn(employeeNo: string, password: string) {
    const result = await api.login(employeeNo, password)
    saveEmployee(result)
    return result
  }

  async function refreshEmployee() {
    const result = await api.getMe()
    saveEmployee({ ...result, must_change_password: false })
  }

  async function signOut() {
    try {
      await api.logout()
    } catch {
      // 即使网络暂时失败，也先清除本地登录界面状态。
    } finally {
      employee.value = null
      localStorage.removeItem('marketflow_employee')
    }
  }

  return {
    employee,
    isAuthenticated,
    isManager,
    signIn,
    refreshEmployee,
    signOut,
  }
})
