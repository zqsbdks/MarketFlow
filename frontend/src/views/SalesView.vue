<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { CalendarDays, ReceiptText, Search } from '@lucide/vue'

import { getSale, getSales } from '../api'
import { getErrorMessage } from '../api/http'
import ModalPanel from '../components/ModalPanel.vue'
import PageHeader from '../components/PageHeader.vue'
import type { SaleDetail, SaleListItem } from '../types/api'
import { apiDateTime, createDefaultRange, formatDateTime, formatMoney } from '../utils'

// region 销售记录查询状态
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
// endregion


// region 获取销售单列表
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

function search() {
  page.value = 1
  loadSales()
}
// endregion


// region 获取销售单详情
async function openSale(number: string) {
  try {
    detail.value = await getSale(number)
    detailOpen.value = true
  } catch (reason) {
    error.value = getErrorMessage(reason)
  }
}
// endregion


watch(page, loadSales)
onMounted(loadSales)
</script>

<template>
  <div>
    <PageHeader
      eyebrow="SALES RECORDS"
      title="销售记录"
      description="按照销售单号或发生时间查询历史结账记录，并查看成交价格和折扣明细。"
    >
      <span class="record-count"><ReceiptText :size="17" />共 {{ total }} 张销售单</span>
    </PageHeader>

    <section class="panel filter-panel sales-filter">
      <div class="search-field">
        <Search :size="18" />
        <input v-model="saleNo" placeholder="输入销售单号" @keyup.enter="search" />
      </div>
      <div class="field inline">
        <CalendarDays :size="17" />
        <input v-model="startTime" type="datetime-local" />
      </div>
      <span>至</span>
      <div class="field inline"><input v-model="endTime" type="datetime-local" /></div>
      <button class="primary-button" @click="search">查询记录</button>
    </section>

    <p v-if="error" class="alert error">{{ error }}</p>

    <section class="panel table-panel">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>销售单号</th>
              <th>发生时间</th>
              <th>商品种类</th>
              <th>商品总数</th>
              <th>原价金额</th>
              <th>优惠金额</th>
              <th>实收金额</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in sales" :key="item.sale_no">
              <td><strong class="mono">{{ item.sale_no }}</strong></td>
              <td>{{ formatDateTime(item.sold_at) }}</td>
              <td>{{ item.item_count }} 种</td>
              <td>{{ item.total_quantity }} 件</td>
              <td>{{ formatMoney(item.original_total_amount) }}</td>
              <td class="discount-value">-{{ formatMoney(item.discount_amount) }}</td>
              <td><strong>{{ formatMoney(item.total_amount) }}</strong></td>
              <td><button class="text-button" @click="openSale(item.sale_no)">查看明细</button></td>
            </tr>
            <tr v-if="!loading && !sales.length">
              <td colspan="8" class="empty-cell">所选范围内没有销售记录</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="pagination">
        <span>第 {{ page }} / {{ totalPages || 1 }} 页</span>
        <div>
          <button :disabled="page <= 1" @click="page--">上一页</button>
          <button :disabled="page >= totalPages" @click="page++">下一页</button>
        </div>
      </div>
    </section>

    <ModalPanel title="销售单详情" :open="detailOpen" @close="detailOpen = false">
      <div v-if="detail" class="receipt-sheet">
        <div class="receipt-head">
          <div><p>销售单号</p><strong>{{ detail.sale_no }}</strong></div>
          <div><p>销售时间</p><strong>{{ formatDateTime(detail.sold_at) }}</strong></div>
        </div>
        <div class="receipt-lines">
          <div v-for="item in detail.items" :key="`${item.product_id}-${item.unit_price}-${item.discount_rule_id}`">
            <div>
              <strong>{{ item.product_name }}</strong>
              <span><s v-if="Number(item.discount_amount) > 0">{{ formatMoney(item.original_unit_price) }}</s> {{ formatMoney(item.unit_price) }} × {{ item.quantity }}</span>
              <small v-if="item.discount_rule_name" class="discount-name">{{ item.discount_rule_name }}</small>
            </div>
            <b>{{ formatMoney(item.subtotal) }}</b>
          </div>
        </div>
        <div class="receipt-total"><span>原价合计</span><strong>{{ formatMoney(detail.original_total_amount) }}</strong></div>
        <div v-if="Number(detail.discount_amount) > 0" class="receipt-total"><span>优惠金额</span><strong class="discount-value">-{{ formatMoney(detail.discount_amount) }}</strong></div>
        <div class="receipt-total final-total"><span>实际支付</span><strong>{{ formatMoney(detail.total_amount) }}</strong></div>
      </div>
    </ModalPanel>
  </div>
</template>

<style scoped>
.discount-value { color: #ff907b; }
.discount-name { display: block; margin-top: 4px; color: #c8ff5a; }
.final-total { margin-top: 12px; border-top: 1px solid #2b2e35; }
</style>
