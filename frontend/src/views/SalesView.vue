<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { CalendarDays, ReceiptText, Search } from '@lucide/vue'

import { getSale, getSales } from '../api'
import { getErrorMessage } from '../api/http'
import ModalPanel from '../components/ModalPanel.vue'
import PageHeader from '../components/PageHeader.vue'
import type { SaleDetail, SaleListItem } from '../types/api'
import { apiDateTime, createDefaultRange, formatDateTime, formatMoney } from '../utils'

const defaultRange = createDefaultRange()
const startTime = ref(defaultRange.start)
const endTime = ref(defaultRange.end)
const saleNo = ref('')
const sales = ref<SaleListItem[]>([])
const detail = ref<SaleDetail | null>(null)
const detailOpen = ref(false)
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const totalPages = ref(0)
const loading = ref(false)
const error = ref('')

async function loadSales() {
  loading.value = true
  error.value = ''
  try {
    const result = await getSales({
      page: page.value,
      page_size: pageSize.value,
      start_time: apiDateTime(startTime.value),
      end_time: apiDateTime(endTime.value),
      sale_no: saleNo.value || undefined,
    })
    sales.value = result.items
    total.value = result.total
    totalPages.value = result.total_pages
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

async function openSale(number: string) {
  try {
    detail.value = await getSale(number)
    detailOpen.value = true
  } catch (reason) {
    error.value = getErrorMessage(reason)
  }
}

function search() {
  page.value = 1
  loadSales()
}

watch(page, loadSales)
onMounted(loadSales)
</script>

<template>
  <div>
    <PageHeader eyebrow="TRANSACTION LEDGER" title="销售记录" description="按时间或销售单号查询每一张收银记录。">
      <span class="record-count"><ReceiptText :size="17" />共 {{ total }} 张销售单</span>
    </PageHeader>

    <section class="panel filter-panel sales-filter">
      <div class="search-field"><Search :size="18" /><input v-model="saleNo" placeholder="输入销售单号" @keyup.enter="search" /></div>
      <div class="field inline"><CalendarDays :size="17" /><input v-model="startTime" type="datetime-local" /></div>
      <span>至</span><div class="field inline"><input v-model="endTime" type="datetime-local" /></div>
      <button class="primary-button" @click="search">查询记录</button>
    </section>

    <p v-if="error" class="alert error">{{ error }}</p>
    <section class="panel table-panel">
      <div class="table-wrap">
        <table>
          <thead><tr><th>销售单号</th><th>发生时间</th><th>商品种类</th><th>商品总数</th><th>销售金额</th><th></th></tr></thead>
          <tbody>
            <tr v-for="item in sales" :key="item.sale_no"><td><strong class="mono">{{ item.sale_no }}</strong></td><td>{{ formatDateTime(item.sold_at) }}</td><td>{{ item.item_count }} 种</td><td>{{ item.total_quantity }} 件</td><td><strong>{{ formatMoney(item.total_amount) }}</strong></td><td><button class="text-button" @click="openSale(item.sale_no)">查看明细</button></td></tr>
            <tr v-if="!loading && !sales.length"><td colspan="6" class="empty-cell">所选范围内没有销售记录</td></tr>
          </tbody>
        </table>
      </div>
      <div class="pagination"><span>第 {{ page }} / {{ totalPages || 1 }} 页</span><div><button :disabled="page <= 1" @click="page--">上一页</button><button :disabled="page >= totalPages" @click="page++">下一页</button></div></div>
    </section>

    <ModalPanel title="销售单详情" :open="detailOpen" @close="detailOpen = false">
      <div v-if="detail" class="receipt-sheet">
        <div class="receipt-head"><div><p>销售单号</p><strong>{{ detail.sale_no }}</strong></div><div><p>销售时间</p><strong>{{ formatDateTime(detail.sold_at) }}</strong></div></div>
        <div class="receipt-lines"><div v-for="item in detail.items" :key="`${item.product_name}-${item.unit_price}`"><div><strong>{{ item.product_name }}</strong><span>{{ formatMoney(item.unit_price) }} × {{ item.quantity }}</span></div><b>{{ formatMoney(item.subtotal) }}</b></div></div>
        <div class="receipt-total"><span>销售总金额</span><strong>{{ formatMoney(detail.total_amount) }}</strong></div>
      </div>
    </ModalPanel>
  </div>
</template>
