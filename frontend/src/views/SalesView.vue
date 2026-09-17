<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { CalendarDays, Minus, Plus, ReceiptText, ScanLine, Search, ShoppingCart, Trash2 } from '@lucide/vue'

import { createSale, getProducts, getSale, getSales } from '../api'
import { getErrorMessage } from '../api/http'
import ModalPanel from '../components/ModalPanel.vue'
import PageHeader from '../components/PageHeader.vue'
import type { ProductListItem, SaleDetail, SaleListItem } from '../types/api'
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
const products = ref<ProductListItem[]>([])
const selectedProductId = ref<number | ''>('')
const cart = ref<Array<{ product: ProductListItem; quantity: number }>>([])
const checkoutLoading = ref(false)

const cartQuantity = computed(() => cart.value.reduce((sum, item) => sum + item.quantity, 0))
const cartAmount = computed(() =>
  cart.value.reduce((sum, item) => sum + Number(item.product.sale_price) * item.quantity, 0),
)

async function loadSaleProducts() {
  try {
    // 收银台只展示仍在销售并且批次库存大于零的商品，避免选择明显无法结账的商品。
    const result = await getProducts({ page: 1, page_size: 100, status: 'on_sale' })
    products.value = result.items.filter((product) => product.batch_stock_quantity > 0)
  } catch (reason) {
    error.value = getErrorMessage(reason)
  }
}

function addSelectedProduct() {
  if (selectedProductId.value === '') return
  const product = products.value.find((item) => item.id === selectedProductId.value)
  if (!product) return
  const existing = cart.value.find((item) => item.product.id === product.id)
  if (existing) existing.quantity += 1
  else cart.value.push({ product, quantity: 1 })
  selectedProductId.value = ''
}

function changeQuantity(productId: number, difference: number) {
  const item = cart.value.find((entry) => entry.product.id === productId)
  if (!item) return
  item.quantity += difference
  if (item.quantity <= 0) removeProduct(productId)
}

function removeProduct(productId: number) {
  cart.value = cart.value.filter((item) => item.product.id !== productId)
}

async function checkout() {
  if (!cart.value.length) return
  checkoutLoading.value = true
  error.value = ''
  try {
    detail.value = await createSale(
      cart.value.map((item) => ({ product_id: item.product.id, quantity: item.quantity })),
    )
    cart.value = []
    detailOpen.value = true
    await Promise.all([loadSales(), loadSaleProducts()])
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    checkoutLoading.value = false
  }
}

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
onMounted(async () => {
  await Promise.all([loadSales(), loadSaleProducts()])
})
</script>

<template>
  <div>
    <PageHeader
      eyebrow="POINT OF SALE"
      title="销售收银"
      description="模拟扫码结账，并按时间或销售单号查询历史收银记录。"
    >
      <span class="record-count"><ReceiptText :size="17" />共 {{ total }} 张销售单</span>
    </PageHeader>

    <section class="checkout-grid">
      <div class="panel checkout-catalog">
        <div class="checkout-title">
          <div>
            <span class="checkout-kicker">POS CHECKOUT</span>
            <h2>模拟收银台</h2>
          </div>
          <ScanLine :size="28" />
        </div>
        <p>选择扫码识别出的商品，系统会在结账时自动从最早到期批次扣减库存。</p>
        <div class="scan-row">
          <select v-model="selectedProductId" @keyup.enter="addSelectedProduct">
            <option value="">选择商品编号或名称</option>
            <option v-for="product in products" :key="product.id" :value="product.id">
              {{ product.product_no }} · {{ product.name }} · 库存 {{ product.batch_stock_quantity }}
            </option>
          </select>
          <button
            class="primary-button"
            :disabled="selectedProductId === ''"
            @click="addSelectedProduct"
          >
            <Plus :size="17" />加入
          </button>
        </div>
        <div v-if="cart.length" class="cart-lines">
          <article v-for="item in cart" :key="item.product.id">
            <div class="cart-product">
              <span>{{ item.product.name.slice(0, 1) }}</span>
              <div>
                <strong>{{ item.product.name }}</strong>
                <small>
                  {{ item.product.product_no }} · {{ formatMoney(item.product.sale_price) }}
                </small>
              </div>
            </div>
            <div class="quantity-control">
              <button @click="changeQuantity(item.product.id, -1)">
                <Minus :size="15" />
              </button>
              <b>{{ item.quantity }}</b>
              <button @click="changeQuantity(item.product.id, 1)">
                <Plus :size="15" />
              </button>
            </div>
            <strong>{{ formatMoney(Number(item.product.sale_price) * item.quantity) }}</strong>
            <button class="remove-button" title="移除" @click="removeProduct(item.product.id)">
              <Trash2 :size="17" />
            </button>
          </article>
        </div>
        <div v-else class="cart-empty"><ShoppingCart :size="28" /><span>尚未扫描商品</span></div>
      </div>

      <aside class="panel checkout-summary">
        <span class="checkout-kicker">CURRENT RECEIPT</span>
        <h2>本次结账</h2>
        <dl>
          <div><dt>商品种类</dt><dd>{{ cart.length }} 种</dd></div>
          <div><dt>商品数量</dt><dd>{{ cartQuantity }} 件</dd></div>
        </dl>
        <div class="amount-due"><span>应收金额</span><strong>{{ formatMoney(cartAmount) }}</strong></div>
        <button
          class="primary-button checkout-button"
          :disabled="!cart.length || checkoutLoading"
          @click="checkout"
        >
          <ReceiptText :size="18" />
          {{ checkoutLoading ? '正在结账…' : '确认结账' }}
        </button>
        <small>结账后将同时生成销售单、销售明细并扣减对应批次库存。</small>
      </aside>
    </section>

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

<style scoped>
.checkout-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 330px;
  gap: 18px;
  margin-bottom: 22px;
}
.checkout-catalog, .checkout-summary { padding: 24px; }
.checkout-title { display: flex; align-items: flex-start; justify-content: space-between; }
.checkout-title svg { color: #c8ff5a; }
.checkout-kicker { color: #c8ff5a; font-size: 11px; font-weight: 800; letter-spacing: .18em; }
.checkout-grid h2 { margin: 5px 0 0; font-size: 24px; }
.checkout-catalog > p, .checkout-summary > small { color: #858a94; }
.scan-row { display: grid; grid-template-columns: 1fr auto; gap: 10px; margin: 22px 0 14px; }
.scan-row select { width: 100%; }
.cart-lines { display: grid; gap: 8px; }
.cart-lines article { display: grid; grid-template-columns: minmax(220px, 1fr) auto 110px 34px; gap: 18px; align-items: center; padding: 13px 14px; background: #101217; border: 1px solid #292c33; border-radius: 10px; }
.cart-product { display: flex; align-items: center; gap: 12px; }
.cart-product > span { display: grid; place-items: center; width: 38px; height: 38px; color: #d7ff8b; background: #29331f; border-radius: 8px; }
.cart-product small { display: block; margin-top: 4px; color: #777d87; }
.quantity-control { display: flex; align-items: center; gap: 9px; }
.quantity-control button, .remove-button { display: grid; place-items: center; width: 30px; height: 30px; padding: 0; color: #b8bdc5; background: #1c1f25; border: 1px solid #343840; border-radius: 7px; }
.quantity-control b { min-width: 20px; text-align: center; }
.remove-button { color: #ff907b; }
.cart-empty { display: grid; place-items: center; gap: 8px; min-height: 120px; color: #6f747d; border: 1px dashed #343840; border-radius: 10px; }
.checkout-summary { display: flex; flex-direction: column; }
.checkout-summary dl { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 24px 0; }
.checkout-summary dl div { padding: 13px; background: #101217; border-radius: 9px; }
.checkout-summary dt { color: #777d87; font-size: 12px; }
.checkout-summary dd { margin: 5px 0 0; font-weight: 700; }
.amount-due { padding-top: 20px; border-top: 1px solid #2b2e35; }
.amount-due span { display: block; color: #858a94; }
.amount-due strong { display: block; margin-top: 7px; color: #c8ff5a; font-size: 34px; }
.checkout-button { justify-content: center; width: 100%; margin: 22px 0 12px; }
@media (max-width: 980px) {
  .checkout-grid { grid-template-columns: 1fr; }
  .cart-lines article { grid-template-columns: 1fr auto; }
  .cart-lines article > strong { text-align: right; }
}
</style>
