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
  const token = ref(localStorage.getItem('marketflow_token'))
  const employee = ref<EmployeeIdentity | null>(readEmployee())
  const isAuthenticated = computed(() => Boolean(token.value))
  const isManager = computed(() => employee.value?.role === '店长')

  function saveEmployee(value: EmployeeIdentity) {
    employee.value = value
    localStorage.setItem('marketflow_employee', JSON.stringify(value))
  }

  async function signIn(employeeNo: string, password: string) {
    const result = await api.login(employeeNo, password)
    token.value = result.access_token
    localStorage.setItem('marketflow_token', result.access_token)
    saveEmployee(result.employee)
    return result.employee
  }

  async function refreshEmployee() {
    const result = await api.getMe()
    saveEmployee({ ...result, must_change_password: false })
  }

  function signOut() {
    token.value = null
    employee.value = null
    localStorage.removeItem('marketflow_token')
    localStorage.removeItem('marketflow_employee')
  }

  return {
    token,
    employee,
    isAuthenticated,
    isManager,
    signIn,
    refreshEmployee,
    signOut,
  }
})
