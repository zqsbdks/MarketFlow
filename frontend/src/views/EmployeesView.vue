<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { KeyRound, Plus, Search, UserRoundCheck, Users } from '@lucide/vue'

import {
  createEmployee,
  getDepartments,
  getEmployees,
  resetEmployeePassword,
  updateEmployeeStatus,
} from '../api'
import { getErrorMessage } from '../api/http'
import ModalPanel from '../components/ModalPanel.vue'
import PageHeader from '../components/PageHeader.vue'
import { useAuthStore } from '../stores/auth'
import type { CreatedEmployee, Department, EmployeeListItem, EmployeeRole } from '../types/api'

const authStore = useAuthStore()
const employees = ref<EmployeeListItem[]>([])
const departments = ref<Department[]>([])
const page = ref(1)
const total = ref(0)
const totalPages = ref(0)
const departmentId = ref<number | ''>('')
const role = ref<EmployeeRole | ''>('')
const activeState = ref<'' | 'true' | 'false'>('')
const createOpen = ref(false)
const credentialOpen = ref(false)
const credential = ref<CreatedEmployee | null>(null)
const form = ref<{ name: string; role: EmployeeRole; department_id: number | null }>({
  name: '',
  role: '正式员工',
  department_id: null,
})
const loading = ref(false)
const error = ref('')

async function loadEmployees() {
  loading.value = true
  error.value = ''
  try {
    const result = await getEmployees({
      page: page.value,
      page_size: 10,
      department_id: departmentId.value || undefined,
      role: role.value || undefined,
      is_active: activeState.value || undefined,
    })
    employees.value = result.items
    total.value = result.total
    totalPages.value = result.total_pages
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

async function submitCreate() {
  error.value = ''
  try {
    const payload = { ...form.value }
    if (payload.role === '店长') payload.department_id = null
    credential.value = await createEmployee(payload)
    createOpen.value = false
    credentialOpen.value = true
    form.value = { name: '', role: '正式员工', department_id: null }
    await loadEmployees()
  } catch (reason) {
    error.value = getErrorMessage(reason)
  }
}

async function toggleStatus(item: EmployeeListItem) {
  if (!window.confirm(`确定要${item.is_active ? '停用' : '启用'} ${item.name} 的账号吗？`)) return
  try {
    await updateEmployeeStatus(item.id, !item.is_active)
    await loadEmployees()
  } catch (reason) {
    error.value = getErrorMessage(reason)
  }
}

async function resetPassword(item: EmployeeListItem) {
  if (!window.confirm(`确定重置 ${item.name} 的密码吗？`)) return
  try {
    credential.value = await resetEmployeePassword(item.id)
    credentialOpen.value = true
  } catch (reason) {
    error.value = getErrorMessage(reason)
  }
}

function applyFilters() {
  page.value = 1
  loadEmployees()
}

watch(page, loadEmployees)
onMounted(async () => {
  try {
    departments.value = await getDepartments()
  } catch (reason) {
    error.value = getErrorMessage(reason)
  }
  await loadEmployees()
})
</script>

<template>
  <div>
    <PageHeader eyebrow="TEAM DIRECTORY" title="员工管理" description="创建员工账号，管理启用状态与临时密码。">
      <button class="primary-button" @click="createOpen = true"><Plus :size="18" />创建员工</button>
    </PageHeader>

    <section class="panel filter-panel">
      <div class="filter-label"><Search :size="17" /><span>筛选</span></div>
      <select v-model="departmentId" @change="applyFilters"><option value="">全部部门</option><option v-for="item in departments" :key="item.id" :value="item.id">{{ item.name }}</option></select>
      <select v-model="role" @change="applyFilters"><option value="">全部角色</option><option value="店长">店长</option><option value="正式员工">正式员工</option><option value="契约工">契约工</option></select>
      <select v-model="activeState" @change="applyFilters"><option value="">全部状态</option><option value="true">已启用</option><option value="false">已停用</option></select>
      <span class="record-count push-right"><Users :size="17" />共 {{ total }} 名员工</span>
    </section>

    <p v-if="error" class="alert error">{{ error }}</p>
    <section class="panel table-panel">
      <div class="table-wrap">
        <table>
          <thead><tr><th>员工</th><th>编号</th><th>角色</th><th>所属部门</th><th>账号状态</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="item in employees" :key="item.id"><td><div class="employee-cell"><span>{{ item.name.slice(0, 1) }}</span><strong>{{ item.name }}</strong></div></td><td class="mono">{{ item.employee_no }}</td><td>{{ item.role }}</td><td>{{ item.department_name || '全店' }}</td><td><span :class="['status-badge', item.is_active ? 'on_sale' : 'stopped']">{{ item.is_active ? '已启用' : '已停用' }}</span></td><td><div v-if="item.id !== authStore.employee?.id" class="row-actions"><button class="text-button" @click="resetPassword(item)"><KeyRound :size="15" />重置密码</button><button class="text-button muted" @click="toggleStatus(item)">{{ item.is_active ? '停用' : '启用' }}</button></div><span v-else class="record-count">当前账号</span></td></tr>
            <tr v-if="!loading && !employees.length"><td colspan="6" class="empty-cell">没有符合条件的员工</td></tr>
          </tbody>
        </table>
      </div>
      <div class="pagination"><span>第 {{ page }} / {{ totalPages || 1 }} 页</span><div><button :disabled="page <= 1" @click="page--">上一页</button><button :disabled="page >= totalPages" @click="page++">下一页</button></div></div>
    </section>

    <ModalPanel title="创建员工" :open="createOpen" @close="createOpen = false">
      <form class="stack-form" @submit.prevent="submitCreate">
        <label><span>员工姓名</span><input v-model="form.name" maxlength="50" required placeholder="请输入姓名" /></label>
        <label><span>员工角色</span><select v-model="form.role"><option value="正式员工">正式员工</option><option value="契约工">契约工</option><option value="店长">店长</option></select></label>
        <label v-if="form.role !== '店长'"><span>所属部门</span><select v-model="form.department_id" required><option :value="null" disabled>请选择部门</option><option v-for="item in departments" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
        <p class="form-tip">账号创建后默认使用临时密码，员工首次登录必须修改。</p>
        <button class="primary-button full"><UserRoundCheck :size="18" />确认创建</button>
      </form>
    </ModalPanel>

    <ModalPanel title="员工登录凭据" :open="credentialOpen" @close="credentialOpen = false">
      <div v-if="credential" class="credential-card"><div class="success-icon"><UserRoundCheck :size="25" /></div><p>请将以下信息安全地交给员工</p><dl><div><dt>员工编号</dt><dd>{{ credential.employee_no || `ID ${credential.id}` }}</dd></div><div><dt>临时密码</dt><dd>{{ credential.temporary_password }}</dd></div></dl><small>该员工首次登录后将被要求修改密码。</small></div>
    </ModalPanel>
  </div>
</template>
