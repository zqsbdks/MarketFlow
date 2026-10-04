<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Trash2 } from '@lucide/vue'
import { createDiscard, getDiscardRecords, getDiscardStock, previewDiscard } from '../api/inventoryDiscards'
import type { DiscardPage, DiscardPayload, DiscardPlan, DiscardReason, DiscardRecord, DiscardStock } from '../api/inventoryDiscards'
import { getDepartments } from '../api'
import { getErrorMessage } from '../api/http'
import { useAuthStore } from '../stores/auth'
import { useStoreScope } from '../stores/storeScope'
import type { Department } from '../types/api'
import { formatDateTime, formatMoney } from '../utils'
import LocalizedDateInput from './LocalizedDateInput.vue'
import ModalPanel from './ModalPanel.vue'

const emit = defineEmits<{ changed: [] }>()
const auth = useAuthStore()
const scope = useStoreScope()
const canWrite = computed(() => scope.canWriteStore && (auth.isManager || auth.employee?.role === '正式员工'))
const departments = ref<Department[]>([])
const result = ref<DiscardPage | null>(null)
const page = ref(1)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const formError = ref('')
const notice = ref('')
const open = ref(false)
const detail = ref<DiscardRecord | null>(null)
const stock = ref<DiscardStock | null>(null)
const plan = ref<DiscardPlan | null>(null)
const pending = ref<DiscardPayload | null>(null)
const filters = reactive({ product_id: '', department_id: '', reason_code: '', mode: '', start_date: '', end_date: '', all_stores: false })
let applied: Record<string, unknown> = {}
let appliedAll = false
let listGeneration = 0
const form = reactive({ product_id: '' as number | '', quantity: 1, batch_id: '' as number | '', reason_code: 'damaged' as Exclude<DiscardReason, 'expired'>, note: '' })
const reasonLabel: Record<DiscardReason, string> = { expired: '过期', damaged: '破损', spoiled: '腐败', contaminated: '污染', other: '其他' }
const formSignature = computed(() => JSON.stringify(form))
watch(formSignature, () => { plan.value = null; pending.value = null; formError.value = '' })
watch(() => form.product_id, () => { stock.value = null; form.batch_id = '' })

async function load(targetPage = page.value) {
  const generation = ++listGeneration
  loading.value = true
  error.value = ''
  try {
    const data = await getDiscardRecords({ ...applied, page: targetPage, page_size: 20 }, appliedAll)
    if (generation !== listGeneration) return
    if (data.total_pages && targetPage > data.total_pages) { await load(data.total_pages); return }
    result.value = data
    page.value = targetPage
  } catch (cause) { if (generation === listGeneration) error.value = getErrorMessage(cause) }
  finally { if (generation === listGeneration) loading.value = false }
}
function search() {
  applied = Object.fromEntries(Object.entries(filters).filter(([key, value]) => key !== 'all_stores' && value !== ''))
  appliedAll = auth.isHeadquarters && filters.all_stores
  void load(1)
}
function begin() {
  form.product_id = ''; form.quantity = 1; form.batch_id = ''; form.reason_code = 'damaged'; form.note = ''
  stock.value = null; plan.value = null; pending.value = null; formError.value = ''; notice.value = ''; open.value = true
}
async function lookup() {
  if (!form.product_id || busy.value) return
  busy.value = true; formError.value = ''; plan.value = null; pending.value = null
  const productId = form.product_id
  try {
    const data = await getDiscardStock(productId)
    if (productId === form.product_id) stock.value = data
  } catch (cause) { formError.value = getErrorMessage(cause) }
  finally { busy.value = false }
}
async function prepare() {
  if (!stock.value || busy.value) return
  if (form.reason_code === 'other' && !form.note.trim()) { formError.value = '其他原因必须填写说明'; return }
  busy.value = true; formError.value = ''
  const signature = formSignature.value
  const payload: DiscardPayload = {
    product_id: stock.value.product_id, quantity: form.quantity, batch_id: form.batch_id || undefined,
    reason_code: form.reason_code, note: form.note.trim() || undefined, request_id: pending.value?.request_id ?? crypto.randomUUID(),
  }
  try {
    const data = await previewDiscard({ product_id: payload.product_id, quantity: payload.quantity, batch_id: payload.batch_id })
    if (signature === formSignature.value) { pending.value = payload; plan.value = data }
  } catch (cause) { formError.value = getErrorMessage(cause) }
  finally { busy.value = false }
}
async function submit() {
  if (!pending.value || busy.value || !canWrite.value) return
  busy.value = true; formError.value = ''
  try {
    await createDiscard(pending.value)
    open.value = false; pending.value = null; plan.value = null
    notice.value = '商品废弃完成，库存已同步扣减'
    emit('changed')
    await load()
  } catch (cause) { formError.value = getErrorMessage(cause) }
  finally { busy.value = false }
}
watch(() => scope.selectedId, () => {
  open.value = false; detail.value = null; pending.value = null; plan.value = null; stock.value = null
  void load(1)
})
onMounted(async () => {
  try { departments.value = await getDepartments() } catch (cause) { error.value = getErrorMessage(cause) }
  await load()
})
</script>

<template>
  <section class="discard-section">
    <div class="discard-heading">
      <div><h2>商品废弃</h2><p class="muted">过期库存每天自动废弃；破损、腐败等情况由员工手动处理。</p></div>
      <button v-if="canWrite" class="primary-button" @click="begin"><Trash2 :size="16" />手动废弃</button>
    </div>
    <p class="form-tip">自动废弃会扣减系统库存，实际商品仍需从货架取走。</p>
    <form class="panel discard-filters" @submit.prevent="search">
      <label><span>商品ID</span><input v-model="filters.product_id" type="number" min="1" /></label>
      <label><span>部门</span><select v-model="filters.department_id"><option value="">全部部门</option><option v-for="item in departments" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
      <label><span>废弃原因</span><select v-model="filters.reason_code"><option value="">全部原因</option><option v-for="(label, code) in reasonLabel" :key="code" :value="code">{{ label }}</option></select></label>
      <label><span>处理方式</span><select v-model="filters.mode"><option value="">全部方式</option><option value="automatic">自动废弃</option><option value="manual">手动废弃</option></select></label>
      <label><span>开始日期</span><LocalizedDateInput v-model="filters.start_date" /></label>
      <label><span>结束日期</span><LocalizedDateInput v-model="filters.end_date" /></label>
      <label v-if="auth.isHeadquarters" class="discard-checkbox"><input v-model="filters.all_stores" type="checkbox" /><span>全公司汇总</span></label>
      <button class="primary-button" :disabled="loading">查询</button>
    </form>
    <p v-if="error" class="alert error">{{ error }}</p><p v-if="notice" class="alert success">{{ notice }}</p>
    <div v-if="result" class="discard-summary">
      <div class="panel"><span>废弃记录数</span><strong>{{ result.total }}</strong></div>
      <div class="panel"><span>废弃数量</span><strong>{{ result.total_quantity }}</strong></div>
      <div class="panel"><span>损耗成本</span><strong>{{ formatMoney(result.total_cost) }}</strong></div>
    </div>
    <section class="panel table-panel" :aria-busy="loading">
      <div class="table-wrap"><table>
        <thead><tr><th>时间</th><th>商品</th><th>门店 / 部门</th><th>废弃数量</th><th>损耗成本</th><th>废弃原因</th><th>操作人</th><th></th></tr></thead>
        <tbody>
          <tr v-for="row in result?.items" :key="row.id">
            <td>{{ formatDateTime(row.created_at) }}<small class="block">{{ row.employee_id === null ? '自动废弃' : '手动废弃' }}</small></td>
            <td><strong data-no-translate>{{ row.product_name }}</strong><small class="block" data-no-translate>{{ row.product_no }} · ID {{ row.product_id }}</small></td>
            <td><span data-no-translate>{{ scope.stores.find(s => s.id === row.store_id)?.name || row.store_id }}</span><small class="block">{{ row.department_name }}</small></td>
            <td>{{ row.quantity }}</td><td>{{ formatMoney(row.total_cost) }}</td><td>{{ reasonLabel[row.reason_code] }}</td>
            <td><span v-if="row.employee_name" data-no-translate>{{ row.employee_name }}</span><span v-else>系统</span></td>
            <td><button class="text-button" @click="detail = row">查看详情</button></td>
          </tr>
          <tr v-if="loading && !result"><td colspan="8" class="empty-cell">加载中</td></tr>
          <tr v-else-if="!result?.items.length"><td colspan="8" class="empty-cell">没有符合条件的废弃记录</td></tr>
        </tbody>
      </table></div>
      <div class="pagination"><span>第 {{ page }} / {{ result?.total_pages || 1 }} 页</span><div><button :disabled="loading || page <= 1" @click="load(page - 1)">上一页</button><button :disabled="loading || page >= (result?.total_pages || 0)" @click="load(page + 1)">下一页</button></div></div>
    </section>

    <ModalPanel title="手动废弃商品" :open="open" @close="!busy && (open = false)">
      <form class="stack-form" @submit.prevent="prepare">
        <p v-if="formError" class="alert error">{{ formError }}</p>
        <label><span>商品ID</span><div class="discard-lookup"><input v-model.number="form.product_id" type="number" min="1" required :disabled="busy" aria-label="商品ID" /><button type="button" class="secondary-button" :disabled="busy || !form.product_id" @click="lookup">查询商品</button></div></label>
        <div v-if="stock" class="discard-stock"><strong data-no-translate>{{ stock.product_name }}</strong><p>{{ stock.department_name }} · <span>可处理库存</span>: {{ stock.available_quantity }}</p></div>
        <template v-if="stock">
          <label><span>废弃数量</span><input v-model.number="form.quantity" type="number" min="1" :max="stock.available_quantity" step="1" required :disabled="busy" /></label>
          <label><span>扣减批次</span><select v-model="form.batch_id" :disabled="busy"><option value="">自动分配（最早到期优先）</option><option v-for="batch in stock.batches" :key="batch.batch_id" :value="batch.batch_id" data-no-translate>{{ batch.batch_no }} · {{ batch.expiration_date || '—' }} · {{ batch.remaining_quantity }}</option></select></label>
          <label><span>废弃原因</span><select v-model="form.reason_code" :disabled="busy"><option value="damaged">破损</option><option value="spoiled">腐败</option><option value="contaminated">污染</option><option value="other">其他</option></select></label>
          <label><span>补充说明</span><textarea v-model="form.note" maxlength="255" :required="form.reason_code === 'other'" :disabled="busy" /></label>
          <p class="form-tip">能识别实际批次时请选择该批次；无法识别时按最早到期批次分配。</p>
          <button class="primary-button" :disabled="busy || stock.available_quantity === 0">预览扣减方案</button>
        </template>
      </form>
      <div v-if="plan" class="discard-preview">
        <h3>确认废弃</h3><p><span>损耗成本</span>: {{ formatMoney(plan.total_cost) }}</p>
        <ul class="discard-allocation"><li v-for="item in plan.items" :key="item.batch_id"><strong data-no-translate>{{ item.batch_no }}</strong><span><span>废弃数量</span>: {{ item.quantity }} · {{ item.before_quantity }} → {{ item.after_quantity }}</span></li></ul>
        <p class="form-tip">提交时会重新检查库存；库存不足时不会扣减。</p>
        <button class="danger-button" :disabled="busy" @click="submit">确认废弃</button>
      </div>
    </ModalPanel>
    <ModalPanel title="废弃记录详情" :open="!!detail" @close="detail = null">
      <div v-if="detail" class="stack-form">
        <h3 data-no-translate>{{ detail.product_name }}</h3>
        <p>{{ reasonLabel[detail.reason_code] }} · {{ formatDateTime(detail.created_at) }}</p>
        <p v-if="detail.note" data-no-translate>{{ detail.note }}</p>
        <p><span>损耗成本</span>: {{ formatMoney(detail.total_cost) }}</p>
        <ul class="discard-allocation"><li v-for="item in detail.items" :key="item.batch_id"><strong data-no-translate>{{ item.batch_no }}</strong><span><span>废弃数量</span>: {{ item.quantity }} · {{ item.before_quantity }} → {{ item.after_quantity }}</span><span>{{ formatMoney(item.unit_cost) }} × {{ item.quantity }} = {{ formatMoney(item.total_cost) }}</span></li></ul>
      </div>
    </ModalPanel>
  </section>
</template>

<style scoped>
.discard-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:12px}.discard-heading h2{margin:0}.discard-heading p{margin:8px 0}.discard-filters{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,145px),1fr));gap:12px;padding:18px;margin:18px 0;align-items:end}.discard-filters label{display:flex;flex-direction:column;gap:7px;min-width:0}.discard-filters input,.discard-filters select{width:100%;min-width:0}.discard-filters .discard-checkbox{flex-direction:row;align-items:center;align-self:center}.discard-checkbox input{width:auto}.discard-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:18px}.discard-summary>div{padding:18px;display:flex;flex-direction:column;gap:10px;min-width:0}.discard-summary strong{font-size:24px;overflow-wrap:anywhere}.discard-lookup{display:flex;gap:10px}.discard-lookup input{min-width:0;flex:1}.discard-stock{border:1px solid var(--line);border-radius:10px;padding:14px}.discard-preview{margin-top:20px;border-top:1px solid var(--line);padding-top:16px}.discard-allocation{list-style:none;padding:0;display:grid;gap:12px}.discard-allocation li{display:flex;flex-direction:column;gap:6px;padding:12px;border:1px solid var(--line);border-radius:9px;overflow-wrap:anywhere}.block{display:block;color:var(--muted);margin-top:4px}.danger-button{padding:10px 16px;border:1px solid #ff7c68;background:rgba(255,124,104,.1);color:#ff7c68;border-radius:9px;font-weight:700}textarea{min-height:80px;resize:vertical;background:var(--paper);color:var(--ink);border:1px solid var(--line);border-radius:9px;padding:10px}.danger-button:disabled{opacity:.5}@media(max-width:600px){.discard-summary{grid-template-columns:1fr}.discard-lookup{flex-wrap:wrap}.discard-lookup>*{flex:1 1 100%}}
</style>
