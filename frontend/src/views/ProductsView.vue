<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Boxes, Pencil, Search, SlidersHorizontal } from '@lucide/vue'

import {
  getCategories,
  getDepartments,
  getProduct,
  getProducts,
  updateProduct,
  updateProductStatus,
} from '../api'
import { getErrorMessage } from '../api/http'
import ModalPanel from '../components/ModalPanel.vue'
import PageHeader from '../components/PageHeader.vue'
import { useAuthStore } from '../stores/auth'
import type { Category, Department, ProductDetail, ProductListItem, ProductStatus } from '../types/api'
import { formatMoney } from '../utils'

const products = ref<ProductListItem[]>([])
const auth = useAuthStore()
const departments = ref<Department[]>([])
const categories = ref<Category[]>([])
const detail = ref<ProductDetail | null>(null)
const detailOpen = ref(false)
const editOpen = ref(false)
const saving = ref(false)
const notice = ref('')
const editForm = reactive({
  name: '',
  category_id: 0,
  sale_price: '',
  expiry_warning_days: 1,
  low_stock_threshold: '' as number | '',
  reason: '',
})
const loading = ref(false)
const error = ref('')
const keyword = ref('')
const departmentId = ref<number | ''>('')
const categoryId = ref<number | ''>('')
const status = ref<ProductStatus | ''>('')
const stockConsistent = ref<'' | 'true' | 'false'>('')
const lowStock = ref<'' | 'true' | 'false'>('')
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const totalPages = ref(0)
const canEditDetail = computed(() =>
  Boolean(
    detail.value &&
      (auth.isManager ||
        (auth.employee?.role === '正式员工' &&
          auth.employee.department?.id === detail.value.department.id)),
  ),
)

async function loadProducts() {
  loading.value = true
  error.value = ''
  try {
    const result = await getProducts({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
      department_id: departmentId.value || undefined,
      category_id: categoryId.value || undefined,
      status: status.value || undefined,
      stock_consistent: stockConsistent.value || undefined,
      low_stock: lowStock.value || undefined,
    })
    products.value = result.items
    total.value = result.total
    totalPages.value = result.total_pages
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

async function openDetail(productId: number) {
  try {
    detail.value = await getProduct(productId)
    detailOpen.value = true
  } catch (reason) {
    error.value = getErrorMessage(reason)
  }
}

async function openEditor() {
  if (!detail.value) return
  editForm.name = detail.value.name
  editForm.category_id = detail.value.category.id
  editForm.sale_price = detail.value.sale_price
  editForm.expiry_warning_days = detail.value.expiry_warning_days ?? 1
  editForm.low_stock_threshold = detail.value.low_stock_threshold ?? ''
  editForm.reason = ''
  categories.value = await getCategories(detail.value.department.id)
  editOpen.value = true
}

async function submitEdit() {
  if (!detail.value) return
  saving.value = true
  error.value = ''
  try {
    detail.value = await updateProduct(detail.value.id, {
      name: editForm.name,
      category_id: editForm.category_id,
      sale_price: editForm.sale_price,
      expiry_warning_days: editForm.expiry_warning_days,
      low_stock_threshold:
        editForm.low_stock_threshold === '' ? null : editForm.low_stock_threshold,
      reason: editForm.reason || undefined,
    })
    editOpen.value = false
    notice.value = '商品资料修改成功。'
    await loadProducts()
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    saving.value = false
  }
}

async function toggleDetailStatus() {
  if (!detail.value) return
  const nextStatus: ProductStatus = detail.value.status === 'on_sale' ? 'stopped' : 'on_sale'
  const reason = window.prompt(`请输入${nextStatus === 'on_sale' ? '上架' : '停售'}理由（可不填）`) || undefined
  try {
    detail.value = await updateProductStatus(detail.value.id, nextStatus, reason)
    notice.value = `商品已${nextStatus === 'on_sale' ? '上架' : '停售'}。`
    await loadProducts()
  } catch (cause) {
    error.value = getErrorMessage(cause)
  }
}

async function changeDepartment() {
  categoryId.value = ''
  categories.value = await getCategories(departmentId.value || undefined)
  page.value = 1
  await loadProducts()
}

function search() {
  page.value = 1
  loadProducts()
}

watch(page, loadProducts)
onMounted(async () => {
  try {
    ;[departments.value, categories.value] = await Promise.all([getDepartments(), getCategories()])
  } catch (reason) {
    error.value = getErrorMessage(reason)
  }
  await loadProducts()
})
</script>

<template>
  <div>
    <PageHeader eyebrow="PRODUCT CATALOG" title="商品查询" description="按部门、分类和状态快速定位商品与当前库存。">
      <span class="record-count"><Boxes :size="17" />共 {{ total }} 个商品</span>
    </PageHeader>

    <section class="panel filter-panel">
      <div class="search-field"><Search :size="18" /><input v-model="keyword" placeholder="搜索商品名称" @keyup.enter="search" /></div>
      <select v-model="departmentId" @change="changeDepartment"><option value="">全部部门</option><option v-for="item in departments" :key="item.id" :value="item.id">{{ item.name }}</option></select>
      <select v-model="categoryId" @change="search"><option value="">全部分类</option><option v-for="item in categories" :key="item.id" :value="item.id">{{ item.name }}</option></select>
      <select v-model="status" @change="search"><option value="">全部状态</option><option value="on_sale">在售</option><option value="stopped">停售</option></select>
      <select v-model="stockConsistent" @change="search"><option value="">全部库存</option><option value="true">库存一致</option><option value="false">库存不一致</option></select>
      <select v-model="lowStock" @change="search"><option value="">全部预警状态</option><option value="true">仅低库存</option><option value="false">未触发低库存</option></select>
      <button class="primary-button" @click="search"><SlidersHorizontal :size="17" />应用筛选</button>
    </section>

    <p v-if="error" class="alert error">{{ error }}</p>
    <p v-if="notice" class="alert success">{{ notice }}</p>
    <section class="panel table-panel">
      <div class="table-wrap">
        <table>
          <thead><tr><th>商品</th><th>部门 / 分类</th><th>进货价</th><th>销售价</th><th>库存概览</th><th>临期 / 过期</th><th>库存校验</th><th>状态</th><th></th></tr></thead>
          <tbody>
            <tr v-for="item in products" :key="item.id">
              <td><div class="product-cell"><span>{{ item.name.slice(0, 1) }}</span><div><strong>{{ item.name }}</strong><small>{{ item.product_no }}</small></div></div></td>
              <td><strong class="plain">{{ item.department_name }}</strong><small class="block">{{ item.category_name }}</small></td>
              <td>{{ formatMoney(item.purchase_price) }}</td><td><strong>{{ formatMoney(item.sale_price) }}</strong></td>
              <td>
                <div class="inventory-overview">
                  <span :class="['stock-badge', { low: item.is_low_stock }]">可售 {{ item.saleable_stock_quantity }} 件</span>
                  <small>全部 {{ item.total_stock_quantity }} 件</small>
                </div>
              </td>
              <td>
                <div class="inventory-overview warning-stock">
                  <span>临期 {{ item.near_expiry_stock_quantity }} 件 / {{ item.near_expiry_batch_count }} 批</span>
                  <small :class="{ expired: item.expired_stock_quantity > 0 }">过期 {{ item.expired_stock_quantity }} 件 / {{ item.expired_batch_count }} 批</small>
                </div>
              </td>
              <td><span :class="['status-badge', item.is_stock_consistent ? 'on_sale' : 'stopped']">{{ item.is_stock_consistent ? '一致' : `相差 ${item.stock_difference}` }}</span></td>
              <td><span :class="['status-badge', item.status]">{{ item.status === 'on_sale' ? '在售' : '停售' }}</span></td>
              <td><button class="text-button" @click="openDetail(item.id)">详情</button></td>
            </tr>
            <tr v-if="!loading && !products.length"><td colspan="9" class="empty-cell">没有找到符合条件的商品</td></tr>
          </tbody>
        </table>
      </div>
      <div class="pagination"><span>第 {{ page }} / {{ totalPages || 1 }} 页</span><div><button :disabled="page <= 1" @click="page--">上一页</button><button :disabled="page >= totalPages" @click="page++">下一页</button></div></div>
    </section>

    <ModalPanel title="商品详情" :open="detailOpen" @close="detailOpen = false">
      <div v-if="detail" class="detail-sheet">
        <div class="detail-hero"><span>{{ detail.name.slice(0, 1) }}</span><div><p>{{ detail.product_no }}</p><h3>{{ detail.name }}</h3></div></div>
        <dl><div><dt>所属部门</dt><dd>{{ detail.department.name }}</dd></div><div><dt>商品分类</dt><dd>{{ detail.category.name }}</dd></div><div><dt>进货价格</dt><dd>{{ formatMoney(detail.purchase_price) }}</dd></div><div><dt>销售价格</dt><dd>{{ formatMoney(detail.sale_price) }}</dd></div><div><dt>当前库存</dt><dd>{{ detail.stock_quantity }} 件</dd></div><div><dt>临期提醒</dt><dd>提前 {{ detail.expiry_warning_days ?? 0 }} 天</dd></div><div><dt>低库存阈值</dt><dd>{{ detail.low_stock_threshold === null ? '未启用' : `${detail.low_stock_threshold} 件` }}</dd></div><div><dt>销售状态</dt><dd>{{ detail.status === 'on_sale' ? '在售' : '停售' }}</dd></div></dl>
        <div v-if="canEditDetail" class="detail-actions"><button class="primary-button" @click="openEditor"><Pencil :size="16" />修改资料</button><button class="secondary-button" @click="toggleDetailStatus">{{ detail.status === 'on_sale' ? '设为停售' : '重新上架' }}</button></div>
      </div>
    </ModalPanel>

    <ModalPanel title="修改商品资料" :open="editOpen" @close="editOpen = false">
      <form class="stack-form" @submit.prevent="submitEdit">
        <label><span>商品名称</span><input v-model="editForm.name" maxlength="100" required /></label>
        <label><span>商品分类</span><select v-model.number="editForm.category_id" required><option v-for="item in categories" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
        <label><span>销售价格</span><input v-model="editForm.sale_price" type="number" min="0" step="0.01" required /></label>
        <label><span>临期提前提醒天数</span><input v-model.number="editForm.expiry_warning_days" type="number" min="0" required /></label>
        <label><span>低库存预警阈值（留空关闭）</span><input v-model.number="editForm.low_stock_threshold" type="number" min="0" placeholder="例如 10" /></label>
        <label><span>修改理由（可选）</span><textarea v-model="editForm.reason" maxlength="255" /></label>
        <button class="primary-button full" :disabled="saving">保存修改</button>
      </form>
    </ModalPanel>
  </div>
</template>

<style scoped>
.detail-actions{display:flex;gap:10px;margin-top:20px}.inventory-overview{display:flex;flex-direction:column;align-items:flex-start;gap:5px}.inventory-overview small{color:var(--muted)}.warning-stock span{color:#f0b84b}.warning-stock .expired{color:#ff7c68;font-weight:700}textarea{min-height:80px;resize:vertical;padding:11px;border:1px solid var(--line);border-radius:9px;background:var(--paper);color:var(--ink)}
</style>
