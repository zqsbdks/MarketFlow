<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { saveMinimumStock, savePurchasePlan, getPurchasePlanning } from '../api'
import { getErrorMessage } from '../api/http'
import type { Department, PurchasePlanning, PurchasePlanningItem } from '../types/api'
import { displayLocale, formatMoney } from '../utils'
import { isPurchaseDayLocked } from '../utils/purchaseOrdering'

const props = defineProps<{ departments: Department[]; ownDepartmentId: number | null; isManager: boolean }>()
const emit = defineEmits<{ created: [] }>()
const departmentId = ref(props.isManager ? props.departments[0]?.id || 0 : props.ownDepartmentId || 0)
const planning = ref<PurchasePlanning | null>(null)
const quantities = ref<Record<string, number>>({})
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
const selected = computed(() => (planning.value?.items || []).filter((item) => item.days.some((day) => quantity(item, day.date) > 0)))
const totalQuantity = computed(() => selected.value.reduce((sum, item) => sum + item.days.reduce((daySum, day) => daySum + quantity(item, day.date), 0), 0))
const totalAmount = computed(() => selected.value.reduce((sum, item) => sum + item.days.reduce((daySum, day) => daySum + Number(item.unit_cost) * quantity(item, day.date), 0), 0))

function quantity(item: PurchasePlanningItem, date: string) { return quantities.value[`${date}:${item.supplier_product_id}`] || 0 }
function dayLocked(date: string) {
  return isPurchaseDayLocked(date, now.value)
}
function setQuantity(item: PurchasePlanningItem, date: string, value: number | null) {
  if (dayLocked(date)) return
  const key = `${date}:${item.supplier_product_id}`
  const amount = value === null ? null : Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0
  quantities.value[key] = amount ?? item.days.find(day => day.date === date)?.suggested_quantity ?? 0
  const department = departmentId.value
  pendingSaves.value++
  saving.value = true
  saved.value = false
  saveQueue = saveQueue.then(async () => {
    try {
      await savePurchasePlan({ department_id: department, arrival_date: date, supplier_product_id: item.supplier_product_id, quantity: amount })
      if (departmentId.value === department) confirmedQuantities.value[key] = quantities.value[key] || 0
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
function setMinimumStock(item: PurchasePlanningItem, value: number) {
  const amount = Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0
  const department = departmentId.value
  const previous = item.minimum_stock
  item.minimum_stock = amount
  pendingSaves.value++
  saving.value = true
  saved.value = false
  saveQueue = saveQueue.then(async () => {
    try {
      await saveMinimumStock({department_id: department, supplier_product_id: item.supplier_product_id, minimum_stock: amount})
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
watch(departmentId, () => { void loadPlanning() }, { immediate: true })
watch(() => (planning.value?.days || []).map(dayLocked).join(','), (value, previous) => {
  if (previous && value !== previous && !saving.value && !loading.value) {
    void loadPlanning()
    emit('created')
  }
})

</script>

<template>
  <div class="planner">
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
        <thead><tr><th>商品名</th><th>供应商</th><th v-if="planning?.previous_arrival_date" class="arrival-reference">{{ dateHeading(planning.previous_arrival_date) }}<small class="block">到货量（只读）</small></th><th v-for="day in planning?.days || []" :key="day" :class="{ 'locked-day': dayLocked(day) }">{{ dateHeading(day) }}<small v-if="dayLocked(day)" class="block">已截止</small></th><th class="minimum-stock-heading">保底库存</th><th>可售库存</th><th>订货当天临期数量</th><th>订货金额</th></tr></thead>
        <tbody>
          <tr v-for="item in rows" :key="item.supplier_product_id">
            <td><strong data-no-translate>{{ item.name }}</strong></td><td data-no-translate>{{ item.supplier_name }}</td>
            <td v-if="planning?.previous_arrival_date" class="day-cell arrival-reference"><strong>{{ item.previous_expected_quantity || 0 }} 件</strong><small>待到货</small><small v-if="item.previous_received_quantity">已签收 {{ item.previous_received_quantity }}</small></td>
            <td v-for="day in item.days" :key="day.date" class="day-cell" :class="{ 'locked-day': dayLocked(day.date) }"><input type="number" min="0" step="1" :disabled="loading || dayLocked(day.date)" :value="quantity(item, day.date) || ''" :placeholder="dayLocked(day.date) ? '截止' : '订货数'" :aria-label="`${item.name} ${day.date}订货数量`" @input="setQuantity(item, day.date, Number(($event.target as HTMLInputElement).value))" /><small v-if="!dayLocked(day.date)">{{ day.is_manual ? '人工调整' : '自动建议' }}</small><button v-if="day.is_manual && !dayLocked(day.date)" class="restore-auto" type="button" @click="setQuantity(item, day.date, null)">恢复自动建议</button><small v-if="day.expected_quantity">预计到货 {{ day.expected_quantity }}</small><small v-if="day.received_quantity">已签收 {{ day.received_quantity }}</small><span class="last-sales">{{ day.last_week_sales }}</span><small>上周同曜日售出</small></td>
            <td class="minimum-stock-cell"><input type="number" min="0" step="1" :value="item.minimum_stock" :disabled="loading" :aria-label="`${item.name} 保底库存`" @change="setMinimumStock(item, Number(($event.target as HTMLInputElement).value))" /></td><td>{{ item.saleable_stock }} 件</td><td :class="{ warning: item.near_expiry_stock_quantity > 0 }">{{ item.near_expiry_stock_quantity }} 件</td>
            <td>{{ formatMoney(Number(item.unit_cost) * item.days.reduce((sum, day) => sum + quantity(item, day.date), 0)) }}</td>
          </tr>
          <tr v-if="!loading && !rows.length"><td :colspan="planning?.previous_arrival_date ? 14 : 13" class="empty-cell">没有符合条件的供应商商品</td></tr>
        </tbody>
      </table>
    </div>
    <p class="planner-note">系统自动计算订货量；人工修改（包括填零）优先，点击恢复自动建议可重新自动计算。保底库存默认0，表示预计销售后希望保留的数量，库存充足时不订货。</p>
    <div class="planner-bottom"><span>已选 {{ selected.length }} 种 · {{ totalQuantity }} 件 · 预计金额 {{ formatMoney(totalAmount) }}</span><span role="status">{{ saving ? '正在保存订货计划…' : error ? '保存失败，请重新填写' : saved ? '订货计划已保存' : '修改数量后自动保存' }}</span></div>
    <small>每天日本时间12:00锁定两天后的订货计划，并自动生成进货单；截止前可修改，无需手动提交。</small>
  </div>
</template>

<style scoped>
.minimum-stock-cell input{width:76px}.restore-auto{display:block;border:0;background:transparent;color:var(--green);font-size:11px;padding:4px 0;white-space:normal;text-align:left}
.planner-table .arrival-reference{background:var(--panel);min-width:100px}.arrival-reference strong{color:var(--ink)}.arrival-reference small{color:var(--muted)}
.planner{display:grid;gap:16px;color:var(--ink)}.planner-top,.planner-filters,.planner-bottom{display:flex;align-items:end;gap:12px;flex-wrap:wrap}.planner-top label{display:grid;gap:6px}.planner-top small{color:var(--muted)}.planner-filters{align-items:center}.planner-filters button{padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--paper);color:var(--ink)}.planner-filters button.active{background:var(--green);color:#101508}.planner input,.planner select{padding:9px;border:1px solid var(--line);border-radius:8px;background:var(--paper);color:var(--ink)}.planner-filters input{flex:1;min-width:180px}.planner-scroll{max-height:55vh;overflow:auto;border:1px solid var(--line)}.planner-table{border-collapse:collapse;min-width:1150px;width:100%;color:var(--ink);font-size:13px}.planner-table th,.planner-table td{border:1px solid var(--line);padding:8px;min-width:85px;text-align:left;vertical-align:middle}.planner-table th{position:sticky;top:0;background:var(--paper);z-index:1}.planner-table td:first-child strong{color:var(--ink);font-size:13px}.planner-table th:first-child,.planner-table td:first-child{min-width:150px}.planner-table th:nth-child(2),.planner-table td:nth-child(2){min-width:120px}.planner-table tbody tr:hover{background:rgba(130,165,80,.12)}.planner-table tbody tr:hover td,.planner-table tbody tr:hover td strong{color:var(--ink)}.day-cell span,.day-cell small{display:block}.day-cell small{font-size:11px;color:var(--muted)}.day-cell input{width:76px;padding:5px;margin-bottom:4px}.day-cell.locked-day,.planner-table th.locked-day{background:#343940;color:#f3f5f0}.day-cell.locked-day small{color:#c6ccc6}.day-cell.locked-day input{background:#555b62;color:#fff;border-color:#697078;cursor:not-allowed}.last-sales{color:#2067ca;font-weight:800;margin-top:5px}.warning{color:#d26633;font-weight:700}.planner-note{font-size:12px;color:var(--muted)}.planner-bottom{justify-content:space-between;font-weight:700}
</style>
