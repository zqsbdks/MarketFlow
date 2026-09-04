<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CalendarDays, CircleDollarSign, ReceiptText, TrendingUp } from '@lucide/vue'

import { getCategories, getDepartments, getOverview, getRankings } from '../api'
import { getErrorMessage } from '../api/http'
import LoadingBlock from '../components/LoadingBlock.vue'
import PageHeader from '../components/PageHeader.vue'
import StatCard from '../components/StatCard.vue'
import type { Category, Department, OverviewReport, RankingItem } from '../types/api'
import { apiDateTime, createDefaultRange, formatMoney } from '../utils'

const route = useRoute()
const router = useRouter()
const defaultRange = createDefaultRange()
const startTime = ref(defaultRange.start)
const endTime = ref(defaultRange.end)
const departments = ref<Department[]>([])
const categories = ref<Category[]>([])
const overview = ref<OverviewReport | null>(null)
const rankings = ref<RankingItem[]>([])
const categoryId = ref<number | ''>('')
const sortBy = ref<'quantity' | 'amount'>('quantity')
const loading = ref(true)
const error = ref('')
const departmentId = computed(() => Number(route.params.id))
const currentDepartment = computed(() => departments.value.find((item) => item.id === departmentId.value))

async function load() {
  loading.value = true
  error.value = ''
  try {
    if (!departments.value.length) departments.value = await getDepartments()
    if (!categories.value.length) categories.value = await getCategories(departmentId.value)
    const [report, ranking] = await Promise.all([
      getOverview({
        department_id: departmentId.value,
        start_time: apiDateTime(startTime.value),
        end_time: apiDateTime(endTime.value),
      }),
      getRankings({
        department_id: departmentId.value,
        category_id: categoryId.value || undefined,
        start_date: apiDateTime(startTime.value),
        end_date: apiDateTime(endTime.value),
        group_by: 'product',
        sort_by: sortBy.value,
        sort_order: 'desc',
        page_size: 20,
      }),
    ])
    overview.value = report
    rankings.value = ranking.items
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

watch(
  () => route.params.id,
  async () => {
    categoryId.value = ''
    categories.value = await getCategories(departmentId.value)
    await load()
  },
)
watch([categoryId, sortBy], load)
onMounted(load)
</script>

<template>
  <div>
    <PageHeader
      eyebrow="DEPARTMENT VIEW"
      :title="currentDepartment?.name || '部门经营'"
      description="查看一个部门在所选时间内的经营结果与销售排行。"
    >
      <select :value="departmentId" @change="router.push(`/departments/${($event.target as HTMLSelectElement).value}`)">
        <option v-for="item in departments" :key="item.id" :value="item.id">{{ item.name }}</option>
      </select>
    </PageHeader>

    <div class="toolbar panel compact">
      <div class="field inline"><CalendarDays :size="17" /><input v-model="startTime" type="datetime-local" /></div>
      <span>至</span>
      <div class="field inline"><input v-model="endTime" type="datetime-local" /></div>
      <button class="secondary-button" @click="load">查询</button>
    </div>
    <p v-if="error" class="alert error">{{ error }}</p>
    <LoadingBlock v-if="loading && !overview" />

    <template v-else-if="overview">
      <section class="stat-grid three">
        <StatCard label="部门营业额" :value="formatMoney(overview.revenue)" hint="所选时间范围" :icon="CircleDollarSign" tone="green" />
        <StatCard label="部门毛利润" :value="formatMoney(overview.gross_profit)" :hint="`成本 ${formatMoney(overview.sales_cost)}`" :icon="TrendingUp" tone="orange" />
        <StatCard label="商品与订单" :value="`${overview.sales_quantity} 件`" :hint="`涉及 ${overview.sale_count} 张销售单`" :icon="ReceiptText" tone="blue" />
      </section>

      <section class="panel">
        <div class="panel-heading wrap">
          <div><p class="eyebrow">SALES RANKING</p><h2>部门销售排行</h2></div>
          <div class="segmented-controls">
            <select v-model="categoryId" aria-label="商品分类">
              <option value="">全部分类</option>
              <option v-for="category in categories" :key="category.id" :value="category.id">
                {{ category.name }}
              </option>
            </select>
            <select v-model="sortBy" aria-label="排行依据">
              <option value="quantity">按销售数量</option>
              <option value="amount">按销售金额</option>
            </select>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>排名</th><th>商品</th><th>累计数量</th><th>累计金额</th></tr></thead>
            <tbody>
              <tr v-for="item in rankings" :key="item.id"><td><span class="table-rank">{{ item.rank }}</span></td><td><strong>{{ item.name }}</strong></td><td>{{ item.quantity }} 件</td><td>{{ formatMoney(item.amount) }}</td></tr>
              <tr v-if="!rankings.length"><td colspan="4" class="empty-cell">暂无排行数据</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>
