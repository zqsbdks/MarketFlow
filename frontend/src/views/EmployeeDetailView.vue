<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute } from 'vue-router'
import { ArrowLeft, Pencil, Save, UserRound } from '@lucide/vue'
import { getEmployeeDetail, updateEmployeeDetail } from '../api'
import { getErrorMessage } from '../api/http'
import PageHeader from '../components/PageHeader.vue'
import { useAuthStore } from '../stores/auth'
import type { EmployeeDetail, EmployeeDetailUpdate } from '../types/api'

const route = useRoute()
const auth = useAuthStore()
const detail = ref<EmployeeDetail | null>(null)
const loading = ref(false)
const saving = ref(false)
const editing = ref(false)
const error = ref('')
const success = ref('')
const form = ref<EmployeeDetailUpdate | null>(null)
const original = ref('')
const dirty = computed(() => editing.value && JSON.stringify(form.value) !== original.value)
const separated = computed(() => ['离职', '解雇'].includes(form.value?.employment_status || ''))
const today = new Intl.DateTimeFormat('sv-SE').format(new Date())
let loadVersion = 0

// 表单使用副本，取消编辑时不会改变正在展示的员工资料。
function beginEdit() {
  if (!detail.value) return
  const d = detail.value
  form.value = {
    gender: d.gender, birth_date: d.birth_date || '', hire_date: d.hire_date,
    phone: d.phone || '', address: d.address || '', employment_status: d.employment_status,
    separation_date: d.separation_date, separation_reason: d.separation_reason,
  }
  original.value = JSON.stringify(form.value)
  editing.value = true
  error.value = ''
  success.value = ''
}

function cancelEdit() {
  if (dirty.value && !window.confirm('放弃尚未保存的修改？')) return
  editing.value = false
  error.value = ''
}

function changeStatus() {
  if (form.value && !separated.value) {
    form.value.separation_date = null
    form.value.separation_reason = null
  }
}

async function load() {
  const version = ++loadVersion
  detail.value = null
  editing.value = false
  error.value = ''
  success.value = ''
  const id = Number(route.params.id)
  if (!Number.isSafeInteger(id) || id < 1) { error.value = '员工编号无效'; return }
  loading.value = true
  try {
    const result = await getEmployeeDetail(id)
    if (version === loadVersion) detail.value = result
  } catch (reason) {
    if (version === loadVersion) error.value = getErrorMessage(reason)
  } finally {
    if (version === loadVersion) loading.value = false
  }
}

async function save() {
  if (!form.value || !detail.value || saving.value) return
  error.value = ''
  const payload = { ...form.value, phone: form.value.phone.trim(), address: form.value.address.trim() }
  if (!payload.phone || !payload.address) { error.value = '联系电话和居住地址不能为空'; return }
  if (payload.birth_date > today || payload.birth_date > payload.hire_date) {
    error.value = '出生日期不能晚于今天或入职日期'; return
  }
  // 空日期传 null，由后端保留原离职日期或补为今天。
  payload.separation_date = separated.value ? payload.separation_date || null : null
  payload.separation_reason = separated.value ? payload.separation_reason?.trim() || null : null
  if (payload.separation_date && payload.separation_date < payload.hire_date) {
    error.value = '离职或解雇日期不能早于入职日期'; return
  }
  saving.value = true
  try {
    detail.value = await updateEmployeeDetail(detail.value.id, payload)
    editing.value = false
    success.value = '员工档案已保存'
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally { saving.value = false }
}

function confirmLeave() {
  if (saving.value) return false
  return !dirty.value || window.confirm('有尚未保存的修改，确定离开？')
}
onBeforeRouteLeave(confirmLeave)
onBeforeRouteUpdate(confirmLeave)
watch(() => route.params.id, load, { immediate: true })
// 后端时间未携带时区时按原值显示，避免额外偏移；日期字段也不转 UTC。
const displayTime = (value: string | null) => value ? value.replace('T', ' ').slice(0, 19) : '暂无记录'
</script>

<template>
  <div class="employee-profile">
    <RouterLink class="text-button back-link" :to="auth.isManager ? '/employees' : '/dashboard'"><ArrowLeft :size="16" />{{ auth.isManager ? '返回员工管理' : '返回店铺总览' }}</RouterLink>
    <PageHeader eyebrow="EMPLOYEE PROFILE" title="员工档案" description="个人资料与任职信息，一处清晰查看。">
      <button v-if="detail && auth.isManager && !editing" class="primary-button" @click="beginEdit"><Pencil :size="17" />编辑资料</button>
    </PageHeader>
    <p v-if="error" role="alert" class="alert error">{{ error }}</p>
    <p v-if="success" role="status" class="notice">{{ success }}</p>
    <section v-if="loading" class="panel loading-state" role="status">正在读取员工档案…</section>
    <section v-else-if="!detail" class="panel loading-state"><p>暂时无法查看该员工档案。</p><button class="text-button" @click="load">重新加载</button></section>
    <div v-else class="profile-layout">
      <aside class="panel identity-card">
        <div class="profile-avatar">{{ detail.name.slice(0, 1) }}</div>
        <p class="eyebrow">{{ detail.employee_no }}</p>
        <h2>{{ detail.name }}</h2>
        <p class="muted">{{ detail.department_name || '全店' }} · {{ detail.role }}</p>
        <span :class="['status-badge', detail.employment_status === '在职' ? 'on_sale' : 'stopped']">{{ detail.employment_status }}</span>
        <dl class="identity-facts">
          <div><dt>账号状态</dt><dd>{{ detail.is_active ? '已启用' : '已停用' }}</dd></div>
          <div><dt>入职日期</dt><dd>{{ detail.hire_date }}</dd></div>
          <div><dt>最后登录</dt><dd>{{ displayTime(detail.last_login_at) }}</dd></div>
        </dl>
        <p class="form-tip">账号启用状态与在职、休假等雇佣状态分别管理。</p>
      </aside>

      <form v-if="editing && form" class="panel details-card stack-form" @submit.prevent="save">
        <div><p class="eyebrow">EDIT PROFILE</p><h2>编辑员工资料</h2><p class="form-tip">带 * 的字段必填。姓名、部门和工种在本页仅供查看。</p></div>
        <fieldset :disabled="saving" class="edit-fields">
          <div class="field-grid">
            <label><span>性别 *</span><select v-model="form.gender" required><option>未填写</option><option>男</option><option>女</option></select></label>
            <label><span>出生日期 *</span><input v-model="form.birth_date" type="date" :max="today" required /></label>
            <label><span>入职日期 *</span><input v-model="form.hire_date" type="date" required /></label>
            <label><span>联系电话 *</span><input v-model="form.phone" type="tel" maxlength="30" required autocomplete="tel" /></label>
            <label class="wide"><span>居住地址 *</span><input v-model="form.address" maxlength="255" required autocomplete="street-address" /></label>
            <label><span>雇佣状态 *</span><select v-model="form.employment_status" required @change="changeStatus"><option>在职</option><option>休假</option><option>离职</option><option>解雇</option></select></label>
            <label v-if="separated"><span>离职或解雇日期（选填）</span><input v-model="form.separation_date" type="date" :min="form.hire_date" /></label>
            <label v-if="separated" class="wide"><span>离职或解雇原因（选填）</span><textarea v-model="form.separation_reason" rows="3" maxlength="255" /></label>
          </div>
          <p v-if="separated" class="form-tip">日期留空时，同一离职状态保留原日期；首次离职或解雇默认使用今天。</p>
          <div class="edit-actions"><button type="button" class="text-button muted" @click="cancelEdit">取消编辑</button><button type="submit" class="primary-button"><Save :size="17" />{{ saving ? '正在保存…' : '保存修改' }}</button></div>
        </fieldset>
      </form>

      <section v-else class="panel details-card">
        <p class="eyebrow">PERSONAL INFORMATION</p><h2><UserRound :size="20" />基本资料</h2>
        <dl class="detail-grid">
          <div><dt>性别</dt><dd>{{ detail.gender }}</dd></div>
          <div><dt>出生日期</dt><dd>{{ detail.birth_date || '未填写' }}</dd></div>
          <div><dt>联系电话</dt><dd>{{ detail.phone || '未填写' }}</dd></div>
          <div><dt>工种</dt><dd>{{ detail.role }}</dd></div>
          <div class="wide"><dt>居住地址</dt><dd>{{ detail.address || '未填写' }}</dd></div>
        </dl>
        <div class="section-divider"><p class="eyebrow">EMPLOYMENT RECORD</p><h2>任职信息</h2></div>
        <dl class="detail-grid">
          <div><dt>雇佣状态</dt><dd>{{ detail.employment_status }}</dd></div>
          <div><dt>离职或解雇日期</dt><dd>{{ detail.separation_date || '未填写' }}</dd></div>
          <div class="wide"><dt>离职或解雇原因</dt><dd>{{ detail.separation_reason || '未填写' }}</dd></div>
        </dl>
        <footer class="profile-footer"><span>档案创建 {{ displayTime(detail.created_at) }}</span><span>最近更新 {{ displayTime(detail.updated_at) }}</span></footer>
      </section>
    </div>
  </div>
</template>

<style scoped>
.back-link { display: inline-flex; margin-bottom: 24px; }
.profile-layout { display: grid; grid-template-columns: 300px minmax(0, 1fr); gap: 24px; align-items: start; }
.identity-card { padding: 32px 26px; border-top: 3px solid var(--green); }
.profile-avatar { width: 76px; height: 76px; display: grid; place-items: center; background: var(--green); color: #111; border-radius: 22px; font-size: 32px; margin-bottom: 24px; }
h2 { margin: 10px 0 16px; font-size: 23px; display: flex; align-items: center; gap: 10px; }
.identity-facts { border-top: 1px solid var(--line); margin-top: 28px; padding-top: 12px; }
.identity-facts div { margin: 20px 0; }
dt { color: var(--muted); font-size: 12px; margin-bottom: 9px; }
dd { margin: 0; overflow-wrap: anywhere; white-space: pre-wrap; }
.details-card { padding: 30px; }
.detail-grid, .field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 26px 32px; }
.detail-grid { margin: 26px 0; }
.wide { grid-column: 1 / -1; }
.section-divider { border-top: 1px solid var(--line); padding-top: 24px; margin-top: 30px; }
.profile-footer { display: flex; flex-wrap: wrap; gap: 12px 24px; border-top: 1px solid var(--line); padding-top: 22px; color: var(--muted); font-size: 12px; }
.edit-fields { border: 0; padding: 0; margin: 0; min-width: 0; }
.edit-fields:disabled { opacity: .65; }
.edit-actions { display: flex; justify-content: flex-end; gap: 24px; margin-top: 30px; }
.notice { padding: 15px 20px; color: var(--green); border: 1px solid var(--green); border-radius: 8px; }
.loading-state { padding: 48px; text-align: center; color: var(--muted); }
@media (max-width: 800px) { .profile-layout { grid-template-columns: 1fr; } .details-card { padding: 22px; } }
@media (max-width: 480px) { .field-grid, .detail-grid { grid-template-columns: 1fr; } }
</style>
