<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { CalendarDays, Layers3, PackageSearch, Pencil, Search, Trash2 } from '@lucide/vue'

import {
  discardExpiredInventoryBatch,
  getDepartments,
  getInventoryBatch,
  getInventoryBatches,
  getSuppliers,
  updateInventoryBatchQuantity,
} from '../api'
import { getErrorMessage } from '../api/http'
import ModalPanel from '../components/ModalPanel.vue'
import PageHeader from '../components/PageHeader.vue'
import { useAuthStore } from '../stores/auth'
import type {
  Department,
  InventoryBatchDetail,
  InventoryBatchListItem,
  InventoryBatchStatus,
  Supplier,
} from '../types/api'
import { formatDateTime, formatMoney } from '../utils'

const auth = useAuthStore()
const batches = ref<InventoryBatchListItem[]>([])
const departments = ref<Department[]>([])
const suppliers = ref<Supplier[]>([])
const detail = ref<InventoryBatchDetail | null>(null)
const detailOpen = ref(false)
const editOpen = ref(false)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const notice = ref('')
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const totalPages = ref(0)
const filters = reactive({
  status: '' as InventoryBatchStatus | '',
  supplier_id: '' as number | '',
  department_id: '' as number | '',
  product_id: '' as number | '',
  expiration_start: '',
  expiration_end: '',
})
const quantityForm = reactive({ remaining_quantity: 0, reason: '' })

const canEditDetail = computed(() => {
  if (!detail.value) return false
  return (
    auth.isManager ||
    (auth.employee?.role === '正式员工' &&
      auth.employee.department?.id === detail.value.department_id)
  )
})

const statusLabel: Record<InventoryBatchStatus, string> = {
  available: '可用',
  near_expiry: '临期',
  expired: '已过期',
  sold_out: '售罄',
}

async function loadBatches() {
  loading.value = true
  error.value = ''
  try {
    const result = await getInventoryBatches({
      page: page.value,
      page_size: pageSize.value,
      status: filters.status || undefined,
      supplier_id: filters.supplier_id || undefined,
      department_id: filters.department_id || undefined,
      product_id: filters.product_id || undefined,
      expiration_start: filters.expiration_start || undefined,
      expiration_end: filters.expiration_end || undefined,
    })
    batches.value = result.items
    total.value = result.total
    totalPages.value = result.total_pages
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

async function openDetail(batchId: number) {
  error.value = ''
  try {
    detail.value = await getInventoryBatch(batchId)
    detailOpen.value = true
  } catch (reason) {
    error.value = getErrorMessage(reason)
  }
}

function openQuantityEditor() {
  if (!detail.value) return
  quantityForm.remaining_quantity = detail.value.remaining_quantity
  quantityForm.reason = ''
  editOpen.value = true
}

async function submitQuantity() {
  if (!detail.value) return
  saving.value = true
  error.value = ''
  try {
    detail.value = await updateInventoryBatchQuantity(
      detail.value.id,
      quantityForm.remaining_quantity,
      quantityForm.reason,
    )
    editOpen.value = false
    notice.value = '批次数量已修改，商品总库存已同步更新。'
    await loadBatches()
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    saving.value = false
  }
}

async function discardExpiredBatch() {
  if (!detail.value || detail.value.status !== 'expired' || detail.value.remaining_quantity <= 0) {
    return
  }
  if (!window.confirm(`确认废弃批次 ${detail.value.batch_no} 的全部剩余库存吗？`)) return

  const reason = window.prompt('请输入废弃原因（可不填）') || undefined
  saving.value = true
  error.value = ''
  try {
    detail.value = await discardExpiredInventoryBatch(detail.value.id, reason)
    notice.value = '过期批次已废弃，商品总库存已同步扣减。'
    await loadBatches()
  } catch (cause) {
    error.value = getErrorMessage(cause)
  } finally {
    saving.value = false
  }
}

function applyFilters() {
  page.value = 1
  loadBatches()
}

watch(page, loadBatches)
onMounted(async () => {
  try {
    const [departmentRows, supplierPage] = await Promise.all([
      getDepartments(),
      getSuppliers({ page: 1, page_size: 100 }),
    ])
    departments.value = departmentRows
    suppliers.value = supplierPage.items
  } catch (reason) {
    error.value = getErrorMessage(reason)
  }
  await loadBatches()
})
</script>

<template>
  <div>
    <PageHeader
      eyebrow="INVENTORY LOTS"
      title="库存批次"
      description="追踪每批商品的来源、保质期和剩余数量。"
    >
      <span class="record-count"><Layers3 :size="17" />共 {{ total }} 个批次</span>
    </PageHeader>

    <section class="panel batch-filter">
      <div class="filter-heading"><Search :size="18" /><span>筛选批次</span></div>
      <select v-model="filters.status">
        <option value="">全部状态</option>
        <option value="available">可用</option>
        <option value="near_expiry">临期</option>
        <option value="expired">已过期</option>
        <option value="sold_out">售罄</option>
      </select>
      <select v-model="filters.department_id">
        <option value="">全部部门</option>
        <option v-for="item in departments" :key="item.id" :value="item.id">{{ item.name }}</option>
      </select>
      <select v-model="filters.supplier_id">
        <option value="">全部供应商</option>
        <option v-for="item in suppliers" :key="item.id" :value="item.id">{{ item.name }}</option>
      </select>
      <input v-model="filters.product_id" type="number" min="1" placeholder="商品ID" />
      <label><CalendarDays :size="15" /><input v-model="filters.expiration_start" type="date" /></label>
      <span>至</span>
      <input v-model="filters.expiration_end" type="date" />
      <button class="primary-button" @click="applyFilters">查询</button>
    </section>

    <p v-if="error" class="alert error">{{ error }}</p>
    <p v-if="notice" class="alert success">{{ notice }}</p>

    <section class="panel table-panel">
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>批次 / 商品</th><th>部门</th><th>数量</th><th>生产 / 到期</th><th>到货时间</th><th>状态</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="item in batches" :key="item.id">
              <td><strong>{{ item.product_name }}</strong><small class="block">{{ item.batch_no }} · {{ item.product_no }}</small></td>
              <td>{{ item.department_name }}</td>
              <td><strong>{{ item.remaining_quantity }}</strong> / {{ item.initial_quantity }} 件</td>
              <td>{{ item.production_date || '—' }}<small class="block">{{ item.expiration_date || '未设置' }}</small></td>
              <td>{{ formatDateTime(item.arrived_at) }}</td>
              <td><span :class="['status-badge', item.status]">{{ statusLabel[item.status] }}</span></td>
              <td><button class="text-button" @click="openDetail(item.id)">查看详情</button></td>
            </tr>
            <tr v-if="!loading && !batches.length"><td colspan="7" class="empty-cell">没有符合条件的库存批次</td></tr>
          </tbody>
        </table>
      </div>
      <div class="pagination">
        <span>第 {{ page }} / {{ totalPages || 1 }} 页</span>
        <div><button :disabled="page <= 1" @click="page--">上一页</button><button :disabled="page >= totalPages" @click="page++">下一页</button></div>
      </div>
    </section>

    <ModalPanel title="库存批次详情" :open="detailOpen" @close="detailOpen = false">
      <div v-if="detail" class="detail-sheet">
        <div class="detail-hero"><span><PackageSearch /></span><div><p>{{ detail.batch_no }}</p><h3>{{ detail.product_name }}</h3></div></div>
        <dl>
          <div><dt>商品编号</dt><dd>{{ detail.product_no }}</dd></div><div><dt>部门 / 分类</dt><dd>{{ detail.department_name }} / {{ detail.category_name }}</dd></div>
          <div><dt>供应商</dt><dd>{{ detail.supplier_name }}</dd></div><div><dt>来源进货单</dt><dd>{{ detail.purchase_no }}</dd></div>
          <div><dt>进货明细ID</dt><dd>{{ detail.purchase_item_id }}</dd></div><div><dt>进货单价</dt><dd>{{ formatMoney(detail.unit_cost) }}</dd></div>
          <div><dt>初始数量</dt><dd>{{ detail.initial_quantity }} 件</dd></div><div><dt>剩余数量</dt><dd>{{ detail.remaining_quantity }} 件</dd></div>
          <div><dt>生产日期</dt><dd>{{ detail.production_date || '—' }}</dd></div><div><dt>到期日期</dt><dd>{{ detail.expiration_date || '未设置' }}</dd></div>
          <div><dt>批次状态</dt><dd>{{ statusLabel[detail.status] }}</dd></div><div><dt>到货时间</dt><dd>{{ formatDateTime(detail.arrived_at) }}</dd></div>
        </dl>
        <div v-if="canEditDetail" class="detail-actions">
          <button class="primary-button" @click="openQuantityEditor"><Pencil :size="16" />盘点并修改数量</button>
          <button v-if="detail.status === 'expired' && detail.remaining_quantity > 0" class="danger-button" :disabled="saving" @click="discardExpiredBatch"><Trash2 :size="16" />废弃过期库存</button>
        </div>
      </div>
    </ModalPanel>

    <ModalPanel title="修改批次剩余数量" :open="editOpen" @close="editOpen = false">
      <form class="stack-form" @submit.prevent="submitQuantity">
        <label><span>盘点后的剩余数量</span><input v-model.number="quantityForm.remaining_quantity" type="number" min="0" required /></label>
        <label><span>修改理由（可选）</span><textarea v-model="quantityForm.reason" maxlength="255" placeholder="例如：盘点发现破损 2 件" /></label>
        <p class="form-tip">保存后会同时重新汇总并更新正式商品的总库存。</p>
        <button class="primary-button full" :disabled="saving">确认修改</button>
      </form>
    </ModalPanel>
  </div>
</template>

<style scoped>
.batch-filter{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:18px;margin-bottom:18px}.batch-filter select,.batch-filter input{min-width:130px}.batch-filter label{display:flex;align-items:center;gap:7px}.filter-heading{display:flex;align-items:center;gap:7px;color:var(--muted);font-weight:700}.block{display:block;margin-top:4px;color:var(--muted)}.detail-actions{display:flex;gap:10px;flex-wrap:wrap}.danger-button{display:inline-flex;align-items:center;gap:7px;padding:10px 14px;border:1px solid #ff7c68;border-radius:9px;background:rgba(255,124,104,.1);color:#ff7c68;font-weight:700}.danger-button:disabled{opacity:.55;cursor:not-allowed}textarea{min-height:90px;resize:vertical;padding:11px;border:1px solid var(--line);border-radius:9px;background:var(--paper);color:var(--ink)}@media(max-width:760px){.batch-filter>*{flex:1 1 100%}}
</style>
