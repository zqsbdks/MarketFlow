<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { createPurchase, getPurchasePlanning } from '../api'
import { getErrorMessage } from '../api/http'
import { confirmTranslated } from '../i18n'
import type { Department, PurchasePlanning, PurchasePlanningItem } from '../types/api'
import { formatMoney } from '../utils'

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
const requestIds = ref<Record<string, string>>({})
const now = ref(new Date())
let clock: ReturnType<typeof setInterval> | undefined
onMounted(() => { clock = setInterval(() => { now.value = new Date() }, 30_000) })
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
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Tokyo', hour: 'numeric', hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now.value)
  const value = (type: string) => parts.find((part) => part.type === type)?.value || ''
  const today = `${value('year')}-${value('month')}-${value('day')}`
  return date < today || (date === today && Number(value('hour')) >= 12)
}
function setQuantity(item: PurchasePlanningItem, date: string, value: number) {
  if (dayLocked(date)) return
  quantities.value[`${date}:${item.supplier_product_id}`] = Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0
  requestIds.value[date] = crypto.randomUUID()
}
function dateHeading(value: string) {
  const date = new Date(`${value}T12:00:00+09:00`)
  return `${value.slice(5)}（${new Intl.DateTimeFormat('zh-CN', { weekday: 'short', timeZone: 'Asia/Tokyo' }).format(date)}）`
}
async function loadPlanning() {
  if (!departmentId.value) { planning.value = null; return }
  loading.value = true
  error.value = ''
  try {
    planning.value = await getPurchasePlanning(departmentId.value)
    quantities.value = {}
    requestIds.value = {}
  } catch (cause) { error.value = getErrorMessage(cause) }
  finally { loading.value = false }
}
watch(departmentId, () => { void loadPlanning() }, { immediate: true })

async function submit() {
  if (!planning.value || !selected.value.length || saving.value) return
  const days = planning.value.days.filter((date) => planning.value?.items.some((item) => quantity(item, date) > 0))
  if (days.some(dayLocked)) { error.value = '有日期已过订货截止时间，请清除该日数量后重试'; return }
  if (!confirmTranslated(`确认按 ${days.length} 个到货日，提交 ${selected.value.length} 种商品、共 ${totalQuantity.value} 件吗？`)) return
  saving.value = true
  error.value = ''
  const completed: string[] = []
  try {
    for (const date of days) {
      const items = selected.value.filter((item) => quantity(item, date) > 0).map((item) => ({
        supplier_product_id: item.supplier_product_id,
        quantity: quantity(item, date),
      }))
      await createPurchase({
        client_request_id: requestIds.value[date] || crypto.randomUUID(),
        department_id: departmentId.value,
        expected_arrival_date: date,
        items,
      })
      for (const item of items) delete quantities.value[`${date}:${item.supplier_product_id}`]
      delete requestIds.value[date]
      completed.push(date)
    }
    emit('created')
  } catch (cause) {
    error.value = `${completed.length ? `已成功提交 ${completed.join('、')}；其余日期未提交。` : ''}${getErrorMessage(cause)}`
  }
  finally { saving.value = false }
}
</script>

<template>
  <div class="planner">
    <div class="planner-top">
      <label>进货部门<select v-model.number="departmentId" :disabled="!isManager"><option :value="0" disabled>请选择</option><option v-for="item in departments.filter((row) => isManager || row.id === ownDepartmentId)" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
      <small>默认两天后；从到货日起显示七天。每日格子可直接填写订货数量，当天 12:00 后锁定。</small>
    </div>
    <div class="planner-filters">
      <button v-for="option in ([['all', '全部商品'], ['selected', '只看已选'], ['expiring', '只看临期']] as const)" :key="option[0]" type="button" :class="{ active: display === option[0] }" @click="display = option[0]">{{ option[1] }}</button>
      <input v-model="keyword" placeholder="搜索商品或供应商" />
      <select v-model="supplier"><option value="">全部供应商</option><option v-for="name in suppliers" :key="name">{{ name }}</option></select>
    </div>
    <p v-if="error" class="alert error">{{ error }}</p>
    <div class="planner-scroll">
      <table class="planner-table">
        <thead><tr><th>商品名</th><th>供应商</th><th v-for="day in planning?.days || []" :key="day" :class="{ 'locked-day': dayLocked(day) }">{{ dateHeading(day) }}<small v-if="dayLocked(day)" class="block">已截止</small></th><th>可售库存</th><th>订货当天临期数量</th><th>订货金额</th></tr></thead>
        <tbody>
          <tr v-for="item in rows" :key="item.supplier_product_id">
            <td><strong>{{ item.name }}</strong></td><td>{{ item.supplier_name }}</td>
            <td v-for="day in item.days" :key="day.date" class="day-cell" :class="{ 'locked-day': dayLocked(day.date) }"><input type="number" min="0" step="1" :disabled="dayLocked(day.date)" :value="quantity(item, day.date) || ''" :placeholder="dayLocked(day.date) ? '截止' : '订货数'" :aria-label="`${item.name} ${day.date}订货数量`" @change="setQuantity(item, day.date, Number(($event.target as HTMLInputElement).value))" /><small v-if="day.expected_quantity">预计到货 {{ day.expected_quantity }}</small><small v-if="day.received_quantity">已签收 {{ day.received_quantity }}</small><span class="last-sales">{{ day.last_week_sales }}</span><small>上周同曜日售出</small></td>
            <td>{{ item.saleable_stock }} 件</td><td :class="{ warning: item.near_expiry_stock_quantity > 0 }">{{ item.near_expiry_stock_quantity }} 件</td>
            <td>{{ formatMoney(Number(item.unit_cost) * item.days.reduce((sum, day) => sum + quantity(item, day.date), 0)) }}</td>
          </tr>
          <tr v-if="!loading && !rows.length"><td :colspan="12" class="empty-cell">没有符合条件的供应商商品</td></tr>
        </tbody>
      </table>
    </div>
    <p class="planner-note">日期格上方输入本次订货数量；黑色文字为已有订单到货量，蓝色为上周同曜日销量。深灰色日期已过截止时间。</p>
    <div class="planner-bottom"><span>已选 {{ selected.length }} 种 · {{ totalQuantity }} 件 · 预计金额 {{ formatMoney(totalAmount) }}</span><button class="primary-button" :disabled="saving || loading || !selected.length" @click="submit">提交进货单</button></div>
    <small>同一日期的商品组成一张进货单；当天 12:00 后不可再订当天到货的商品。提交前会再次确认。</small>
  </div>
</template>

<style scoped>
.planner{display:grid;gap:16px;color:var(--ink)}.planner-top,.planner-filters,.planner-bottom{display:flex;align-items:end;gap:12px;flex-wrap:wrap}.planner-top label{display:grid;gap:6px}.planner-top small{color:var(--muted)}.planner-filters{align-items:center}.planner-filters button{padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--paper);color:var(--ink)}.planner-filters button.active{background:var(--green);color:#101508}.planner input,.planner select{padding:9px;border:1px solid var(--line);border-radius:8px;background:var(--paper);color:var(--ink)}.planner-filters input{flex:1;min-width:180px}.planner-scroll{max-height:55vh;overflow:auto;border:1px solid var(--line)}.planner-table{border-collapse:collapse;min-width:1150px;width:100%;color:var(--ink);font-size:13px}.planner-table th,.planner-table td{border:1px solid var(--line);padding:8px;min-width:85px;text-align:left;vertical-align:middle}.planner-table th{position:sticky;top:0;background:var(--paper);z-index:1}.planner-table td:first-child strong{color:var(--ink);font-size:13px}.planner-table th:first-child,.planner-table td:first-child{min-width:150px}.planner-table th:nth-child(2),.planner-table td:nth-child(2){min-width:120px}.planner-table tbody tr:hover{background:rgba(130,165,80,.12)}.planner-table tbody tr:hover td,.planner-table tbody tr:hover td strong{color:var(--ink)}.day-cell span,.day-cell small{display:block}.day-cell small{font-size:11px;color:var(--muted)}.day-cell input{width:76px;padding:5px;margin-bottom:4px}.day-cell.locked-day,.planner-table th.locked-day{background:#343940;color:#f3f5f0}.day-cell.locked-day small{color:#c6ccc6}.day-cell.locked-day input{background:#555b62;color:#fff;border-color:#697078;cursor:not-allowed}.last-sales{color:#2067ca;font-weight:800;margin-top:5px}.warning{color:#d26633;font-weight:700}.planner-note{font-size:12px;color:var(--muted)}.planner-bottom{justify-content:space-between;font-weight:700}
</style>
