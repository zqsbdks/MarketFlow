<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { saveMinimumStock, savePurchasePlan, getPurchasePlanning } from '../api'
import { getErrorMessage } from '../api/http'
import type { Department, PurchasePlanning, PurchasePlanningDay, PurchasePlanningItem } from '../types/api'
import { displayLocale } from '../utils'
import { isPurchaseDayLocked } from '../utils/purchaseOrdering'
import ModalPanel from './ModalPanel.vue'
import { translate } from '../i18n'
import type { QuantitySaveResult } from '../api'

const confirmation = ref<{ item: PurchasePlanningItem; date: string; amount: number; check: QuantitySaveResult } | null>(null)
const returnButton = ref<HTMLButtonElement>()
let answerConfirmation: ((answer: boolean) => void) | undefined
function finishConfirmation(answer: boolean) {
  confirmation.value = null
  answerConfirmation?.(answer)
  answerConfirmation = undefined
}
onUnmounted(() => finishConfirmation(false))
async function checkedSave(save: (token?: string) => Promise<QuantitySaveResult>, item: PurchasePlanningItem, date: string, amount: number) {
  // HTTP成功不等于已保存：后端可能返回saved=false的确认挑战。
  // 用户接受后才携带签名重试；过期挑战会重新展示，取消不写入异常值。
  let result = await save()
  while (result.confirmation_required) {
    confirmation.value = { item, date, amount, check: result }
    const answer = new Promise<boolean>(resolve => { answerConfirmation = resolve })
    await nextTick(); returnButton.value?.focus()
    const accepted = await answer
    if (!accepted) return false
    result = await save(result.confirmation_token)
  }
  return true
}
const reasonLabels: Record<string, string> = {
  far_above_reference: '数量明显超过正常需求',
  possible_extra_zero: '可能多输入了一个0',
  possible_repeated_key: '可能重复按键',
}

const props = defineProps<{ departments: Department[]; ownDepartmentId: number | null; isManager: boolean }>()
const emit = defineEmits<{ created: [] }>()
const departmentId = ref(props.isManager ? props.departments[0]?.id || 0 : props.ownDepartmentId || 0)
const planning = ref<PurchasePlanning | null>(null)
const quantities = ref<Record<string, number>>({})
// 输入草稿独立保存，定时重绘及其他单元格保存后的刷新不能覆盖未提交输入。
const drafts = ref<Record<string, string>>({})
const inputMethods = ref<Record<string, 'keyboard' | 'stepper'>>({})
function markPointer(key: string, event: PointerEvent) {
  // 原生number输入框右侧为加减控制区；之后的键盘或粘贴事件会重新标为keyboard。
  const bounds = (event.target as HTMLInputElement).getBoundingClientRect()
  inputMethods.value[key] = event.clientX >= bounds.right - 20 ? 'stepper' : 'keyboard'
}
function markInput(key: string, event: KeyboardEvent) {
  // 方向键递增递减不属于误按重复数字，普通输入/删除恢复键盘检查规则。
  if (event.key === 'ArrowUp' || event.key === 'ArrowDown') inputMethods.value[key] = 'stepper'
  else if (event.key.length === 1 || event.key === 'Backspace' || event.key === 'Delete') inputMethods.value[key] = 'keyboard'
}
function editDraft(key: string, value: string) {
  // 保留字符串才能区分空输入与0；这里仅更新草稿，不触发后台保存。
  drafts.value[key] = value
  saved.value = false
}
const keyword = ref('')
const supplier = ref('')
const display = ref<'all' | 'selected' | 'expiring'>('all')
const loading = ref(false)
const saving = ref(false)
const error = ref('')
let saveQueue: Promise<void> = Promise.resolve()
const pendingSaves = ref(0)
const saved = ref(false)
const confirmedQuantities = ref<Record<string, number>>({})
const now = ref(new Date())
let clock: ReturnType<typeof setInterval> | undefined
onMounted(() => { clock = setInterval(() => { now.value = new Date() }, 1_000) })
onUnmounted(() => { if (clock) clearInterval(clock) })

const suppliers = computed(() => [...new Set(planning.value?.items.map((item) => item.supplier_name) || [])])
const rows = computed(() => (planning.value?.items || []).filter((item) => {
  if (display.value === 'selected' && !item.days.some((day) => quantity(item, day.date) > 0)) return false
  if (display.value === 'expiring' && item.near_expiry_stock_quantity === 0) return false
  if (supplier.value && item.supplier_name !== supplier.value) return false
  if (keyword.value && !`${item.name} ${item.supplier_name}`.toLowerCase().includes(keyword.value.toLowerCase())) return false
  return true
}))

function quantity(item: PurchasePlanningItem, date: string) { return quantities.value[`${date}:${item.supplier_product_id}`] || 0 }
function highAutomaticQuantity(item: PurchasePlanningItem, day: PurchasePlanningDay) {
  // 仅渲染橘红提示：不修改数量、不发请求、不影响截止任务。
  // 取预测与上周同日实际销量较大值，避免单周高销量时过度提醒。
  const recentSales = Math.max(day.forecast_sales, day.last_week_sales)
  return !day.is_manual && drafts.value[`${day.date}:${item.supplier_product_id}`] === undefined
    && day.planned_quantity >= 50 && day.planned_quantity > recentSales * 5
}
function dayLocked(date: string) {
  return isPurchaseDayLocked(date, now.value)
}
function setQuantity(item: PurchasePlanningItem, date: string, value: number | null, input?: HTMLInputElement) {
  // 结束编辑后才进入队列，避免5→50→500输入过程中提交中间数字。
  // 队列按顺序保存每次替换量，确认取消或网络失败恢复已成功保存的量。
  if (dayLocked(date)) return
  if (value !== null && (!Number.isInteger(value) || value < 0 || value > 1000000)) {
    error.value = '请输入0至1000000之间的整数'; input?.focus(); return
  }
  const key = `${date}:${item.supplier_product_id}`
  const inputMethod = inputMethods.value[key] || 'keyboard'
  delete drafts.value[key]
  const amount = value === null ? null : Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0
  quantities.value[key] = amount ?? item.days.find(day => day.date === date)?.suggested_quantity ?? 0
  const department = departmentId.value
  pendingSaves.value++
  saving.value = true
  saved.value = false
  saveQueue = saveQueue.then(async () => {
    try {
      const accepted = await checkedSave(token => savePurchasePlan({ department_id: department, arrival_date: date, supplier_product_id: item.supplier_product_id, quantity: amount, ...(inputMethod === 'stepper' ? { input_method: inputMethod } : {}), ...(token ? { confirmation_token: token } : {}) }), item, date, amount ?? 0)
      if (!accepted) {
        quantities.value[key] = confirmedQuantities.value[key] || 0
        await nextTick()
        input?.focus(); input?.select()
        return
      }
      // 使用本次实际提交量，不把后来在同一格输入的草稿误记为已保存。
      if (departmentId.value === department) confirmedQuantities.value[key] = amount ?? quantities.value[key] ?? 0
      error.value = ''
      saved.value = true
    } catch (cause) {
      if (departmentId.value === department && (amount === null || quantities.value[key] === amount)) quantities.value[key] = confirmedQuantities.value[key] || 0
      error.value = getErrorMessage(cause)
      saved.value = false
    } finally {
      pendingSaves.value--
      saving.value = pendingSaves.value > 0
      if (!saving.value && saved.value && departmentId.value === department) await loadPlanning()
    }
  })
}
function setMinimumStock(item: PurchasePlanningItem, value: number, input?: HTMLInputElement) {
  // 保底库存属于供应目录设置，独立于某一天计划；保存后刷新所有受影响的建议日期。
  if (!Number.isInteger(value) || value < 0 || value > 1000000) {
    error.value = '请输入0至1000000之间的整数'; input?.focus(); return
  }
  const amount = Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0
  const inputMethod = inputMethods.value[`minimum:${item.supplier_product_id}`] || 'keyboard'
  delete drafts.value[`minimum:${item.supplier_product_id}`]
  const department = departmentId.value
  const previous = item.minimum_stock
  item.minimum_stock = amount
  pendingSaves.value++
  saving.value = true
  saved.value = false
  saveQueue = saveQueue.then(async () => {
    try {
      const accepted = await checkedSave(token => saveMinimumStock({department_id: department, supplier_product_id: item.supplier_product_id, minimum_stock: amount, ...(inputMethod === 'stepper' ? { input_method: inputMethod } : {}), ...(token ? { confirmation_token: token } : {})}), item, '', amount)
      if (!accepted) { item.minimum_stock = previous; await nextTick(); input?.focus(); input?.select(); return }
      error.value = ''
      saved.value = true
    } catch (cause) {
      item.minimum_stock = previous
      error.value = getErrorMessage(cause)
      saved.value = false
    } finally {
      pendingSaves.value--
      saving.value = pendingSaves.value > 0
      if (!saving.value && saved.value && departmentId.value === department) await loadPlanning()
    }
  })
}
function dateHeading(value: string) {
  const date = new Date(`${value}T12:00:00+09:00`)
  return `${value.slice(5)} (${new Intl.DateTimeFormat(displayLocale(), { weekday: 'short', timeZone: 'Asia/Tokyo' }).format(date)})`
}
async function loadPlanning() {
  // 服务端数量更新已保存状态，drafts保持独立，不能因其他格子保存或时钟刷新丢失输入。
  if (!departmentId.value) { planning.value = null; return }
  loading.value = true
  error.value = ''
  try {
    planning.value = await getPurchasePlanning(departmentId.value)
    quantities.value = Object.fromEntries(planning.value.items.flatMap((item) => item.days.map((day) => [`${day.date}:${item.supplier_product_id}`, day.planned_quantity || 0])))
    confirmedQuantities.value = { ...quantities.value }
  } catch (cause) { error.value = getErrorMessage(cause) }
  finally { loading.value = false }
}
watch(departmentId, () => { drafts.value = {}; void loadPlanning() }, { immediate: true })
watch(() => (planning.value?.days || []).map(dayLocked).join(','), (value, previous) => {
  // 仅在截止状态发生变化时重新读取计划；时钟每秒重绘不是每秒请求后端。
  if (previous && value !== previous && !saving.value && !loading.value) {
    void loadPlanning()
    emit('created')
  }
})

</script>

<template>
  <ModalPanel :open="!!confirmation" :title="translate('请确认异常数量')" @close="finishConfirmation(false)">
    <div v-if="confirmation" class="quantity-confirmation" @keydown.esc.stop.prevent="finishConfirmation(false)">
      <p data-no-translate>{{ confirmation.item.name }}</p>
      <p v-if="confirmation.date"><span>到货日期</span>：{{ confirmation.date }}</p>
      <p><span>{{ confirmation.date ? '订货数' : '保底库存' }}</span>：<strong>{{ confirmation.amount }}</strong></p>
      <p><span>参考数量</span>：{{ confirmation.check.reference }} · <span>修改前数量</span>：{{ confirmation.check.previous }}</p>
      <ul><li v-for="reason in confirmation.check.reasons" :key="reason">{{ reasonLabels[reason] || reason }}</li></ul>
      <p>确认前不会保存该数量，请检查是否输入正确。</p>
      <div class="confirmation-actions"><button ref="returnButton" type="button" @click="finishConfirmation(false)">返回修改</button><button type="button" @click="finishConfirmation(true)">确认使用此数量</button></div>
    </div>
  </ModalPanel>
  <div class="planner" :inert="!!confirmation">
    <div class="planner-top">
      <label>进货部门<select v-model.number="departmentId" :disabled="!isManager || saving"><option :value="0" disabled>请选择</option><option v-for="item in departments.filter((row) => isManager || row.id === ownDepartmentId)" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
      <small>默认两天后；从到货日起显示七天。到货日前两天的 12:00 截止订货（日本时间）。</small>
    </div>
    <div class="planner-filters">
      <button v-for="option in ([['all', '全部商品'], ['selected', '只看已选'], ['expiring', '只看临期']] as const)" :key="option[0]" type="button" :class="{ active: display === option[0] }" @click="display = option[0]">{{ option[1] }}</button>
      <input v-model="keyword" placeholder="搜索商品或供应商" />
      <select v-model="supplier"><option value="">全部供应商</option><option v-for="name in suppliers" :key="name">{{ name }}</option></select>
    </div>
    <p v-if="error" class="alert error">{{ error }}</p>
    <div class="planner-scroll">
      <table class="planner-table">
        <thead><tr><th>商品名</th><th>供应商</th><th v-if="planning?.previous_arrival_date" class="arrival-reference">{{ dateHeading(planning.previous_arrival_date) }}<small class="block">到货量（只读）</small></th><th v-for="day in planning?.days || []" :key="day" :class="{ 'locked-day': dayLocked(day) }">{{ dateHeading(day) }}<small v-if="dayLocked(day)" class="block">已截止</small></th><th class="minimum-stock-heading">保底库存</th><th>可售库存</th><th>订货当天临期数量</th></tr></thead>
        <tbody>
          <tr v-for="item in rows" :key="item.supplier_product_id">
            <td><strong data-no-translate>{{ item.name }}</strong></td><td data-no-translate>{{ item.supplier_name }}</td>
            <td v-if="planning?.previous_arrival_date" class="day-cell arrival-reference"><strong>{{ item.previous_expected_quantity || 0 }} 件</strong><small>待到货</small><small v-if="item.previous_received_quantity">已签收 {{ item.previous_received_quantity }}</small></td>
            <td v-for="day in item.days" :key="day.date" class="day-cell" :class="{ 'locked-day': dayLocked(day.date) }"><input type="number" min="0" step="1" :class="{ 'high-auto-quantity': highAutomaticQuantity(item, day) }" :title="highAutomaticQuantity(item, day) ? translate('自动建议明显超过近期销量；仍会按时提交。') : ''" :disabled="loading || dayLocked(day.date)" :value="drafts[`${day.date}:${item.supplier_product_id}`] ?? (quantity(item, day.date) || '')" @pointerdown="markPointer(`${day.date}:${item.supplier_product_id}`, $event)" @keydown="markInput(`${day.date}:${item.supplier_product_id}`, $event)" @paste="inputMethods[`${day.date}:${item.supplier_product_id}`] = 'keyboard'" @input="editDraft(`${day.date}:${item.supplier_product_id}`, ($event.target as HTMLInputElement).value)" :placeholder="dayLocked(day.date) ? '截止' : '订货数'" :aria-label="`${item.name} ${day.date}订货数量`" @blur="drafts[`${day.date}:${item.supplier_product_id}`] !== undefined && setQuantity(item, day.date, Number(($event.target as HTMLInputElement).value), $event.target as HTMLInputElement)" @keydown.enter="($event.target as HTMLInputElement).blur()" /><small v-if="!dayLocked(day.date)">{{ day.is_manual ? '人工调整' : '自动建议' }}</small><button v-if="day.is_manual && !dayLocked(day.date)" class="restore-auto" type="button" @click="setQuantity(item, day.date, null)">恢复自动建议</button><small v-if="day.expected_quantity">预计到货 {{ day.expected_quantity }}</small><small v-if="day.received_quantity">已签收 {{ day.received_quantity }}</small><span class="last-sales">{{ day.last_week_sales }}</span><small>上周同曜日售出</small></td>
            <td class="minimum-stock-cell"><input type="number" min="0" step="1" :value="drafts[`minimum:${item.supplier_product_id}`] ?? item.minimum_stock" @pointerdown="markPointer(`minimum:${item.supplier_product_id}`, $event)" @keydown="markInput(`minimum:${item.supplier_product_id}`, $event)" @paste="inputMethods[`minimum:${item.supplier_product_id}`] = 'keyboard'" @input="editDraft(`minimum:${item.supplier_product_id}`, ($event.target as HTMLInputElement).value)" :disabled="loading" :aria-label="`${item.name} 保底库存`" @blur="drafts[`minimum:${item.supplier_product_id}`] !== undefined && setMinimumStock(item, Number(($event.target as HTMLInputElement).value), $event.target as HTMLInputElement)" @keydown.enter="($event.target as HTMLInputElement).blur()" /></td><td>{{ item.saleable_stock }} 件</td><td :class="{ warning: item.near_expiry_stock_quantity > 0 }">{{ item.near_expiry_stock_quantity }} 件</td>
          </tr>
          <tr v-if="!loading && !rows.length"><td :colspan="planning?.previous_arrival_date ? 13 : 12" class="empty-cell">没有符合条件的供应商商品</td></tr>
        </tbody>
      </table>
    </div>
    <p class="planner-note">系统自动计算订货量；人工修改（包括填零）优先，点击恢复自动建议可重新自动计算。保底库存默认0，表示预计销售后希望保留的数量，库存充足时不订货。</p>
    <div class="planner-bottom"><span role="status">{{ saving ? '正在保存订货计划…' : error ? '保存失败，请重新填写' : saved ? '订货计划已保存' : '修改数量后自动保存' }}</span></div>
    <small>每天日本时间12:00锁定两天后的订货计划，并自动生成进货单；截止前可修改，无需手动提交。</small>
  </div>
</template>

<style scoped>
.planner-table .day-cell input.high-auto-quantity{color:#e06435;border-color:#e06435;background:rgba(224,100,53,.1);font-weight:800}
.quantity-confirmation{display:grid;gap:12px}.confirmation-actions{display:flex;gap:12px;flex-wrap:wrap}.confirmation-actions button{padding:10px 16px;border:1px solid var(--line);border-radius:8px;background:var(--paper);color:var(--ink)}.confirmation-actions button:last-child{background:var(--green)}
.minimum-stock-cell input{width:76px}.restore-auto{display:block;border:0;background:transparent;color:var(--green);font-size:11px;padding:4px 0;white-space:normal;text-align:left}
.planner-table .arrival-reference{background:var(--panel);min-width:100px}.arrival-reference strong{color:var(--ink)}.arrival-reference small{color:var(--muted)}
.planner{display:grid;gap:16px;color:var(--ink)}.planner-top,.planner-filters,.planner-bottom{display:flex;align-items:end;gap:12px;flex-wrap:wrap}.planner-top label{display:grid;gap:6px}.planner-top small{color:var(--muted)}.planner-filters{align-items:center}.planner-filters button{padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--paper);color:var(--ink)}.planner-filters button.active{background:var(--green);color:#101508}.planner input,.planner select{padding:9px;border:1px solid var(--line);border-radius:8px;background:var(--paper);color:var(--ink)}.planner-filters input{flex:1;min-width:180px}.planner-scroll{max-height:55vh;overflow:auto;border:1px solid var(--line)}.planner-table{border-collapse:collapse;min-width:1150px;width:100%;color:var(--ink);font-size:13px}.planner-table th,.planner-table td{border:1px solid var(--line);padding:8px;min-width:85px;text-align:left;vertical-align:middle}.planner-table th{position:sticky;top:0;background:var(--paper);z-index:1}.planner-table td:first-child strong{color:var(--ink);font-size:13px}.planner-table th:first-child,.planner-table td:first-child{min-width:150px}.planner-table th:nth-child(2),.planner-table td:nth-child(2){min-width:120px}.planner-table tbody tr:hover{background:rgba(130,165,80,.12)}.planner-table tbody tr:hover td,.planner-table tbody tr:hover td strong{color:var(--ink)}.day-cell span,.day-cell small{display:block}.day-cell small{font-size:11px;color:var(--muted)}.day-cell input{width:76px;padding:5px;margin-bottom:4px}.day-cell.locked-day,.planner-table th.locked-day{background:#343940;color:#f3f5f0}.day-cell.locked-day small{color:#c6ccc6}.day-cell.locked-day input{background:#555b62;color:#fff;border-color:#697078;cursor:not-allowed}.last-sales{color:#2067ca;font-weight:800;margin-top:5px}.warning{color:#d26633;font-weight:700}.planner-note{font-size:12px;color:var(--muted)}.planner-bottom{justify-content:flex-end;font-weight:700}
</style>
