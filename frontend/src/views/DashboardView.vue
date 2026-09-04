<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { init, use, type EChartsType } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import {
  ArrowRight,
  Banknote,
  Boxes,
  CalendarDays,
  CircleDollarSign,
  ReceiptText,
  TrendingUp,
} from '@lucide/vue'

import { getDepartmentReports, getOverview, getRankings } from '../api'
import { getErrorMessage } from '../api/http'
import LoadingBlock from '../components/LoadingBlock.vue'
import PageHeader from '../components/PageHeader.vue'
import StatCard from '../components/StatCard.vue'
import type { DepartmentReport, OverviewReport, RankingItem } from '../types/api'
import { apiDateTime, createDefaultRange, formatMoney } from '../utils'

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const router = useRouter()
const defaultRange = createDefaultRange()
const startTime = ref(defaultRange.start)
const endTime = ref(defaultRange.end)
const overview = ref<OverviewReport | null>(null)
const departments = ref<DepartmentReport[]>([])
const rankings = ref<RankingItem[]>([])
const loading = ref(true)
const error = ref('')
const chartElement = ref<HTMLDivElement | null>(null)
let chart: EChartsType | null = null

const marginRate = computed(() => {
  if (!overview.value || Number(overview.value.revenue) === 0) return '0.0%'
  return `${((Number(overview.value.gross_profit) / Number(overview.value.revenue)) * 100).toFixed(1)}%`
})

async function loadDashboard() {
  loading.value = true
  error.value = ''
  const timeParams = {
    start_time: apiDateTime(startTime.value),
    end_time: apiDateTime(endTime.value),
  }
  try {
    const [overviewData, departmentData, rankingData] = await Promise.all([
      getOverview(timeParams),
      getDepartmentReports(timeParams),
      getRankings({
        start_date: apiDateTime(startTime.value),
        end_date: apiDateTime(endTime.value),
        group_by: 'product',
        sort_by: 'amount',
        sort_order: 'desc',
        page: 1,
        page_size: 5,
      }),
    ])
    overview.value = overviewData
    departments.value = departmentData
    rankings.value = rankingData.items
    await nextTick()
    renderChart()
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

function renderChart() {
  if (!chartElement.value) return
  chart ??= init(chartElement.value)
  chart.setOption({
    animationDuration: 700,
    grid: { left: 12, right: 12, top: 24, bottom: 8, containLabel: true },
    tooltip: { trigger: 'axis', valueFormatter: (value: unknown) => formatMoney(Number(value)) },
    xAxis: {
      type: 'category',
      data: departments.value.map((item) => item.department_name),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#8d929c', fontSize: 12 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#292c33' } },
      axisLabel: { color: '#737883', formatter: (value: number) => `${value / 1000}k` },
    },
    series: [
      {
        type: 'bar',
        data: departments.value.map((item) => Number(item.revenue)),
        barWidth: 28,
        itemStyle: { color: '#c8ff5a', borderRadius: [3, 3, 0, 0] },
        emphasis: { itemStyle: { color: '#7887ff' } },
      },
    ],
  })
}

function resizeChart() {
  chart?.resize()
}

onMounted(() => {
  loadDashboard()
  window.addEventListener('resize', resizeChart)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeChart)
  chart?.dispose()
})
</script>

<template>
  <div>
    <PageHeader eyebrow="STORE PULSE" title="店铺总览" description="把销售、利润与部门表现放在同一张经营地图上。">
      <div class="date-filter">
        <CalendarDays :size="17" />
        <input v-model="startTime" type="datetime-local" />
        <span>至</span>
        <input v-model="endTime" type="datetime-local" />
        <button class="secondary-button" type="button" @click="loadDashboard">更新</button>
      </div>
    </PageHeader>

    <p v-if="error" class="alert error">{{ error }}</p>
    <LoadingBlock v-if="loading && !overview" />

    <template v-else-if="overview">
      <section class="stat-grid">
        <StatCard label="营业额" :value="formatMoney(overview.revenue)" hint="所选时间范围" :icon="CircleDollarSign" tone="green" />
        <StatCard label="毛利润" :value="formatMoney(overview.gross_profit)" :hint="`毛利率 ${marginRate}`" :icon="TrendingUp" tone="orange" />
        <StatCard label="销售商品" :value="`${overview.sales_quantity} 件`" hint="累计售出数量" :icon="Boxes" tone="blue" />
        <StatCard label="销售单" :value="`${overview.sale_count} 单`" :hint="`成本 ${formatMoney(overview.sales_cost)}`" :icon="ReceiptText" tone="ink" />
      </section>

      <section class="dashboard-grid">
        <article class="panel chart-panel">
          <div class="panel-heading">
            <div><p class="eyebrow">DEPARTMENT MIX</p><h2>部门营业额对比</h2></div>
            <span class="panel-note">单位：元</span>
          </div>
          <div ref="chartElement" class="department-chart" />
          <div class="department-links">
            <button v-for="item in departments" :key="item.department_id" @click="router.push(`/departments/${item.department_id}`)">
              <span>{{ item.department_name }}</span><strong>{{ formatMoney(item.revenue) }}</strong><ArrowRight :size="15" />
            </button>
          </div>
        </article>

        <article class="panel ranking-panel">
          <div class="panel-heading">
            <div><p class="eyebrow">TOP PRODUCTS</p><h2>销售额排行</h2></div>
            <button class="text-button" @click="router.push('/products')">查看商品</button>
          </div>
          <ol class="ranking-list">
            <li v-for="item in rankings" :key="item.id">
              <span class="rank-number">{{ String(item.rank).padStart(2, '0') }}</span>
              <div><strong>{{ item.name }}</strong><small>售出 {{ item.quantity }} 件</small></div>
              <b>{{ formatMoney(item.amount) }}</b>
            </li>
            <li v-if="rankings.length === 0" class="empty-row">所选时间内暂无销售排行</li>
          </ol>
        </article>
      </section>

      <section class="insight-strip">
        <div class="insight-icon"><Banknote :size="22" /></div>
        <div><p class="eyebrow">OPERATING NOTE</p><strong>经营数字已经准备好</strong><span>点击部门卡片可以进一步查看单个部门的收入、毛利与热销商品。</span></div>
        <ArrowRight :size="20" />
      </section>
    </template>
  </div>
</template>
