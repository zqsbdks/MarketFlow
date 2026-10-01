<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  BadgePercent,
  CalendarClock,
  CirclePause,
  CirclePlay,
  Pencil,
  Plus,
  Search,
  Tags,
  Trash2,
} from '@lucide/vue'

import {
  addDiscountRuleProducts,
  clearDiscountRuleProducts,
  clearDiscountRules,
  createDiscountRule,
  deleteDiscountRule,
  deleteDiscountRuleProduct,
  getDepartments,
  getDiscountRule,
  getDiscountRuleProducts,
  getDiscountRules,
  getProducts,
  updateDiscountRule,
  updateDiscountRuleStatus,
} from '../api'
import { getErrorMessage } from '../api/http'
import { confirmTranslated, language, promptTranslated, translate } from '../i18n'
import ModalPanel from '../components/ModalPanel.vue'
import PageHeader from '../components/PageHeader.vue'
import { useAuthStore } from '../stores/auth'
import type {
  Department,
  DiscountComputedStatus,
  DiscountRule,
  DiscountRulePayload,
  DiscountRuleProduct,
  DiscountScheduleType,
  DiscountType,
  ProductListItem,
} from '../types/api'
import { apiDateTime, formatDateTime, formatMoney } from '../utils'

const auth = useAuthStore()

// region 页面列表、筛选与权限状态
const rules = ref<DiscountRule[]>([])
const departments = ref<Department[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const successMessage = ref('')
const keyword = ref('')
const departmentId = ref<number | ''>('')
const discountType = ref<DiscountType | ''>('')
const scheduleType = ref<DiscountScheduleType | ''>('')
const computedStatus = ref<DiscountComputedStatus | ''>('')
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const totalPages = ref(0)

// 店长可以管理全部部门，正式员工只管理本部门；契约工仅查看。
const canMaintain = computed(
  () => auth.employee?.role === '店长' || auth.employee?.role === '正式员工',
)
function canMaintainRule(rule: DiscountRule | null) {
  if (rule === null) return false
  if (auth.isManager) return true
  return (
    auth.employee?.role === '正式员工' &&
    auth.employee.department?.id === rule.department_id
  )
}
const availableDepartments = computed(() => {
  if (auth.isManager) return departments.value
  const employeeDepartment = auth.employee?.department
  return employeeDepartment ? [employeeDepartment] : []
})
const activeCount = computed(
  () => rules.value.filter((item) => item.computed_status === 'active').length,
)
const scheduledCount = computed(
  () => rules.value.filter((item) => item.computed_status === 'scheduled').length,
)
const disabledCount = computed(
  () => rules.value.filter((item) => item.computed_status === 'disabled').length,
)

async function loadRules() {
  loading.value = true
  error.value = ''
  try {
    const result = await getDiscountRules({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
      department_id: departmentId.value || undefined,
      discount_type: discountType.value || undefined,
      schedule_type: scheduleType.value || undefined,
      computed_status: computedStatus.value || undefined,
    })
    rules.value = result.items
    total.value = result.total
    totalPages.value = result.total_pages
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  loadRules()
}

function resetFilters() {
  keyword.value = ''
  departmentId.value = ''
  discountType.value = ''
  scheduleType.value = ''
  computedStatus.value = ''
  search()
}

watch(page, loadRules)
// endregion

// region 折扣规则表单与创建修改
interface RuleFormState {
  department_id: number | ''
  name: string
  discount_type: DiscountType
  discount_value: number
  schedule_type: DiscountScheduleType
  starts_at: string
  ends_at: string
  daily_start_time: string
  daily_end_time: string
  weekdays: number[]
  is_active: boolean
  reason: string
}

function emptyRuleForm(): RuleFormState {
  return {
    department_id: availableDepartments.value[0]?.id ?? '',
    name: '',
    discount_type: 'percentage',
    discount_value: 0.9,
    schedule_type: 'once',
    starts_at: '',
    ends_at: '',
    daily_start_time: '09:00',
    daily_end_time: '21:00',
    weekdays: [],
    is_active: true,
    reason: '',
  }
}

const form = reactive<RuleFormState>(emptyRuleForm())
const formMode = ref<'create' | 'edit'>('create')
const formOpen = ref(false)
const editingRuleId = ref<number | null>(null)

function buildRulePayload(includeDepartment: boolean): DiscountRulePayload {
  const payload: DiscountRulePayload = {
    name: form.name,
    discount_type: form.discount_type,
    discount_value: Number(form.discount_value),
    schedule_type: form.schedule_type,
    starts_at: form.schedule_type === 'once' ? (apiDateTime(form.starts_at) ?? null) : null,
    ends_at: form.schedule_type === 'once' ? (apiDateTime(form.ends_at) ?? null) : null,
    daily_start_time: form.schedule_type === 'once' ? null : form.daily_start_time || null,
    daily_end_time: form.schedule_type === 'once' ? null : form.daily_end_time || null,
    weekdays: form.schedule_type === 'weekly' ? form.weekdays : null,
  }
  if (includeDepartment) {
    payload.department_id = Number(form.department_id)
    payload.is_active = form.is_active
  } else {
    payload.reason = form.reason || undefined
  }
  return payload
}

function openCreateForm() {
  formMode.value = 'create'
  editingRuleId.value = null
  Object.assign(form, emptyRuleForm())
  formOpen.value = true
}

async function openEditForm(rule: DiscountRule) {
  error.value = ''
  try {
    const detail = await getDiscountRule(rule.id)
    formMode.value = 'edit'
    editingRuleId.value = detail.id
    Object.assign(form, {
      department_id: detail.department_id,
      name: detail.name,
      discount_type: detail.discount_type,
      discount_value: Number(detail.discount_value),
      schedule_type: detail.schedule_type,
      starts_at: detail.starts_at?.slice(0, 16) ?? '',
      ends_at: detail.ends_at?.slice(0, 16) ?? '',
      daily_start_time: detail.daily_start_time?.slice(0, 5) ?? '09:00',
      daily_end_time: detail.daily_end_time?.slice(0, 5) ?? '21:00',
      weekdays: detail.weekdays ?? [],
      is_active: detail.is_active,
      reason: '',
    })
    formOpen.value = true
  } catch (reason) {
    error.value = getErrorMessage(reason)
  }
}

async function submitRule() {
  if (form.schedule_type === 'weekly' && form.weekdays.length === 0) {
    error.value = '每周循环规则至少需要选择一个星期。'
    return
  }
  saving.value = true
  error.value = ''
  try {
    if (formMode.value === 'create') {
      await createDiscountRule(buildRulePayload(true))
      successMessage.value = '折扣规则创建成功，可以继续添加适用商品。'
    } else if (editingRuleId.value !== null) {
      await updateDiscountRule(editingRuleId.value, buildRulePayload(false))
      successMessage.value = '折扣规则修改成功。'
    }
    formOpen.value = false
    await loadRules()
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    saving.value = false
  }
}
// endregion

// region 详情、启停与删除
const detailOpen = ref(false)
const selectedRule = ref<DiscountRule | null>(null)

async function openDetail(rule: DiscountRule) {
  error.value = ''
  try {
    selectedRule.value = await getDiscountRule(rule.id)
    detailOpen.value = true
  } catch (reason) {
    error.value = getErrorMessage(reason)
  }
}

async function toggleRule(rule: DiscountRule) {
  const actionName = rule.is_active ? '关闭' : '开启'
  const reason = promptTranslated(`${actionName}“${rule.name}”的理由（可不填）`, '')
  if (reason === null) return
  saving.value = true
  error.value = ''
  try {
    await updateDiscountRuleStatus(rule.id, !rule.is_active, reason)
    successMessage.value = `已${actionName}折扣规则。`
    await loadRules()
  } catch (cause) {
    error.value = getErrorMessage(cause)
  } finally {
    saving.value = false
  }
}

async function removeRule(rule: DiscountRule) {
  if (!confirmTranslated(`确定删除折扣规则“${rule.name}”吗？关联商品也会一起移除。`)) return
  saving.value = true
  error.value = ''
  try {
    await deleteDiscountRule(rule.id)
    successMessage.value = '折扣规则已删除。'
    await loadRules()
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    saving.value = false
  }
}

async function removeAllRules() {
  if (!confirmTranslated('确定清空权限范围内的全部折扣规则吗？此操作不可撤销。')) return
  saving.value = true
  error.value = ''
  try {
    await clearDiscountRules()
    successMessage.value = '折扣规则已清空。'
    await loadRules()
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    saving.value = false
  }
}
// endregion

// region 折扣适用商品管理
const productsOpen = ref(false)
const productRule = ref<DiscountRule | null>(null)
const ruleProducts = ref<DiscountRuleProduct[]>([])
const candidateProducts = ref<ProductListItem[]>([])
const selectedProductIds = ref<number[]>([])
const productKeyword = ref('')
const productLoading = ref(false)

const filteredCandidateProducts = computed(() => {
  const joinedProductIds = new Set(ruleProducts.value.map((item) => item.product_id))
  const normalizedKeyword = productKeyword.value.trim().toLowerCase()
  return candidateProducts.value.filter((item) => {
    if (joinedProductIds.has(item.id)) return false
    if (!normalizedKeyword) return true
    return `${item.product_no} ${item.name}`.toLowerCase().includes(normalizedKeyword)
  })
})

async function loadProductManagement(rule: DiscountRule) {
  productLoading.value = true
  error.value = ''
  try {
    const [joinedResult, candidateResult] = await Promise.all([
      getDiscountRuleProducts(rule.id, { page: 1, page_size: 100 }),
      getProducts({ page: 1, page_size: 100, department_id: rule.department_id }),
    ])
    ruleProducts.value = joinedResult.items
    candidateProducts.value = candidateResult.items
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    productLoading.value = false
  }
}

async function openProducts(rule: DiscountRule) {
  productRule.value = rule
  selectedProductIds.value = []
  productKeyword.value = ''
  productsOpen.value = true
  await loadProductManagement(rule)
}

async function addSelectedProducts() {
  if (productRule.value === null || selectedProductIds.value.length === 0) return
  saving.value = true
  error.value = ''
  try {
    await addDiscountRuleProducts(productRule.value.id, selectedProductIds.value)
    successMessage.value = `已添加 ${selectedProductIds.value.length} 件折扣商品。`
    selectedProductIds.value = []
    await loadProductManagement(productRule.value)
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    saving.value = false
  }
}

async function removeProduct(item: DiscountRuleProduct) {
  if (productRule.value === null) return
  if (!confirmTranslated(`确定将“${item.product_name}”移出当前折扣吗？`)) return
  try {
    await deleteDiscountRuleProduct(productRule.value.id, item.product_id)
    await loadProductManagement(productRule.value)
  } catch (reason) {
    error.value = getErrorMessage(reason)
  }
}

async function removeAllProducts() {
  if (productRule.value === null || ruleProducts.value.length === 0) return
  if (!confirmTranslated('确定移除这条规则下的全部商品吗？')) return
  try {
    await clearDiscountRuleProducts(productRule.value.id)
    await loadProductManagement(productRule.value)
  } catch (reason) {
    error.value = getErrorMessage(reason)
  }
}
// endregion

// region 展示格式
const statusLabels: Record<DiscountComputedStatus, string> = {
  disabled: '已停用',
  scheduled: '待生效',
  active: '正在生效',
  ended: '已结束',
}
const weekdayLabels = computed(() => {
  if (language.value === 'ja') return ['月', '火', '水', '木', '金', '土', '日']
  if (language.value === 'en') return ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
  return ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
})

function weekdayText(day: number): string {
  const label = weekdayLabels.value[day - 1] || ''
  return language.value === 'ja' ? `${label}曜` : label
}

function formatDiscount(rule: DiscountRule) {
  const value = Number(rule.discount_value)
  if (rule.discount_type === 'percentage') return translate(`${Math.round(value * 100)}% 售价`)
  if (rule.discount_type === 'amount_off') return translate(`每件减 ${formatMoney(value)}`)
  return translate(`固定价 ${formatMoney(value)}`)
}

function formatSchedule(rule: DiscountRule) {
  if (rule.schedule_type === 'once') {
    if (!rule.starts_at || !rule.ends_at) return '单次时间未设置'
    return `${formatDateTime(rule.starts_at)} ～ ${formatDateTime(rule.ends_at)}`
  }
  const timeRange = `${rule.daily_start_time?.slice(0, 5)} ～ ${rule.daily_end_time?.slice(0, 5)}`
  if (rule.schedule_type === 'daily') return translate(`每天 ${timeRange}`)
  const weekdays = (rule.weekdays ?? []).map(weekdayText).join(language.value === 'en' ? ', ' : '、')
  return `${weekdays} ${timeRange}`
}

onMounted(async () => {
  try {
    departments.value = await getDepartments()
    if (!auth.isManager && auth.employee?.department) {
      departmentId.value = auth.employee.department.id
    }
  } catch (reason) {
    error.value = getErrorMessage(reason)
  }
  await loadRules()
})
// endregion
</script>

<template>
  <div>
    <PageHeader
      eyebrow="DISCOUNT CONTROL"
      title="折扣管理"
      description="配置单次、每日或每周折扣，并管理每条规则适用的商品。"
    >
      <div v-if="canMaintain" class="header-actions">
        <button class="secondary-button danger-button" type="button" :disabled="saving" @click="removeAllRules">
          <Trash2 :size="16" />清空规则
        </button>
        <button class="primary-button" type="button" @click="openCreateForm">
          <Plus :size="17" />新建折扣
        </button>
      </div>
    </PageHeader>

    <section class="stat-grid three">
      <article class="stat-card tone-green"><div class="stat-icon"><BadgePercent :size="18" /></div><p>本页正在生效</p><strong>{{ activeCount }} 条</strong><span>当前时间满足执行条件</span></article>
      <article class="stat-card tone-blue"><div class="stat-icon"><CalendarClock :size="18" /></div><p>本页待生效</p><strong>{{ scheduledCount }} 条</strong><span>已开启但当前不在时段内</span></article>
      <article class="stat-card tone-orange"><div class="stat-icon"><CirclePause :size="18" /></div><p>本页已停用</p><strong>{{ disabledCount }} 条</strong><span>由员工手动关闭</span></article>
    </section>

    <section class="panel filter-panel discount-filter">
      <div class="search-field"><Search :size="18" /><input v-model="keyword" placeholder="搜索折扣名称" @keyup.enter="search" /></div>
      <select v-model="departmentId"><option value="">全部部门</option><option v-for="item in departments" :key="item.id" :value="item.id">{{ item.name }}</option></select>
      <select v-model="discountType"><option value="">全部折扣方式</option><option value="percentage">比例折扣</option><option value="amount_off">固定立减</option><option value="fixed_price">固定价格</option></select>
      <select v-model="scheduleType"><option value="">全部执行周期</option><option value="once">单次</option><option value="daily">每日</option><option value="weekly">每周</option></select>
      <select v-model="computedStatus"><option value="">全部状态</option><option value="active">正在生效</option><option value="scheduled">待生效</option><option value="ended">已结束</option><option value="disabled">已停用</option></select>
      <button class="primary-button" type="button" @click="search">查询</button>
      <button class="secondary-button" type="button" @click="resetFilters">重置</button>
    </section>

    <p v-if="error" class="alert error">{{ error }}</p>
    <p v-if="successMessage" class="alert success">{{ successMessage }}</p>

    <section class="panel table-panel">
      <div class="table-wrap">
        <table>
          <thead><tr><th>规则名称</th><th>部门</th><th>折扣力度</th><th>执行时间</th><th>动态状态</th><th>创建人</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="rule in rules" :key="rule.id">
              <td><button class="rule-name" type="button" @click="openDetail(rule)"><strong>{{ rule.name }}</strong><small>#{{ rule.id }}</small></button></td>
              <td>{{ rule.department_name }}</td>
              <td><strong class="discount-value">{{ formatDiscount(rule) }}</strong></td>
              <td><span class="schedule-text">{{ formatSchedule(rule) }}</span></td>
              <td><span :class="['discount-status', rule.computed_status]">{{ statusLabels[rule.computed_status] }}</span></td>
              <td><strong class="plain">{{ rule.created_by_name }}</strong><small class="block">{{ formatDateTime(rule.created_at) }}</small></td>
              <td><div class="row-actions"><button class="text-button" type="button" @click="openProducts(rule)"><Tags :size="14" />商品</button><template v-if="canMaintainRule(rule)"><button class="text-button" type="button" @click="openEditForm(rule)"><Pencil :size="14" />修改</button><button class="text-button muted" type="button" :disabled="saving" @click="toggleRule(rule)"><CirclePause v-if="rule.is_active" :size="14" /><CirclePlay v-else :size="14" />{{ rule.is_active ? '关闭' : '开启' }}</button><button class="text-button danger-text" type="button" @click="removeRule(rule)"><Trash2 :size="14" />删除</button></template></div></td>
            </tr>
            <tr v-if="!loading && !rules.length"><td colspan="7" class="empty-cell">没有找到符合条件的折扣规则</td></tr>
          </tbody>
        </table>
      </div>
      <div class="pagination"><span>共 {{ total }} 条 · 第 {{ page }} / {{ totalPages || 1 }} 页</span><div><button :disabled="page <= 1" @click="page--">上一页</button><button :disabled="page >= totalPages" @click="page++">下一页</button></div></div>
    </section>

    <ModalPanel :title="formMode === 'create' ? '新建折扣规则' : '修改折扣规则'" :open="formOpen" @close="formOpen = false">
      <form class="rule-form" @submit.prevent="submitRule">
        <label>所属部门<select v-model.number="form.department_id" required :disabled="formMode === 'edit'"><option value="">请选择部门</option><option v-for="item in availableDepartments" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
        <label>规则名称<input v-model="form.name" maxlength="100" required /></label>
        <div class="form-pair"><label>折扣方式<select v-model="form.discount_type"><option value="percentage">比例折扣</option><option value="amount_off">固定立减</option><option value="fixed_price">固定价格</option></select></label><label>折扣数值<input v-model.number="form.discount_value" type="number" min="0.0001" step="0.01" required /></label></div>
        <small v-if="form.discount_type === 'percentage'" class="form-tip">比例填写 0～1 之间的小数，例如 0.8 表示按原价的 80% 销售。</small>
        <label>执行周期<select v-model="form.schedule_type"><option value="once">单次活动</option><option value="daily">每日循环</option><option value="weekly">每周循环</option></select></label>
        <div v-if="form.schedule_type === 'once'" class="form-pair"><label>开始时间<input v-model="form.starts_at" type="datetime-local" required /></label><label>结束时间<input v-model="form.ends_at" type="datetime-local" required /></label></div>
        <div v-else class="form-pair"><label>每天开始<input v-model="form.daily_start_time" type="time" required /></label><label>每天结束<input v-model="form.daily_end_time" type="time" required /></label></div>
        <fieldset v-if="form.schedule_type === 'weekly'" class="weekday-field"><legend>执行星期</legend><label v-for="(label, index) in weekdayLabels" :key="index"><input v-model="form.weekdays" type="checkbox" :value="index + 1" />{{ weekdayText(index + 1) }}</label></fieldset>
        <label v-if="formMode === 'create'" class="switch-field"><input v-model="form.is_active" type="checkbox" />创建后立即开启</label>
        <label v-else>修改理由（可选）<input v-model="form.reason" maxlength="255" /></label>
        <button class="primary-button" :disabled="saving">{{ saving ? '正在保存…' : '保存折扣规则' }}</button>
      </form>
    </ModalPanel>

    <ModalPanel title="折扣规则详情" :open="detailOpen" @close="detailOpen = false">
      <div v-if="selectedRule" class="detail-sheet"><div class="detail-hero"><span><BadgePercent /></span><div><p>{{ selectedRule.department_name }}</p><h3>{{ selectedRule.name }}</h3></div></div><dl><div><dt>折扣力度</dt><dd>{{ formatDiscount(selectedRule) }}</dd></div><div><dt>当前状态</dt><dd>{{ statusLabels[selectedRule.computed_status] }}</dd></div><div><dt>执行时间</dt><dd>{{ formatSchedule(selectedRule) }}</dd></div><div><dt>人工开关</dt><dd>{{ selectedRule.is_active ? '已开启' : '已关闭' }}</dd></div><div><dt>创建人</dt><dd>{{ selectedRule.created_by_name }}</dd></div><div><dt>更新时间</dt><dd>{{ formatDateTime(selectedRule.updated_at) }}</dd></div></dl></div>
    </ModalPanel>

    <ModalPanel :title="productRule ? `${productRule.name} · 适用商品` : '适用商品'" :open="productsOpen" @close="productsOpen = false">
      <div class="product-manager"><div class="manager-heading"><div><strong>已添加 {{ ruleProducts.length }} 件商品</strong><small>只有这些商品会使用当前折扣</small></div><button v-if="canMaintainRule(productRule) && ruleProducts.length" class="text-button danger-text" type="button" @click="removeAllProducts">全部移除</button></div><div v-if="ruleProducts.length" class="joined-products"><div v-for="item in ruleProducts" :key="item.scope_id"><div><strong>{{ item.product_name }}</strong><small>{{ item.product_no }} · {{ item.category_name }}</small></div><span><s>{{ formatMoney(item.original_price) }}</s>{{ formatMoney(item.discounted_price) }}</span><button v-if="canMaintainRule(productRule)" class="icon-button" type="button" title="移除商品" @click="removeProduct(item)"><Trash2 :size="15" /></button></div></div><p v-else class="empty-hint">尚未添加商品，这条折扣暂时不会作用于任何商品。</p><template v-if="canMaintainRule(productRule)"><div class="candidate-heading"><strong>添加商品</strong><div class="search-field"><Search :size="16" /><input v-model="productKeyword" placeholder="搜索商品编号或名称" /></div></div><div v-if="productLoading" class="empty-hint">正在加载商品…</div><div v-else class="candidate-products"><label v-for="item in filteredCandidateProducts" :key="item.id"><input v-model="selectedProductIds" type="checkbox" :value="item.id" /><span><strong>{{ item.name }}</strong><small>{{ item.product_no }} · {{ item.category_name }} · {{ formatMoney(item.sale_price) }}</small></span></label><p v-if="!filteredCandidateProducts.length" class="empty-hint">没有其他可以添加的商品。</p></div><button class="primary-button" type="button" :disabled="saving || !selectedProductIds.length" @click="addSelectedProducts">添加选中的 {{ selectedProductIds.length }} 件商品</button></template></div>
    </ModalPanel>
  </div>
</template>

<style scoped>
.header-actions,.row-actions,.manager-heading,.candidate-heading{display:flex;align-items:center;gap:9px}.header-actions{justify-content:flex-end}.discount-filter{flex-wrap:wrap}.discount-filter .search-field{flex:1 1 230px}.rule-name{display:grid;gap:4px;padding:0;color:inherit;text-align:left;background:none;border:0;cursor:pointer}.rule-name small,.schedule-text,.manager-heading small,.candidate-products small,.joined-products small{color:var(--muted)}.discount-value{color:var(--green)}.discount-status{display:inline-flex;padding:5px 9px;border-radius:20px;font-size:10px;font-weight:800}.discount-status.active{color:#c8ff5a;background:#25321d}.discount-status.scheduled{color:#9facff;background:#252a45}.discount-status.ended{color:#ffd86b;background:#3a321d}.discount-status.disabled{color:#9da3ad;background:#292c32}.row-actions{flex-wrap:wrap;min-width:260px}.row-actions button{display:inline-flex;align-items:center;gap:4px}.danger-text{color:#ff907b}.danger-button{color:#ff9a87}.alert.success{margin-bottom:14px;padding:12px 15px;color:#c8ff5a;background:#1d2918;border:1px solid #445d30;border-radius:9px}.rule-form{display:grid;gap:15px}.rule-form label{display:grid;gap:7px;color:var(--muted)}.rule-form input,.rule-form select{width:100%;padding:11px;border:1px solid var(--line);border-radius:9px}.form-pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}.weekday-field{display:flex;flex-wrap:wrap;gap:9px;padding:12px;border:1px solid var(--line);border-radius:9px}.weekday-field legend{padding:0 6px;color:var(--muted)}.weekday-field label,.switch-field{display:flex!important;grid-template-columns:none;align-items:center;gap:5px}.weekday-field input,.switch-field input{width:auto}.product-manager{display:grid;gap:18px}.manager-heading{justify-content:space-between}.manager-heading>div{display:grid;gap:4px}.joined-products{display:grid;border:1px solid var(--line);border-radius:10px;overflow:hidden}.joined-products>div{display:grid;grid-template-columns:1fr auto 36px;align-items:center;gap:12px;padding:12px;border-bottom:1px solid var(--line)}.joined-products>div:last-child{border-bottom:0}.joined-products>div>div,.candidate-products span{display:grid;gap:3px}.joined-products span{display:flex;gap:8px;align-items:center;color:var(--green);font-weight:700}.joined-products s{color:var(--muted);font-weight:400}.candidate-heading{justify-content:space-between}.candidate-heading .search-field{max-width:290px}.candidate-products{display:grid;max-height:270px;overflow:auto;border:1px solid var(--line);border-radius:10px}.candidate-products label{display:flex;align-items:center;gap:10px;padding:11px 12px;border-bottom:1px solid var(--line);cursor:pointer}.candidate-products label:last-of-type{border-bottom:0}.candidate-products input{width:auto}.empty-hint{margin:0;padding:18px;color:var(--muted);text-align:center;background:#111318;border:1px dashed var(--line);border-radius:9px}.plain{color:var(--ink)}.block{display:block;margin-top:4px}@media(max-width:900px){.row-actions{min-width:210px}}@media(max-width:700px){.header-actions,.candidate-heading{align-items:stretch;flex-direction:column}.header-actions button{width:100%}.form-pair{grid-template-columns:1fr}.joined-products>div{grid-template-columns:1fr auto}.joined-products button{grid-column:2}.candidate-heading .search-field{max-width:none;width:100%}}
</style>
