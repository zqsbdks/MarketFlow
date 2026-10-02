<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { http, unwrap, getErrorMessage } from '../api/http'
import type { ApiResponse } from '../types/api'
import { useStoreScope } from '../stores/storeScope'

interface Department { id: number; name: string; code: string; is_active: boolean }
interface Category { id: number; name: string; department_id: number; is_active: boolean }
interface Employee { id: number; employee_no: string; name: string; store_id: number | null; department_id: number | null; role: string }
interface CompanyData { departments: Department[]; categories: Category[]; employees: Employee[] }
interface StoreDepartment { id: number; name: string; is_active: boolean }
interface Report { revenue: string; gross_profit: string; sales_quantity: number; sale_count: number }

const scope = useStoreScope()
const company = ref<CompanyData>({ departments: [], categories: [], employees: [] })
const selectedStore = ref<number | null>(null)
const enabledDepartments = ref<StoreDepartment[]>([])
const error = ref('')
const message = ref('')
const busy = ref(false)
const newStore = ref({ name: '', address: '', phone: '', department_ids: [] as number[] })
const newEmployee = ref({ name: '', role: '店长', store_id: 1, department_id: null as number | null })
const transfer = ref({ employee_id: 0, store_id: 1, department_id: null as number | null, role: '正式员工', reason: '' })
const newDepartment = ref({ code: '', name: '' })
const newCategory = ref({ name: '', department_id: 0 })
const companyReport = ref<Report | null>(null)
const activeDepartments = computed(() => company.value.departments.filter((item) => item.is_active))
const selectedEmployee = computed(() => company.value.employees.find((item) => item.id === transfer.value.employee_id))

async function load() {
  await scope.load()
  const response = await http.get<ApiResponse<CompanyData>>('/stores/company-data')
  company.value = unwrap(response.data)
  if (!selectedStore.value) selectedStore.value = scope.selectedId
  if (selectedStore.value) await loadDepartments(selectedStore.value)
}

async function loadDepartments(storeId: number) {
  selectedStore.value = storeId
  const response = await http.get<ApiResponse<StoreDepartment[]>>(`/stores/${storeId}/departments`)
  enabledDepartments.value = unwrap(response.data)
}

async function loadCompanyReport() {
  try {
    const today = new Date()
    const first = new Date(today)
    first.setDate(first.getDate() - 60)
    const format = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
    const response = await http.get<ApiResponse<Report>>('/reports/overview', {
      headers: { 'X-Store-ID': 'all' },
      params: { start_time: `${format(first)}T09:00:00`, end_time: `${format(today)}T21:00:00` },
    })
    companyReport.value = unwrap(response.data)
  } catch (cause) { error.value = getErrorMessage(cause) }
}

async function run(action: () => Promise<unknown>) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    const result = await action()
    await load()
    message.value = typeof result === 'string' ? result : '保存成功'
  } catch (cause) { error.value = getErrorMessage(cause) }
  finally { busy.value = false }
}

function createStore() {
  void run(async () => {
    await http.post('/stores', { ...newStore.value, is_active: true })
    newStore.value = { name: '', address: '', phone: '', department_ids: [] }
  })
}
function toggleStore(store: { id: number; name: string; address?: string | null; phone?: string | null; is_active: boolean }) {
  void run(() => http.put(`/stores/${store.id}`, {
      name: store.name,
      address: store.address ?? null,
      phone: store.phone ?? null,
      is_active: !store.is_active,
  }))
}
function toggleDepartment(department: StoreDepartment) {
  if (!selectedStore.value) return
  void run(() => http.put(`/stores/${selectedStore.value}/departments/${department.id}`, { is_active: !department.is_active }))
}
function createEmployee() {
  void run(async () => {
    const payload = {
      ...newEmployee.value,
      store_id: newEmployee.value.role === '总部' ? null : newEmployee.value.store_id,
      department_id: newEmployee.value.role === '总部' ? null : newEmployee.value.department_id,
    }
    const response = await http.post<ApiResponse<{ employee_no: string; temporary_password: string }>>('/stores/employees', payload)
    const data = unwrap(response.data)
    return `员工编号：${data.employee_no}，一次性初始密码：${data.temporary_password}`
  })
}
function transferEmployee() {
  void run(() => http.put(`/stores/employees/${transfer.value.employee_id}/assignment`, {
    store_id: transfer.value.role === '总部' ? null : transfer.value.store_id,
    department_id: transfer.value.role === '总部' ? null : transfer.value.department_id,
    role: transfer.value.role,
    reason: transfer.value.reason || null,
  }))
}
function createDepartment() {
  void run(() => http.post('/stores/company-departments', { ...newDepartment.value, is_active: true }))
}
function createCategory() {
  void run(() => http.post('/stores/company-categories', { ...newCategory.value, is_active: true }))
}
onMounted(() => { void load().catch((cause) => { error.value = getErrorMessage(cause) }) })
</script>

<template>
  <section class="company-page">
    <header><small>HEADQUARTERS</small><h1>门店与总部</h1><p>统一维护门店、部门、分类和员工归属。</p></header>
    <section class="company-card"><h2>全公司近 60 天经营概览</h2><button @click="loadCompanyReport">刷新汇总</button><p v-if="companyReport">营业额 ¥{{ companyReport.revenue }} · 毛利润 ¥{{ companyReport.gross_profit }} · {{ companyReport.sales_quantity }} 件 / {{ companyReport.sale_count }} 单</p></section>
    <p v-if="error" class="company-error">{{ error }}</p>
    <p v-if="message" class="company-success">{{ message }}</p>
    <div class="company-grid">
      <section class="company-card">
        <h2>门店（{{ scope.stores.length }}）</h2>
        <select :value="selectedStore ?? ''" @change="loadDepartments(Number(($event.target as HTMLSelectElement).value))">
          <option v-for="store in scope.stores" :key="store.id" :value="store.id">{{ store.store_no }} {{ store.name }}</option>
        </select>
        <p v-for="store in scope.stores" :key="store.id">{{ store.store_no }} · {{ store.name }} · {{ store.is_active ? '启用' : '停用' }} <button :disabled="busy" @click="toggleStore(store)">{{ store.is_active ? '停用' : '启用' }}</button></p>
        <h3>新增门店</h3>
        <form @submit.prevent="createStore"><input v-model="newStore.name" placeholder="门店名称" required /><input v-model="newStore.address" placeholder="地址" /><input v-model="newStore.phone" placeholder="电话" /><label v-for="department in activeDepartments" :key="department.id"><input v-model="newStore.department_ids" type="checkbox" :value="department.id" />{{ department.name }}</label><button :disabled="busy">创建门店</button></form>
      </section>
      <section class="company-card">
        <h2>门店启用部门</h2>
        <p v-for="department in enabledDepartments" :key="department.id">{{ department.name }} · {{ department.is_active ? '启用' : '停用' }} <button :disabled="busy" @click="toggleDepartment(department)">{{ department.is_active ? '停用' : '启用' }}</button></p>
        <h3>统一部门与分类</h3>
        <form @submit.prevent="createDepartment"><input v-model="newDepartment.code" placeholder="部门编号" required /><input v-model="newDepartment.name" placeholder="部门名称" required /><button :disabled="busy">新增部门</button></form>
        <form @submit.prevent="createCategory"><input v-model="newCategory.name" placeholder="分类名称" required /><select v-model.number="newCategory.department_id" required><option :value="0" disabled>所属部门</option><option v-for="department in activeDepartments" :key="department.id" :value="department.id">{{ department.name }}</option></select><button :disabled="busy">新增分类</button></form>
        <p v-for="category in company.categories" :key="category.id">{{ category.name }} · {{ activeDepartments.find((item) => item.id === category.department_id)?.name }}</p>
      </section>
      <section class="company-card">
        <h2>员工调店和任命</h2>
        <form @submit.prevent="transferEmployee">
          <select v-model.number="transfer.employee_id" required><option :value="0" disabled>选择员工</option><option v-for="employee in company.employees" :key="employee.id" :value="employee.id">{{ employee.employee_no }} {{ employee.name }} · {{ employee.role }}</option></select>
          <p v-if="selectedEmployee">当前门店：{{ scope.stores.find((item) => item.id === selectedEmployee?.store_id)?.name || '总部' }}</p>
          <select v-model="transfer.role"><option value="总部">总部</option><option value="店长">店长</option><option value="正式员工">正式员工</option><option value="契约工">契约工</option></select>
          <select v-if="transfer.role !== '总部'" v-model.number="transfer.store_id"><option v-for="store in scope.stores.filter((item) => item.is_active)" :key="store.id" :value="store.id">{{ store.store_no }} {{ store.name }}</option></select>
          <select v-if="transfer.role !== '总部'" v-model="transfer.department_id"><option :value="null">无部门（仅店长）</option><option v-for="department in activeDepartments" :key="department.id" :value="department.id">{{ department.name }}</option></select>
          <input v-model="transfer.reason" placeholder="调整理由（可选）" /><button :disabled="busy">保存员工归属</button>
        </form>
        <h3>创建员工</h3>
        <form @submit.prevent="createEmployee"><input v-model="newEmployee.name" placeholder="员工姓名" required /><select v-model="newEmployee.role"><option value="总部">总部</option><option value="店长">店长</option><option value="正式员工">正式员工</option><option value="契约工">契约工</option></select><select v-if="newEmployee.role !== '总部'" v-model.number="newEmployee.store_id"><option v-for="store in scope.stores.filter((item) => item.is_active)" :key="store.id" :value="store.id">{{ store.store_no }} {{ store.name }}</option></select><select v-if="newEmployee.role !== '总部'" v-model="newEmployee.department_id"><option :value="null">无部门（仅店长）</option><option v-for="department in activeDepartments" :key="department.id" :value="department.id">{{ department.name }}</option></select><button :disabled="busy">创建员工</button></form>
      </section>
    </div>
  </section>
</template>

<style scoped>
.company-page { max-width: 1300px; margin: 0 auto; padding: 32px 20px; color: var(--text-primary, #e9f0e8); }
.company-page header small { color: #b7ec51; letter-spacing: .2em; }.company-page h1 { font-size: 2.5rem; margin: 8px 0; }
.company-grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(320px,1fr)); gap: 18px; margin-top: 25px; }
.company-card { background: var(--surface, #171b1d); border: 1px solid #59625955; border-radius: 15px; padding: 20px; }
.company-card h2 { margin-top: 0; }.company-card h3 { margin-top: 28px; }
.company-card form { display: flex; flex-direction: column; gap: 10px; margin: 14px 0; }
.company-card input,.company-card select { padding: 10px; border-radius: 8px; border: 1px solid #7776; background: var(--surface, #171b1d); color: inherit; }
.company-card button { padding: 8px 12px; border: 0; border-radius: 8px; background: #b7ec51; color: #17210b; cursor: pointer; }
.company-card button:disabled { opacity: .5; }.company-card p { border-bottom: 1px solid #7774; padding-bottom: 7px; }
.company-error { color: #fb7979; }.company-success { color: #80d876; }
</style>
