<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { Boxes, Search, SlidersHorizontal } from '@lucide/vue'

import { getCategories, getDepartments, getProduct, getProducts } from '../api'
import { getErrorMessage } from '../api/http'
import ModalPanel from '../components/ModalPanel.vue'
import PageHeader from '../components/PageHeader.vue'
import type { Category, Department, ProductDetail, ProductListItem, ProductStatus } from '../types/api'
import { formatMoney } from '../utils'

const products = ref<ProductListItem[]>([])
const departments = ref<Department[]>([])
const categories = ref<Category[]>([])
const detail = ref<ProductDetail | null>(null)
const detailOpen = ref(false)
const loading = ref(false)
const error = ref('')
const keyword = ref('')
const departmentId = ref<number | ''>('')
const categoryId = ref<number | ''>('')
const status = ref<ProductStatus | ''>('')
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const totalPages = ref(0)

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
      <button class="primary-button" @click="search"><SlidersHorizontal :size="17" />应用筛选</button>
    </section>

    <p v-if="error" class="alert error">{{ error }}</p>
    <section class="panel table-panel">
      <div class="table-wrap">
        <table>
          <thead><tr><th>商品</th><th>部门 / 分类</th><th>进货价</th><th>销售价</th><th>库存</th><th>状态</th><th></th></tr></thead>
          <tbody>
            <tr v-for="item in products" :key="item.id">
              <td><div class="product-cell"><span>{{ item.name.slice(0, 1) }}</span><div><strong>{{ item.name }}</strong><small>{{ item.product_no }}</small></div></div></td>
              <td><strong class="plain">{{ item.department_name }}</strong><small class="block">{{ item.category_name }}</small></td>
              <td>{{ formatMoney(item.purchase_price) }}</td><td><strong>{{ formatMoney(item.sale_price) }}</strong></td>
              <td><span :class="['stock-badge', { low: item.stock_quantity <= 5 }]">{{ item.stock_quantity }} 件</span></td>
              <td><span :class="['status-badge', item.status]">{{ item.status === 'on_sale' ? '在售' : '停售' }}</span></td>
              <td><button class="text-button" @click="openDetail(item.id)">详情</button></td>
            </tr>
            <tr v-if="!loading && !products.length"><td colspan="7" class="empty-cell">没有找到符合条件的商品</td></tr>
          </tbody>
        </table>
      </div>
      <div class="pagination"><span>第 {{ page }} / {{ totalPages || 1 }} 页</span><div><button :disabled="page <= 1" @click="page--">上一页</button><button :disabled="page >= totalPages" @click="page++">下一页</button></div></div>
    </section>

    <ModalPanel title="商品详情" :open="detailOpen" @close="detailOpen = false">
      <div v-if="detail" class="detail-sheet">
        <div class="detail-hero"><span>{{ detail.name.slice(0, 1) }}</span><div><p>{{ detail.product_no }}</p><h3>{{ detail.name }}</h3></div></div>
        <dl><div><dt>所属部门</dt><dd>{{ detail.department.name }}</dd></div><div><dt>商品分类</dt><dd>{{ detail.category.name }}</dd></div><div><dt>进货价格</dt><dd>{{ formatMoney(detail.purchase_price) }}</dd></div><div><dt>销售价格</dt><dd>{{ formatMoney(detail.sale_price) }}</dd></div><div><dt>当前库存</dt><dd>{{ detail.stock_quantity }} 件</dd></div><div><dt>销售状态</dt><dd>{{ detail.status === 'on_sale' ? '在售' : '停售' }}</dd></div></dl>
      </div>
    </ModalPanel>
  </div>
</template>
