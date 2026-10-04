<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { http, unwrap, getErrorMessage } from '../api/http'
import type { ApiResponse, Department } from '../types/api'
import { getDepartments } from '../api'
import { useAuthStore } from '../stores/auth'
import { createDefaultRange, formatMoney } from '../utils'
import LocalizedDateInput from './LocalizedDateInput.vue'

interface Group { key: string; name: string; quantity: number; cost: string; cost_share: string }
interface Analysis { record_count: number; quantity: number; cost: string; reasons: Group[]; departments: Group[]; stores: Group[] }
const auth = useAuthStore()
const range = createDefaultRange()
const start = ref(range.start.slice(0, 10))
const end = ref(range.end.slice(0, 10))
const departmentId = ref<number | ''>('')
const allStores = ref(false)
const departments = ref<Department[]>([])
const result = ref<Analysis | null>(null)
const loading = ref(false)
const error = ref('')
const appliedScope = ref(false)
const appliedRange = ref('')
async function load() {
  if (loading.value) return
  if (!start.value || !end.value || start.value > end.value) { error.value = '开始日期不能晚于结束日期'; return }
  loading.value = true
  error.value = ''
  try {
    const response = await http.get<ApiResponse<Analysis>>('/reports/discard-analysis', {
      params: { start_date: start.value, end_date: end.value, department_id: departmentId.value || undefined },
      headers: allStores.value && auth.isHeadquarters ? { 'X-Store-ID': 'all' } : undefined,
    })
    result.value = unwrap(response.data)
    appliedScope.value = allStores.value
    appliedRange.value = `${start.value} ~ ${end.value}`
  } catch (reason) { error.value = getErrorMessage(reason); result.value = null }
  finally { loading.value = false }
}
onMounted(async () => {
  try { departments.value = await getDepartments() } catch (reason) { error.value = getErrorMessage(reason) }
  await load()
})
</script>

<template>
  <section class="panel loss-panel">
    <div class="panel-heading"><h2>废弃损耗分析</h2></div>
    <p class="muted">按废弃处理日期统计完整当天，金额使用批次进货成本；原因占比按损耗成本计算。</p>
    <p class="muted">废弃损耗单独展示，销售毛利润未扣除废弃成本。</p>
    <div class="loss-filters">
      <LocalizedDateInput v-model="start" type="date" aria-label="开始日期" :disabled="loading" />
      <span>至</span>
      <LocalizedDateInput v-model="end" type="date" aria-label="结束日期" :disabled="loading" />
      <select v-model="departmentId" aria-label="部门" :disabled="loading"><option value="">全部部门</option><option v-for="item in departments" :key="item.id" :value="item.id">{{ item.name }}</option></select>
      <label v-if="auth.isHeadquarters"><input v-model="allStores" type="checkbox" :disabled="loading" />全公司汇总</label>
      <button class="primary-button" :disabled="loading" @click="load">{{ loading ? '正在分析…' : '生成分析' }}</button>
    </div>
    <p v-if="error" class="alert error">{{ error }}</p>
    <template v-if="result">
      <p class="muted"><span>{{ appliedScope ? '全公司汇总' : '当前门店' }}</span> · <span data-no-translate>{{ appliedRange }}</span></p>
      <div class="loss-summary">
        <div><span>损耗成本</span><strong>{{ formatMoney(result.cost) }}</strong></div>
        <div><span>废弃数量</span><strong>{{ result.quantity }}</strong></div>
        <div><span>废弃记录数</span><strong>{{ result.record_count }}</strong></div>
      </div>
      <p v-if="!result.record_count" class="empty-row">所选日期内暂无废弃记录</p>
      <div v-else class="loss-groups">
        <article v-for="group in [{ title: '废弃原因占比', items: result.reasons, literal: false }, { title: '部门损耗对比', items: result.departments, literal: false }, ...(auth.isHeadquarters ? [{ title: '门店损耗对比', items: result.stores, literal: true }] : [])]" :key="group.title">
          <h3>{{ group.title }}</h3>
          <div class="table-scroll"><table class="data-table"><thead><tr><th>名称</th><th>废弃数量</th><th>损耗成本</th><th>成本占比</th></tr></thead>
            <tbody><tr v-for="item in group.items" :key="item.key"><td :data-no-translate="group.literal ? '' : undefined">{{ item.name }}</td><td>{{ item.quantity }}</td><td>{{ formatMoney(item.cost) }}</td><td><div class="share-value">{{ item.cost_share }}%<meter min="0" max="100" :value="Number(item.cost_share)" :aria-label="item.name" /></div></td></tr></tbody>
          </table></div>
        </article>
      </div>
    </template>
  </section>
</template>

<style scoped>
.loss-panel { padding: 24px; min-width: 0; }
.muted { color: var(--muted); line-height: 1.6; }
.loss-filters { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin: 22px 0; }
.loss-filters label { display: flex; align-items: center; gap: 8px; }
.loss-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 16px; margin: 22px 0; }
.loss-summary > div { padding: 18px; border: 1px solid var(--line); border-radius: 10px; min-width: 0; }
.loss-summary span { display: block; color: var(--muted); margin-bottom: 12px; }
.loss-summary strong { font-size: 24px; overflow-wrap: anywhere; }
.loss-groups { display: grid; gap: 24px; }
.loss-groups > article { min-width: 0; }
.table-scroll { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; }
th, td { padding: 12px; text-align: left; border-bottom: 1px solid var(--line); white-space: nowrap; }
.share-value { display: flex; align-items: center; gap: 10px; }
meter { width: 90px; accent-color: var(--green); }
@media (max-width: 600px) { .loss-panel { padding: 16px; } .loss-filters > select, .loss-filters > button { width: 100%; } }
</style>
