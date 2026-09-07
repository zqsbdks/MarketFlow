<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { init, use, type EChartsType } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'

import { getDepartments, getReportAnalytics } from '../api'
import { getErrorMessage } from '../api/http'
import PageHeader from '../components/PageHeader.vue'
import type { Department, ReportAnalytics, ReportMetric } from '../types/api'
import { apiDateTime, createDefaultRange, formatDateTime, formatMoney } from '../utils'

use([BarChart, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const metricOptions: { value: ReportMetric; label: string }[] = [
  { value: 'revenue', label: '营业额' },
  { value: 'sales_cost', label: '销售成本' },
  { value: 'gross_profit', label: '毛利润' },
  { value: 'sales_quantity', label: '销售商品数量' },
  { value: 'sale_count', label: '销售单数' },
  { value: 'average_sale_amount', label: '平均每单金额' },
  { value: 'average_sale_quantity', label: '平均每单件数' },
  { value: 'gross_profit_margin', label: '毛利率' },
  { value: 'revenue_growth_rate', label: '营业额增长率' },
  { value: 'gross_profit_growth_rate', label: '毛利润增长率' },
  { value: 'department_revenue_share', label: '部门销售额占比' },
  { value: 'sales_trend', label: '营业趋势' },
]

const defaultRange = createDefaultRange()
const startTime = ref(defaultRange.start)
const endTime = ref(defaultRange.end)
const departmentId = ref<number | ''>('')
const interval = ref<'hour' | 'day' | 'month' | 'year'>('day')
const displayMode = ref<'table' | 'chart' | 'both'>('both')
const selectedMetrics = ref<ReportMetric[]>(metricOptions.map((item) => item.value))
const departments = ref<Department[]>([])
const analytics = ref<ReportAnalytics | null>(null)
const loading = ref(false)
const error = ref('')
const trendChartElement = ref<HTMLDivElement | null>(null)
const shareChartElement = ref<HTMLDivElement | null>(null)
const trafficChartElement = ref<HTMLDivElement | null>(null)
const efficiencyChartElement = ref<HTMLDivElement | null>(null)
const marginChartElement = ref<HTMLDivElement | null>(null)
const growthChartElement = ref<HTMLDivElement | null>(null)
let trendChart: EChartsType | null = null
let shareChart: EChartsType | null = null
let trafficChart: EChartsType | null = null
let efficiencyChart: EChartsType | null = null
let marginChart: EChartsType | null = null
let growthChart: EChartsType | null = null

const showTables = computed(() => displayMode.value === 'table' || displayMode.value === 'both')
const showCharts = computed(() => displayMode.value === 'chart' || displayMode.value === 'both')

const summaryRows = computed(() => {
  const data = analytics.value
  if (!data) return []
  const rows: { label: string; value: string }[] = []
  if (data.revenue !== undefined) rows.push({ label: '营业额', value: data.revenue == null ? '—' : formatMoney(data.revenue) })
  if (data.sales_cost !== undefined) rows.push({ label: '销售成本', value: data.sales_cost == null ? '—' : formatMoney(data.sales_cost) })
  if (data.gross_profit !== undefined) rows.push({ label: '毛利润', value: data.gross_profit == null ? '—' : formatMoney(data.gross_profit) })
  if (data.sales_quantity !== undefined) rows.push({ label: '销售商品数量', value: data.sales_quantity == null ? '—' : `${data.sales_quantity} 件` })
  if (data.sale_count !== undefined) rows.push({ label: '销售单数', value: data.sale_count == null ? '—' : `${data.sale_count} 单` })
  if (data.average_sale_amount !== undefined) rows.push({ label: '平均每单金额', value: data.average_sale_amount == null ? '—' : formatMoney(data.average_sale_amount) })
  if (data.average_sale_quantity !== undefined) rows.push({ label: '平均每单件数', value: data.average_sale_quantity == null ? '—' : `${data.average_sale_quantity} 件` })
  if (data.gross_profit_margin !== undefined) rows.push({ label: '毛利率', value: formatPercent(data.gross_profit_margin) })
  if (data.revenue_growth_rate !== undefined) rows.push({ label: '营业额增长率', value: formatPercent(data.revenue_growth_rate) })
  if (data.gross_profit_growth_rate !== undefined) rows.push({ label: '毛利润增长率', value: formatPercent(data.gross_profit_growth_rate) })
  return rows
})

function selectAllMetrics() {
  selectedMetrics.value = metricOptions.map((item) => item.value)
}

function invertMetrics() {
  const selected = new Set(selectedMetrics.value)
  selectedMetrics.value = metricOptions
    .filter((item) => !selected.has(item.value))
    .map((item) => item.value)
}

function formatPercent(value: string | null | undefined) {
  return value == null ? '—' : `${Number(value).toFixed(2)}%`
}

function formatTrendLabel(value: string) {
  const date = new Date(value)
  if (interval.value === 'year') return `${date.getFullYear()}年`
  if (interval.value === 'month') return `${date.getFullYear()}/${String(date.getMonth() + 1).padStart(2, '0')}`
  if (interval.value === 'day') return `${String(date.getMonth() + 1).padStart(2, '0')}/${String(date.getDate()).padStart(2, '0')}`
  return formatDateTime(value)
}

async function loadAnalytics() {
  error.value = ''
  if (!selectedMetrics.value.length) {
    analytics.value = null
    error.value = '请至少勾选一个营业指标'
    return
  }
  const start = apiDateTime(startTime.value)
  const end = apiDateTime(endTime.value)
  if (!start || !end) {
    error.value = '请选择开始时间和结束时间'
    return
  }

  loading.value = true
  try {
    analytics.value = await getReportAnalytics({
      start_time: start,
      end_time: end,
      department_id: departmentId.value || undefined,
      interval: interval.value,
      metrics: selectedMetrics.value,
    })
    await nextTick()
    renderCharts()
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

function renderCharts() {
  if (!showCharts.value) {
    trendChart?.dispose()
    shareChart?.dispose()
    trafficChart?.dispose()
    efficiencyChart?.dispose()
    marginChart?.dispose()
    growthChart?.dispose()
    trendChart = null
    shareChart = null
    trafficChart = null
    efficiencyChart = null
    marginChart = null
    growthChart = null
    return
  }

  const trend = analytics.value?.sales_trend ?? []
  if (trendChartElement.value && trend.length) {
    trendChart ??= init(trendChartElement.value)
    trendChart.setOption({
      color: ['#7887ff', '#f8d66d', '#c8ff5a'],
      tooltip: { trigger: 'axis' },
      legend: { top: 2, left: 'center', data: ['营业额', '销售成本', '毛利润'], textStyle: { color: '#a5aab4' } },
      grid: { left: 14, right: 20, top: 62, bottom: 34, containLabel: true },
      xAxis: { type: 'category', data: trend.map((item) => formatTrendLabel(item.start_time)), axisLabel: { color: '#8d929c', hideOverlap: true, margin: 14 } },
      yAxis: { type: 'value', name: '金额（元）', nameTextStyle: { color: '#8d929c' }, axisLabel: { color: '#8d929c' }, splitLine: { lineStyle: { color: '#292c33' } } },
      series: [
        { name: '营业额', type: 'bar', data: trend.map((item) => Number(item.revenue)) },
        { name: '销售成本', type: 'bar', data: trend.map((item) => Number(item.sales_cost)) },
        { name: '毛利润', type: 'line', smooth: true, data: trend.map((item) => Number(item.gross_profit)) },
      ],
    })
  } else {
    trendChart?.dispose()
    trendChart = null
  }

  const labels = trend.map((item) => formatTrendLabel(item.start_time))
  if (trafficChartElement.value && trend.length) {
    trafficChart ??= init(trafficChartElement.value)
    trafficChart.setOption({
      color: ['#7887ff', '#c8ff5a'], tooltip: { trigger: 'axis' },
      legend: { top: 2, left: 'center', data: ['销售数量', '销售单数'], textStyle: { color: '#a5aab4' } },
      grid: { left: 12, right: 16, top: 62, bottom: 34, containLabel: true },
      xAxis: { type: 'category', data: labels, axisLabel: { color: '#8d929c', hideOverlap: true, margin: 14 } },
      yAxis: { type: 'value', axisLabel: { color: '#8d929c' }, splitLine: { lineStyle: { color: '#292c33' } } },
      series: [
        { name: '销售数量', type: 'bar', data: trend.map((item) => item.sales_quantity) },
        { name: '销售单数', type: 'line', smooth: true, data: trend.map((item) => item.sale_count) },
      ],
    })
  } else {
    trafficChart?.dispose()
    trafficChart = null
  }

  if (efficiencyChartElement.value && trend.length) {
    efficiencyChart ??= init(efficiencyChartElement.value)
    efficiencyChart.setOption({
      color: ['#f8d66d', '#7887ff'], tooltip: { trigger: 'axis' },
      legend: { top: 2, left: 'center', data: ['平均每单金额', '平均每单件数'], textStyle: { color: '#a5aab4' } },
      grid: { left: 12, right: 16, top: 62, bottom: 34, containLabel: true },
      xAxis: { type: 'category', data: labels, axisLabel: { color: '#8d929c', hideOverlap: true, margin: 14 } },
      yAxis: [
        { type: 'value', name: '元/单', nameTextStyle: { color: '#8d929c' }, axisLabel: { color: '#8d929c' }, splitLine: { lineStyle: { color: '#292c33' } } },
        { type: 'value', name: '件/单', nameTextStyle: { color: '#8d929c' }, axisLabel: { color: '#8d929c' }, splitLine: { show: false } },
      ],
      series: [
        {
          name: '平均每单金额',
          type: 'line',
          smooth: true,
          data: trend.map((item) =>
            item.sale_count ? Number((Number(item.revenue) / item.sale_count).toFixed(2)) : 0,
          ),
        },
        {
          name: '平均每单件数',
          type: 'line',
          smooth: true,
          yAxisIndex: 1,
          data: trend.map((item) =>
            item.sale_count ? Number((item.sales_quantity / item.sale_count).toFixed(2)) : 0,
          ),
        },
      ],
    })
  } else {
    efficiencyChart?.dispose()
    efficiencyChart = null
  }

  if (marginChartElement.value && trend.length) {
    marginChart ??= init(marginChartElement.value)
    marginChart.setOption({
      color: ['#ff8066'], tooltip: { trigger: 'axis', valueFormatter: (value: unknown) => `${Number(value).toFixed(2)}%` },
      grid: { left: 12, right: 16, top: 34, bottom: 34, containLabel: true },
      xAxis: { type: 'category', data: labels, axisLabel: { color: '#8d929c', hideOverlap: true, margin: 14 } },
      yAxis: { type: 'value', axisLabel: { color: '#8d929c', formatter: '{value}%' }, splitLine: { lineStyle: { color: '#292c33' } } },
      series: [{ name: '毛利率', type: 'line', smooth: true, areaStyle: { opacity: .12 }, data: trend.map((item) => Number(item.gross_profit_margin ?? 0)) }],
    })
  } else {
    marginChart?.dispose()
    marginChart = null
  }

  const growthValues = [analytics.value?.revenue_growth_rate, analytics.value?.gross_profit_growth_rate]
  if (growthChartElement.value && growthValues.some((item) => item !== undefined)) {
    growthChart ??= init(growthChartElement.value)
    growthChart.setOption({
      color: ['#c8ff5a'], tooltip: { trigger: 'axis', valueFormatter: (value: unknown) => `${Number(value).toFixed(2)}%` },
      grid: { left: 12, right: 16, top: 24, bottom: 12, containLabel: true },
      xAxis: { type: 'category', data: ['营业额增长率', '毛利润增长率'], axisLabel: { color: '#8d929c' } },
      yAxis: { type: 'value', axisLabel: { color: '#8d929c', formatter: '{value}%' }, splitLine: { lineStyle: { color: '#292c33' } } },
      series: [{ type: 'bar', barWidth: 48, data: growthValues.map((item) => item == null ? 0 : Number(item)) }],
    })
  } else {
    growthChart?.dispose()
    growthChart = null
  }

  const shares = analytics.value?.department_revenue_share ?? []
  if (shareChartElement.value && shares.length) {
    shareChart ??= init(shareChartElement.value)
    shareChart.setOption({
      color: ['#c8ff5a', '#7887ff', '#ff8066', '#f8d66d'],
      tooltip: { trigger: 'item', formatter: '{b}<br/>{c}%' },
      legend: { bottom: 0, textStyle: { color: '#a5aab4' } },
      series: [{
        type: 'pie',
        radius: ['46%', '70%'],
        center: ['50%', '44%'],
        label: { color: '#e9ecf1', formatter: '{b}\n{c}%' },
        data: shares.map((item) => ({ name: item.department_name, value: Number(item.revenue_share ?? 0) })),
      }],
    })
  } else {
    shareChart?.dispose()
    shareChart = null
  }
}

function resizeCharts() {
  trendChart?.resize()
  shareChart?.resize()
  trafficChart?.resize()
  efficiencyChart?.resize()
  marginChart?.resize()
  growthChart?.resize()
}

watch(displayMode, async () => {
  await nextTick()
  renderCharts()
})

onMounted(async () => {
  window.addEventListener('resize', resizeCharts)
  try {
    departments.value = await getDepartments()
  } catch (reason) {
    error.value = getErrorMessage(reason)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  trendChart?.dispose()
  shareChart?.dispose()
  trafficChart?.dispose()
  efficiencyChart?.dispose()
  marginChart?.dispose()
  growthChart?.dispose()
})
</script>

<template>
  <div>
    <PageHeader eyebrow="BUSINESS INTELLIGENCE" title="经营分析" description="自由组合时间、部门、统计粒度和经营指标，生成一份综合营业报告。" />

    <section class="panel query-panel">
      <div class="panel-heading">
        <div><p class="eyebrow">METRICS</p><h2>选择查询指标</h2></div>
        <div class="button-row"><button class="text-button" type="button" @click="selectAllMetrics">全选</button><button class="text-button" type="button" @click="invertMetrics">反选</button></div>
      </div>

      <div class="metric-picker">
        <label v-for="item in metricOptions" :key="item.value" class="metric-option">
          <input v-model="selectedMetrics" type="checkbox" :value="item.value" />
          <span>{{ item.label }}</span>
        </label>
      </div>

      <div class="query-controls">
        <input v-model="startTime" type="datetime-local" aria-label="开始时间" />
        <span>至</span>
        <input v-model="endTime" type="datetime-local" aria-label="结束时间" />
        <select v-model="departmentId"><option value="">全店</option><option v-for="item in departments" :key="item.id" :value="item.id">{{ item.name }}</option></select>
        <select v-model="interval" :disabled="!selectedMetrics.includes('sales_trend')"><option value="hour">按小时</option><option value="day">按日</option><option value="month">按月</option><option value="year">按年</option></select>
        <button class="primary-button" type="button" :disabled="loading || !selectedMetrics.length" @click="loadAnalytics">{{ loading ? '正在分析…' : '生成分析' }}</button>
        <select v-model="displayMode" aria-label="结果展示方式"><option value="table">仅表格</option><option value="chart">仅图表</option><option value="both">表格和图表</option></select>
      </div>
      <p v-if="error" class="alert error">{{ error }}</p>
    </section>

    <template v-if="analytics">
      <section v-if="showCharts" class="metric-results">
        <div v-if="analytics.revenue !== undefined" class="result-card"><span>营业额</span><strong>{{ analytics.revenue == null ? '—' : formatMoney(analytics.revenue) }}</strong></div>
        <div v-if="analytics.sales_cost !== undefined" class="result-card"><span>销售成本</span><strong>{{ analytics.sales_cost == null ? '—' : formatMoney(analytics.sales_cost) }}</strong></div>
        <div v-if="analytics.gross_profit !== undefined" class="result-card"><span>毛利润</span><strong>{{ analytics.gross_profit == null ? '—' : formatMoney(analytics.gross_profit) }}</strong></div>
        <div v-if="analytics.sales_quantity !== undefined" class="result-card"><span>销售商品数量</span><strong>{{ analytics.sales_quantity ?? '—' }} 件</strong></div>
        <div v-if="analytics.sale_count !== undefined" class="result-card"><span>销售单数</span><strong>{{ analytics.sale_count ?? '—' }} 单</strong></div>
        <div v-if="analytics.average_sale_amount !== undefined" class="result-card"><span>平均每单金额</span><strong>{{ analytics.average_sale_amount == null ? '—' : formatMoney(analytics.average_sale_amount) }}</strong></div>
        <div v-if="analytics.average_sale_quantity !== undefined" class="result-card"><span>平均每单件数</span><strong>{{ analytics.average_sale_quantity == null ? '—' : `${analytics.average_sale_quantity} 件` }}</strong></div>
        <div v-if="analytics.gross_profit_margin !== undefined" class="result-card"><span>毛利率</span><strong>{{ formatPercent(analytics.gross_profit_margin) }}</strong></div>
        <div v-if="analytics.revenue_growth_rate !== undefined" class="result-card"><span>营业额增长率</span><strong>{{ formatPercent(analytics.revenue_growth_rate) }}</strong></div>
        <div v-if="analytics.gross_profit_growth_rate !== undefined" class="result-card"><span>毛利润增长率</span><strong>{{ formatPercent(analytics.gross_profit_growth_rate) }}</strong></div>
      </section>

      <section v-if="showTables" class="table-results">
        <article v-if="summaryRows.length" class="panel data-panel">
          <div class="panel-heading"><div><p class="eyebrow">SUMMARY DATA</p><h2>汇总指标表</h2></div></div>
          <table class="data-table">
            <thead><tr><th>指标</th><th>结果</th></tr></thead>
            <tbody><tr v-for="row in summaryRows" :key="row.label"><td>{{ row.label }}</td><td><strong>{{ row.value }}</strong></td></tr></tbody>
          </table>
        </article>

        <article v-if="analytics.sales_trend" class="panel data-panel">
          <div class="panel-heading"><div><p class="eyebrow">TREND DATA</p><h2>营业趋势明细</h2></div></div>
          <div v-if="analytics.sales_trend.length" class="table-scroll">
            <table class="data-table trend-data-table">
              <thead><tr><th>时间</th><th>营业额</th><th>销售成本</th><th>毛利润</th><th>销量</th><th>单数</th><th>毛利率</th></tr></thead>
              <tbody><tr v-for="item in analytics.sales_trend" :key="item.start_time"><td>{{ formatTrendLabel(item.start_time) }}</td><td>{{ formatMoney(item.revenue) }}</td><td>{{ formatMoney(item.sales_cost) }}</td><td>{{ formatMoney(item.gross_profit) }}</td><td>{{ item.sales_quantity }} 件</td><td>{{ item.sale_count }} 单</td><td>{{ formatPercent(item.gross_profit_margin) }}</td></tr></tbody>
            </table>
          </div>
          <p v-else class="empty-row">所选时间内暂无销售数据</p>
        </article>

        <article v-if="analytics.department_revenue_share" class="panel data-panel">
          <div class="panel-heading"><div><p class="eyebrow">DEPARTMENT DATA</p><h2>部门销售额占比表</h2></div></div>
          <table v-if="analytics.department_revenue_share.length" class="data-table">
            <thead><tr><th>部门</th><th>销售额占比</th></tr></thead>
            <tbody><tr v-for="item in analytics.department_revenue_share" :key="item.department_id"><td>{{ item.department_name }}</td><td><strong>{{ formatPercent(item.revenue_share) }}</strong></td></tr></tbody>
          </table>
          <p v-else class="empty-row">所选时间内暂无部门销售数据</p>
        </article>
      </section>

      <section v-if="showCharts" class="chart-grid">
        <article v-if="analytics.sales_trend" class="panel chart-panel-wide">
          <div class="panel-heading"><div><p class="eyebrow">FINANCIAL TREND</p><h2>营收、成本与毛利润</h2></div></div>
          <div v-if="analytics.sales_trend.length" ref="trendChartElement" class="trend-chart" />
          <p v-else class="empty-row">所选时间内暂无销售数据</p>
        </article>
        <article v-if="analytics.department_revenue_share" class="panel share-panel">
          <div class="panel-heading"><div><p class="eyebrow">DEPARTMENT SHARE</p><h2>部门销售额占比</h2></div></div>
          <div v-if="analytics.department_revenue_share.length" ref="shareChartElement" class="share-chart" />
          <p v-else class="empty-row">所选时间内暂无部门销售数据</p>
        </article>
        <article v-if="analytics.sales_trend?.length" class="panel">
          <div class="panel-heading"><div><p class="eyebrow">TRAFFIC & VOLUME</p><h2>销售单数与商品销量</h2></div></div>
          <div ref="trafficChartElement" class="analysis-chart" />
        </article>
        <article v-if="analytics.sales_trend?.length" class="panel">
          <div class="panel-heading"><div><p class="eyebrow">ORDER EFFICIENCY</p><h2>客单价与单均件数</h2></div></div>
          <div ref="efficiencyChartElement" class="analysis-chart" />
        </article>
        <article v-if="analytics.sales_trend?.length" class="panel">
          <div class="panel-heading"><div><p class="eyebrow">MARGIN TREND</p><h2>毛利率变化</h2></div></div>
          <div ref="marginChartElement" class="analysis-chart" />
        </article>
        <article v-if="analytics.revenue_growth_rate !== undefined || analytics.gross_profit_growth_rate !== undefined" class="panel">
          <div class="panel-heading"><div><p class="eyebrow">PERIOD GROWTH</p><h2>同期增长对比</h2></div></div>
          <div ref="growthChartElement" class="analysis-chart" />
        </article>
      </section>
    </template>
  </div>
</template>

<style scoped>
.query-panel { padding: 28px; }
.button-row, .query-controls { display: flex; align-items: center; gap: 12px; }
.metric-picker { display: flex; flex-wrap: wrap; gap: 10px; margin: 22px 0; }
.metric-option { display: flex; align-items: center; gap: 9px; padding: 11px 15px; border: 1px solid var(--line); border-radius: 9px; color: var(--muted); cursor: pointer; }
.metric-option:has(input:checked) { border-color: var(--green); color: var(--ink); background: rgba(200, 255, 90, .08); }
.metric-option input { accent-color: var(--green); }
.query-controls { flex-wrap: wrap; }
.metric-results { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; margin: 22px 0; }
.result-card { padding: 22px; border: 1px solid var(--line); border-radius: 12px; background: var(--panel); }
.result-card span { display: block; margin-bottom: 12px; color: var(--muted); font-size: 13px; }
.result-card strong { font-size: 25px; }
.table-results { display: grid; gap: 18px; margin: 22px 0; }
.data-panel { padding: 26px; overflow: hidden; }
.table-scroll { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; }
.data-table th, .data-table td { padding: 14px 16px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }
.data-table th { color: var(--muted); font-size: 12px; font-weight: 500; }
.data-table td { color: var(--ink); }
.data-table tbody tr:last-child td { border-bottom: 0; }
.data-table tbody tr:hover { background: rgba(255, 255, 255, .025); }
.trend-data-table { min-width: 850px; }
.chart-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.chart-grid article { padding: 26px; }
.chart-panel-wide { grid-column: 1 / -1; }
.trend-chart { width: 100%; height: 430px; }
.share-chart { width: 100%; height: 430px; }
.analysis-chart { width: 100%; height: 330px; }
@media (max-width: 980px) { .chart-grid { grid-template-columns: 1fr; } }
</style>
