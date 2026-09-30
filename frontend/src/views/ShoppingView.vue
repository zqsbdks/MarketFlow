<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  Minus,
  Plus,
  ReceiptText,
  ScanLine,
  ShoppingCart,
  Trash2,
} from '@lucide/vue'

import { createSale, getProducts, previewSalePrice } from '../api'
import { getErrorMessage } from '../api/http'
import ModalPanel from '../components/ModalPanel.vue'
import PageHeader from '../components/PageHeader.vue'
import type { ProductListItem, SaleDetail, SalePricePreview } from '../types/api'
import { formatDateTime, formatMoney } from '../utils'

// region 页面状态
const products = ref<ProductListItem[]>([])
const selectedProductId = ref<number | ''>('')
const cart = ref<Array<{ product: ProductListItem; quantity: number }>>([])
const pricePreview = ref<SalePricePreview | null>(null)
const completedSale = ref<SaleDetail | null>(null)
const receiptOpen = ref(false)
const loadingProducts = ref(false)
const previewLoading = ref(false)
const checkoutLoading = ref(false)
const error = ref('')
const scanMessage = ref('请选择商品，然后点击“模拟扫码”录入购物车。')
let latestPreviewRequest = 0

const cartQuantity = computed(() => {
  let quantity = 0
  for (const item of cart.value) quantity += item.quantity
  return quantity
})

const cartOriginalAmount = computed(() => {
  let amount = 0
  for (const item of cart.value) amount += Number(item.product.sale_price) * item.quantity
  return amount
})

const amountDue = computed(() => {
  if (pricePreview.value !== null) return Number(pricePreview.value.total_amount)
  return cartOriginalAmount.value
})

const previewItems = computed(() => {
  const items = new Map<number, SaleDetail['items'][number]>()
  if (pricePreview.value !== null) {
    for (const item of pricePreview.value.items) items.set(item.product_id, item)
  }
  return items
})
// endregion


// region 加载可销售商品
async function loadProducts() {
  loadingProducts.value = true
  try {
    const result = await getProducts({ page: 1, page_size: 100, status: 'on_sale' })
    products.value = []
    for (const product of result.items) {
      if (product.batch_stock_quantity > 0) products.value.push(product)
    }
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    loadingProducts.value = false
  }
}
// endregion


// region 模拟扫码录入商品
function scanSelectedProduct() {
  if (selectedProductId.value === '') {
    scanMessage.value = '请先选择需要扫描的商品。'
    return
  }

  let selectedProduct: ProductListItem | undefined
  for (const product of products.value) {
    if (product.id === selectedProductId.value) {
      selectedProduct = product
      break
    }
  }
  if (selectedProduct === undefined) return

  let existingItem: { product: ProductListItem; quantity: number } | undefined
  for (const item of cart.value) {
    if (item.product.id === selectedProduct.id) {
      existingItem = item
      break
    }
  }

  if (existingItem !== undefined) existingItem.quantity += 1
  else cart.value.push({ product: selectedProduct, quantity: 1 })

  scanMessage.value = `已扫描：${selectedProduct.product_no} · ${selectedProduct.name}`
}

function changeQuantity(productId: number, difference: number) {
  for (const item of cart.value) {
    if (item.product.id !== productId) continue
    item.quantity += difference
    if (item.quantity <= 0) removeProduct(productId)
    return
  }
}

function removeProduct(productId: number) {
  const remainingItems: Array<{ product: ProductListItem; quantity: number }> = []
  for (const item of cart.value) {
    if (item.product.id !== productId) remainingItems.push(item)
  }
  cart.value = remainingItems
}

function clearCart() {
  cart.value = []
  scanMessage.value = '购物车已清空，可以继续模拟扫码。'
}
// endregion


// region 实时计算折扣价格
async function refreshPricePreview() {
  const requestNumber = ++latestPreviewRequest
  if (cart.value.length === 0) {
    pricePreview.value = null
    previewLoading.value = false
    return
  }

  previewLoading.value = true
  try {
    const requestItems: Array<{ product_id: number; quantity: number }> = []
    for (const item of cart.value) {
      requestItems.push({ product_id: item.product.id, quantity: item.quantity })
    }
    const result = await previewSalePrice(requestItems)

    // 购物车连续变化时，只接收最后一次请求的结果，避免旧价格覆盖新价格。
    if (requestNumber === latestPreviewRequest) {
      pricePreview.value = result
      error.value = ''
    }
  } catch (reason) {
    if (requestNumber === latestPreviewRequest) {
      pricePreview.value = null
      error.value = getErrorMessage(reason)
    }
  } finally {
    if (requestNumber === latestPreviewRequest) previewLoading.value = false
  }
}
// endregion


// region 确认结账
async function checkout() {
  if (cart.value.length === 0) return

  checkoutLoading.value = true
  error.value = ''
  try {
    const requestItems: Array<{ product_id: number; quantity: number }> = []
    for (const item of cart.value) {
      requestItems.push({ product_id: item.product.id, quantity: item.quantity })
    }
    completedSale.value = await createSale(requestItems)
    cart.value = []
    selectedProductId.value = ''
    scanMessage.value = '结账成功，可以开始下一次模拟购物。'
    receiptOpen.value = true
    await loadProducts()
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    checkoutLoading.value = false
  }
}
// endregion


watch(cart, refreshPricePreview, { deep: true })
onMounted(loadProducts)
</script>

<template>
  <div>
    <PageHeader
      eyebrow="SIMULATED SHOPPING"
      title="模拟购物"
      description="模拟顾客挑选商品、收银台扫码、折扣计算和最终结账的完整过程。"
    >
      <span class="record-count"><ShoppingCart :size="17" />购物车 {{ cartQuantity }} 件</span>
    </PageHeader>

    <section class="shopping-layout">
      <div class="shopping-main">
        <article class="panel scanner-panel">
          <div class="panel-heading scanner-heading">
            <div>
              <span class="checkout-kicker">BARCODE SCANNER</span>
              <h2>模拟扫码录入</h2>
              <p>选择一个可销售商品，每点击一次扫码按钮，就向购物车增加一件。</p>
            </div>
            <div class="scanner-icon"><ScanLine :size="30" /></div>
          </div>

          <div class="scan-row">
            <select v-model="selectedProductId" :disabled="loadingProducts" @keyup.enter="scanSelectedProduct">
              <option value="">{{ loadingProducts ? '正在加载商品…' : '选择商品编号或名称' }}</option>
              <option v-for="product in products" :key="product.id" :value="product.id">
                {{ product.product_no }} · {{ product.name }} · {{ formatMoney(product.sale_price) }} · 库存 {{ product.batch_stock_quantity }}
              </option>
            </select>
            <button class="primary-button scan-button" :disabled="selectedProductId === ''" @click="scanSelectedProduct">
              <ScanLine :size="18" />模拟扫码
            </button>
          </div>
          <div class="scan-result"><span class="live-dot" />{{ scanMessage }}</div>
        </article>

        <article class="panel cart-panel">
          <div class="cart-heading">
            <div>
              <span class="checkout-kicker">SHOPPING CART</span>
              <h2>购物车商品</h2>
            </div>
            <button v-if="cart.length" class="text-button muted" @click="clearCart">
              <Trash2 :size="15" />清空购物车
            </button>
          </div>

          <div v-if="cart.length" class="cart-lines">
            <article v-for="item in cart" :key="item.product.id">
              <div class="cart-product">
                <span>{{ item.product.name.slice(0, 1) }}</span>
                <div>
                  <strong>{{ item.product.name }}</strong>
                  <small>{{ item.product.product_no }} · 可售库存 {{ item.product.batch_stock_quantity }}</small>
                  <small v-if="previewItems.get(item.product.id)?.discount_rule_name" class="discount-name">
                    {{ previewItems.get(item.product.id)?.discount_rule_name }}
                  </small>
                </div>
              </div>

              <div class="price-cell">
                <small>单价</small>
                <s v-if="previewItems.get(item.product.id)?.discount_rule_id">
                  {{ formatMoney(item.product.sale_price) }}
                </s>
                <strong>{{ formatMoney(previewItems.get(item.product.id)?.unit_price ?? item.product.sale_price) }}</strong>
              </div>

              <div class="quantity-control">
                <button title="减少一件" @click="changeQuantity(item.product.id, -1)"><Minus :size="15" /></button>
                <b>{{ item.quantity }}</b>
                <button title="增加一件" @click="changeQuantity(item.product.id, 1)"><Plus :size="15" /></button>
              </div>

              <div class="line-total">
                <small>小计</small>
                <strong>{{ formatMoney(previewItems.get(item.product.id)?.subtotal ?? Number(item.product.sale_price) * item.quantity) }}</strong>
                <span v-if="Number(previewItems.get(item.product.id)?.discount_amount ?? 0) > 0">
                  已优惠 {{ formatMoney(previewItems.get(item.product.id)?.discount_amount ?? 0) }}
                </span>
              </div>

              <button class="remove-button" title="删除商品" @click="removeProduct(item.product.id)">
                <Trash2 :size="17" />
              </button>
            </article>
          </div>
          <div v-else class="cart-empty">
            <ShoppingCart :size="34" />
            <strong>购物车还是空的</strong>
            <span>从上方选择商品并点击模拟扫码</span>
          </div>
        </article>
      </div>

      <aside class="panel checkout-summary">
        <span class="checkout-kicker">CURRENT RECEIPT</span>
        <h2>本次结账</h2>
        <dl>
          <div><dt>商品种类</dt><dd>{{ cart.length }} 种</dd></div>
          <div><dt>商品数量</dt><dd>{{ cartQuantity }} 件</dd></div>
          <div><dt>原价合计</dt><dd>{{ formatMoney(pricePreview?.original_total_amount ?? cartOriginalAmount) }}</dd></div>
          <div><dt>优惠金额</dt><dd class="discount-value">-{{ formatMoney(pricePreview?.discount_amount ?? 0) }}</dd></div>
        </dl>
        <div class="amount-due">
          <span>{{ previewLoading ? '正在计算最新折扣…' : '应收金额' }}</span>
          <strong>{{ formatMoney(amountDue) }}</strong>
        </div>
        <button
          class="primary-button checkout-button"
          :disabled="cart.length === 0 || checkoutLoading || previewLoading"
          @click="checkout"
        >
          <ReceiptText :size="18" />
          {{ checkoutLoading ? '正在结账…' : '确认结账' }}
        </button>
        <small>确认后会重新验证折扣、扣减批次库存，并生成销售单和销售明细。</small>
      </aside>
    </section>

    <p v-if="error" class="alert error">{{ error }}</p>

    <ModalPanel title="结账成功" :open="receiptOpen" @close="receiptOpen = false">
      <div v-if="completedSale" class="receipt-sheet">
        <div class="receipt-head">
          <div><p>销售单号</p><strong>{{ completedSale.sale_no }}</strong></div>
          <div><p>销售时间</p><strong>{{ formatDateTime(completedSale.sold_at) }}</strong></div>
        </div>
        <div class="receipt-lines">
          <div v-for="item in completedSale.items" :key="`${item.product_id}-${item.unit_price}-${item.discount_rule_id}`">
            <div>
              <strong>{{ item.product_name }}</strong>
              <span><s v-if="Number(item.discount_amount) > 0">{{ formatMoney(item.original_unit_price) }}</s> {{ formatMoney(item.unit_price) }} × {{ item.quantity }}</span>
              <small v-if="item.discount_rule_name" class="discount-name">{{ item.discount_rule_name }}</small>
            </div>
            <b>{{ formatMoney(item.subtotal) }}</b>
          </div>
        </div>
        <div class="receipt-total"><span>原价合计</span><strong>{{ formatMoney(completedSale.original_total_amount) }}</strong></div>
        <div v-if="Number(completedSale.discount_amount) > 0" class="receipt-total"><span>优惠金额</span><strong class="discount-value">-{{ formatMoney(completedSale.discount_amount) }}</strong></div>
        <div class="receipt-total final-total"><span>实际支付</span><strong>{{ formatMoney(completedSale.total_amount) }}</strong></div>
      </div>
    </ModalPanel>
  </div>
</template>

<style scoped>
.shopping-layout { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 18px; align-items: start; }
.shopping-main { display: grid; gap: 18px; }
.scanner-panel, .cart-panel, .checkout-summary { padding: 24px; }
.scanner-heading, .cart-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
.scanner-heading h2, .cart-heading h2, .checkout-summary h2 { margin: 5px 0 0; font-size: 24px; }
.scanner-heading p { margin: 8px 0 0; color: #858a94; }
.scanner-icon { display: grid; place-items: center; width: 54px; height: 54px; color: #c8ff5a; background: #26331d; border: 1px solid #40532d; border-radius: 12px; }
.checkout-kicker { color: #c8ff5a; font-size: 11px; font-weight: 800; letter-spacing: .18em; }
.scan-row { display: grid; grid-template-columns: 1fr auto; gap: 10px; margin: 24px 0 12px; }
.scan-row select { width: 100%; }
.scan-button { min-width: 138px; justify-content: center; }
.scan-result { display: flex; align-items: center; gap: 9px; padding: 11px 13px; color: #aab0a7; background: #101217; border: 1px solid #292c33; border-radius: 8px; font-size: 12px; }
.cart-heading { align-items: center; margin-bottom: 16px; }
.cart-heading button { display: inline-flex; align-items: center; gap: 6px; }
.cart-lines { display: grid; gap: 9px; }
.cart-lines > article { display: grid; grid-template-columns: minmax(220px, 1fr) 125px auto 120px 34px; gap: 18px; align-items: center; padding: 14px; background: #101217; border: 1px solid #292c33; border-radius: 10px; }
.cart-product { display: flex; align-items: center; gap: 12px; }
.cart-product > span { display: grid; place-items: center; flex: 0 0 auto; width: 40px; height: 40px; color: #d7ff8b; background: #29331f; border-radius: 9px; }
.cart-product small, .price-cell small, .line-total small { display: block; margin-top: 4px; color: #777d87; }
.discount-name { color: #c8ff5a !important; }
.price-cell strong, .price-cell s { display: block; }
.price-cell s { color: #707680; font-size: 12px; }
.quantity-control { display: flex; align-items: center; gap: 9px; }
.quantity-control button, .remove-button { display: grid; place-items: center; width: 30px; height: 30px; padding: 0; color: #b8bdc5; background: #1c1f25; border: 1px solid #343840; border-radius: 7px; }
.quantity-control b { min-width: 20px; text-align: center; }
.line-total strong { display: block; }
.line-total span { color: #ff9a87; font-size: 11px; }
.remove-button { color: #ff907b; }
.cart-empty { display: grid; place-items: center; gap: 7px; min-height: 220px; color: #6f747d; border: 1px dashed #343840; border-radius: 10px; }
.cart-empty strong { color: #aeb3bc; }
.cart-empty span { font-size: 12px; }
.checkout-summary { position: sticky; top: 104px; display: flex; flex-direction: column; }
.checkout-summary dl { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 24px 0; }
.checkout-summary dl div { padding: 13px; background: #101217; border-radius: 9px; }
.checkout-summary dt { color: #777d87; font-size: 12px; }
.checkout-summary dd { margin: 5px 0 0; font-weight: 700; }
.checkout-summary > small { color: #858a94; }
.discount-value { color: #ff907b; }
.amount-due { padding-top: 20px; border-top: 1px solid #2b2e35; }
.amount-due span { display: block; color: #858a94; }
.amount-due strong { display: block; margin-top: 7px; color: #c8ff5a; font-size: 36px; }
.checkout-button { justify-content: center; width: 100%; margin: 22px 0 12px; }
.receipt-lines .discount-name { display: block; margin-top: 4px; }
.final-total { margin-top: 12px; border-top: 1px solid #2b2e35; }
@media (max-width: 1100px) {
  .shopping-layout { grid-template-columns: 1fr; }
  .checkout-summary { position: static; }
}
@media (max-width: 760px) {
  .scan-row { grid-template-columns: 1fr; }
  .cart-lines > article { grid-template-columns: 1fr auto; }
  .price-cell, .line-total { text-align: right; }
}
</style>
