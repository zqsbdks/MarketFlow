<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  History,
  PackageOpen,
  RotateCcw,
  Search,
  SlidersHorizontal,
} from '@lucide/vue'

import { getInventoryMovements } from '../api'
import { getErrorMessage } from '../api/http'
import PageHeader from '../components/PageHeader.vue'
import type { InventoryMovement, InventoryMovementAction } from '../types/api'
import { apiDateTime, formatDateTime } from '../utils'

const movements = ref<InventoryMovement[]>([])
const loading = ref(false)
const error = ref('')
const keyword = ref('')
const action = ref<InventoryMovementAction | ''>('')
const startTime = ref('')
const endTime = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const totalPages = ref(0)

// 页面顶部的增加和减少数量只统计当前页，避免误以为是全部历史合计。
const currentPageIncrease = computed(() =>
  movements.value.reduce(
    (totalQuantity, item) => totalQuantity + Math.max(item.change_quantity ?? 0, 0),
    0,
  ),
)
const currentPageDecrease = computed(() =>
  movements.value.reduce(
    (totalQuantity, item) => totalQuantity + Math.abs(Math.min(item.change_quantity ?? 0, 0)),
    0,
  ),
)

async function loadMovements() {
  loading.value = true
  error.value = ''
  try {
    const result = await getInventoryMovements({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
      action: action.value || undefined,
      start_time: apiDateTime(startTime.value),
      end_time: apiDateTime(endTime.value),
    })
    movements.value = result.items
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
  loadMovements()
}

function resetFilters() {
  keyword.value = ''
  action.value = ''
  startTime.value = ''
  endTime.value = ''
  search()
}

function formatChange(quantity: number | null) {
  if (quantity === null) return '—'
  return quantity > 0 ? `+${quantity}` : String(quantity)
}

watch(page, loadMovements)
onMounted(loadMovements)
</script>

<template>
  <div>
    <PageHeader
      eyebrow="INVENTORY LEDGER"
      title="库存变动流水"
      description="追踪每个批次的进货入库、销售出库、人工盘点与过期废弃。"
    >
      <span class="record-count"><History :size="17" />共 {{ total }} 条流水</span>
    </PageHeader>

    <section class="stat-grid three movement-summary">
      <article class="stat-card tone-ink">
        <div class="stat-icon"><History :size="18" /></div>
        <p>符合条件的记录</p>
        <strong>{{ total }} 条</strong>
        <span>包含全部查询结果</span>
      </article>
      <article class="stat-card tone-green">
        <div class="stat-icon"><ArrowDownToLine :size="18" /></div>
        <p>本页库存增加</p>
        <strong>+{{ currentPageIncrease }} 件</strong>
        <span>进货入库及盘点调增</span>
      </article>
      <article class="stat-card tone-orange">
        <div class="stat-icon"><ArrowUpFromLine :size="18" /></div>
        <p>本页库存减少</p>
        <strong>-{{ currentPageDecrease }} 件</strong>
        <span>销售、废弃及盘点调减</span>
      </article>
    </section>

    <section class="panel filter-panel movement-filter">
      <div class="search-field">
        <Search :size="18" />
        <input
          v-model="keyword"
          placeholder="搜索商品、编号或批次号"
          @keyup.enter="search"
        />
      </div>
      <select v-model="action" @change="search">
        <option value="">全部变动类型</option>
        <option value="create_batch">进货入库</option>
        <option value="sale_deduction">销售出库</option>
        <option value="update_quantity">人工盘点</option>
        <option value="discard_expired">过期废弃</option>
      </select>
      <input v-model="startTime" type="datetime-local" title="开始时间" />
      <span class="range-separator">至</span>
      <input v-model="endTime" type="datetime-local" title="结束时间" />
      <button class="primary-button" type="button" @click="search">
        <SlidersHorizontal :size="17" />查询
      </button>
      <button class="secondary-button" type="button" @click="resetFilters">
        <RotateCcw :size="16" />重置
      </button>
    </section>

    <p v-if="error" class="alert error">{{ error }}</p>

    <section class="panel table-panel">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>变动时间</th>
              <th>商品</th>
              <th>库存批次</th>
              <th>变动类型</th>
              <th>变动前</th>
              <th>变动数量</th>
              <th>变动后</th>
              <th>操作人</th>
              <th>原因</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in movements" :key="item.id">
              <td>{{ formatDateTime(item.created_at) }}</td>
              <td>
                <div class="product-cell">
                  <span>{{ item.product_name?.slice(0, 1) || '?' }}</span>
                  <div>
                    <strong>{{ item.product_name || '商品记录不存在' }}</strong>
                    <small>{{ item.product_no || `商品ID ${item.product_id ?? '—'}` }}</small>
                  </div>
                </div>
              </td>
              <td>
                <strong class="plain mono">{{ item.batch_no || `#${item.batch_id}` }}</strong>
                <small class="block">批次ID {{ item.batch_id }}</small>
              </td>
              <td>
                <span :class="['movement-badge', item.action]">{{ item.action_name }}</span>
              </td>
              <td>{{ item.before_quantity ?? '—' }}<span v-if="item.before_quantity !== null"> 件</span></td>
              <td>
                <strong
                  :class="[
                    'quantity-change',
                    { increase: (item.change_quantity ?? 0) > 0, decrease: (item.change_quantity ?? 0) < 0 },
                  ]"
                >
                  {{ formatChange(item.change_quantity) }}<span v-if="item.change_quantity !== null"> 件</span>
                </strong>
              </td>
              <td>{{ item.after_quantity ?? '—' }}<span v-if="item.after_quantity !== null"> 件</span></td>
              <td>
                <strong class="plain">{{ item.employee_name }}</strong>
                <small class="block">{{ item.employee_id ? `员工ID ${item.employee_id}` : '自动执行' }}</small>
              </td>
              <td class="reason-cell">{{ item.reason || '—' }}</td>
            </tr>
            <tr v-if="!loading && !movements.length">
              <td colspan="9" class="empty-cell">
                <PackageOpen :size="24" />
                <span>没有找到符合条件的库存变动</span>
              </td>
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
  </div>
</template>

<style scoped>
.movement-summary { margin-bottom: 18px; }
.movement-filter { flex-wrap: wrap; }
.movement-filter .search-field { flex: 1 1 260px; }
.range-separator { color: var(--muted); font-size: 12px; }
.movement-badge { display: inline-flex; padding: 5px 9px; border-radius: 20px; font-size: 10px; font-weight: 800; }
.movement-badge.create_batch { color: #c8ff5a; background: #25321d; }
.movement-badge.sale_deduction { color: #9facff; background: #252a45; }
.movement-badge.update_quantity { color: #ffd86b; background: #3a321d; }
.movement-badge.discard_expired { color: #ff9a87; background: #38221f; }
.quantity-change { font-family: "SFMono-Regular", Consolas, monospace; }
.quantity-change.increase { color: #bce95e; }
.quantity-change.decrease { color: #ff8f79; }
.reason-cell { max-width: 250px; overflow: hidden; text-overflow: ellipsis; }
.empty-cell svg { display: block; margin: 0 auto 8px; }
.empty-cell span { display: block; }
@media (max-width: 700px) {
  .movement-filter > input, .movement-filter > select { width: 100%; }
  .range-separator { display: none; }
}
</style>
