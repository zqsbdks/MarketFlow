<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Boxes, Building2, PackageCheck, Plus, RefreshCw, Truck } from '@lucide/vue'

import {
  autoReceivePurchases,
  createPurchase,
  createSupplier,
  createSupplierProduct,
  getCategories,
  getDepartments,
  getPurchase,
  getPurchases,
  getSupplierProducts,
  getSuppliers,
  updateSupplierProductStatus,
  updateSupplierStatus,
} from '../api'
import { getErrorMessage } from '../api/http'
import ModalPanel from '../components/ModalPanel.vue'
import PageHeader from '../components/PageHeader.vue'
import { useAuthStore } from '../stores/auth'
import type { Category, Department, Purchase, Supplier, SupplierProduct } from '../types/api'
import { formatMoney } from '../utils'

type Tab = 'purchases' | 'catalog' | 'suppliers'

const auth = useAuthStore()
const activeTab = ref<Tab>('purchases')
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const notice = ref('')
const suppliers = ref<Supplier[]>([])
const catalog = ref<SupplierProduct[]>([])
const purchases = ref<Purchase[]>([])
const departments = ref<Department[]>([])
const categories = ref<Category[]>([])
const detail = ref<Purchase | null>(null)
const detailOpen = ref(false)
const supplierOpen = ref(false)
const catalogOpen = ref(false)
const purchaseOpen = ref(false)

const supplierForm = reactive({ name: '', contact_name: '', phone: '', address: '' })
const catalogForm = reactive({ supplier_id: '', category_id: '', name: '', unit_cost: '', shelf_life_days: 1 })
const purchaseForm = reactive({ department_id: '', items: [{ supplier_product_id: '', quantity: 1 }] })
const canMaintainCatalog = computed(() => auth.isManager || auth.employee?.role === '正式员工')
const activeCatalog = computed(() => catalog.value.filter((item) => item.is_active))

function clearMessages() { error.value = ''; notice.value = '' }

async function loadAll() {
  loading.value = true
  clearMessages()
  try {
    const [supplierPage, catalogPage, purchasePage, departmentRows, categoryRows] = await Promise.all([
      getSuppliers({ page_size: 100 }),
      getSupplierProducts({ page_size: 100 }),
      getPurchases({ page_size: 100 }),
      getDepartments(),
      getCategories(),
    ])
    suppliers.value = supplierPage.items
    catalog.value = catalogPage.items
    purchases.value = purchasePage.items
    departments.value = departmentRows
    categories.value = categoryRows
  } catch (reason) { error.value = getErrorMessage(reason) }
  finally { loading.value = false }
}

async function submitSupplier() {
  saving.value = true; clearMessages()
  try {
    await createSupplier(Object.fromEntries(Object.entries(supplierForm).filter(([, value]) => value)))
    supplierOpen.value = false; notice.value = '供应商创建成功'; await loadAll()
  } catch (reason) { error.value = getErrorMessage(reason) }
  finally { saving.value = false }
}

async function submitCatalog() {
  saving.value = true; clearMessages()
  try {
    await createSupplierProduct({
      supplier_id: Number(catalogForm.supplier_id), category_id: Number(catalogForm.category_id),
      name: catalogForm.name, unit_cost: catalogForm.unit_cost,
      shelf_life_days: catalogForm.shelf_life_days,
    })
    catalogOpen.value = false; notice.value = '目录商品创建成功'; await loadAll()
  } catch (reason) { error.value = getErrorMessage(reason) }
  finally { saving.value = false }
}

function addPurchaseLine() { purchaseForm.items.push({ supplier_product_id: '', quantity: 1 }) }
function removePurchaseLine(index: number) { if (purchaseForm.items.length > 1) purchaseForm.items.splice(index, 1) }

async function submitPurchase() {
  saving.value = true; clearMessages()
  try {
    await createPurchase({
      department_id: Number(purchaseForm.department_id),
      items: purchaseForm.items.map((item) => ({
        supplier_product_id: Number(item.supplier_product_id), quantity: Number(item.quantity),
      })),
    })
    purchaseOpen.value = false; notice.value = '进货单创建成功'; await loadAll()
  } catch (reason) { error.value = getErrorMessage(reason) }
  finally { saving.value = false }
}

async function openPurchase(id: number) {
  clearMessages()
  try { detail.value = await getPurchase(id); detailOpen.value = true }
  catch (reason) { error.value = getErrorMessage(reason) }
}

async function runAutoReceive() {
  saving.value = true; clearMessages()
  try {
    const rows = await autoReceivePurchases()
    notice.value = `自动签收完成，共签收 ${rows.length} 张进货单`
    await loadAll()
  } catch (reason) { error.value = getErrorMessage(reason) }
  finally { saving.value = false }
}

async function toggleSupplier(item: Supplier) {
  try { await updateSupplierStatus(item.id, !item.is_active); await loadAll() }
  catch (reason) { error.value = getErrorMessage(reason) }
}

async function toggleCatalog(item: SupplierProduct) {
  try { await updateSupplierProductStatus(item.id, !item.is_active); await loadAll() }
  catch (reason) { error.value = getErrorMessage(reason) }
}

onMounted(loadAll)
</script>

<template>
  <div>
    <PageHeader eyebrow="PROCUREMENT DESK" title="进货管理" description="从供应商目录下单，在预计到货后统一签收并生成库存批次。">
      <span class="record-count"><Truck :size="17" /> {{ purchases.length }} 张进货单</span>
    </PageHeader>

    <section class="procurement-tabs">
      <button :class="{ active: activeTab === 'purchases' }" @click="activeTab = 'purchases'"><PackageCheck :size="17" />进货单</button>
      <button :class="{ active: activeTab === 'catalog' }" @click="activeTab = 'catalog'"><Boxes :size="17" />供应商品</button>
      <button :class="{ active: activeTab === 'suppliers' }" @click="activeTab = 'suppliers'"><Building2 :size="17" />供应商</button>
    </section>

    <p v-if="error" class="alert error">{{ error }}</p>
    <p v-if="notice" class="alert success">{{ notice }}</p>

    <section v-if="activeTab === 'purchases'" class="panel table-panel">
      <div class="section-bar"><div><small>ARRIVAL QUEUE</small><h2>进货单队列</h2><p class="schedule-note">系统每天 12:00 自动签收；任务遗漏时可由店长手动补执行。</p></div><div class="actions"><button v-if="auth.isManager" class="secondary-button" title="处理已到预计时间但仍待到货的进货单" :disabled="saving" @click="runAutoReceive"><RefreshCw :size="16" />补执行签收</button><button v-if="canMaintainCatalog" class="primary-button" @click="purchaseOpen = true"><Plus :size="16" />新建进货单</button></div></div>
      <div class="table-wrap"><table><thead><tr><th>单号</th><th>部门</th><th>下单 / 预计到货</th><th>商品</th><th>金额</th><th>状态</th><th></th></tr></thead><tbody>
        <tr v-for="item in purchases" :key="item.id"><td><strong>{{ item.purchase_no }}</strong><small class="block">{{ item.created_by_name }}</small></td><td>{{ item.department_name }}</td><td>{{ new Date(item.ordered_at).toLocaleString() }}<small class="block">{{ new Date(item.expected_arrival_at).toLocaleString() }}</small></td><td>{{ item.item_count }} 种 / {{ item.total_quantity }} 件</td><td>{{ formatMoney(item.total_amount) }}</td><td><span :class="['status-badge', item.status]">{{ item.status === 'arrived' ? '已到货' : '待到货' }}</span></td><td><button class="text-button" @click="openPurchase(item.id)">详情</button></td></tr>
        <tr v-if="!loading && !purchases.length"><td colspan="7" class="empty-cell">暂无进货单</td></tr>
      </tbody></table></div>
    </section>

    <section v-else-if="activeTab === 'catalog'" class="panel table-panel">
      <div class="section-bar"><div><small>SUPPLIER CATALOG</small><h2>供应商商品目录</h2></div><button v-if="canMaintainCatalog" class="primary-button" @click="catalogOpen = true"><Plus :size="16" />添加商品</button></div>
      <div class="table-wrap"><table><thead><tr><th>商品</th><th>供应商</th><th>分类</th><th>进货价</th><th>保质期</th><th>状态</th><th></th></tr></thead><tbody>
        <tr v-for="item in catalog" :key="item.id"><td><strong>{{ item.name }}</strong></td><td>{{ item.supplier_name }}</td><td>{{ item.category_name || '未设置' }}</td><td>{{ formatMoney(item.unit_cost) }}</td><td>{{ item.shelf_life_days ? `${item.shelf_life_days} 天` : '未设置' }}</td><td>{{ item.is_active ? '供应中' : '已停用' }}</td><td><button v-if="canMaintainCatalog" class="text-button" @click="toggleCatalog(item)">{{ item.is_active ? '停用' : '启用' }}</button></td></tr>
      </tbody></table></div>
    </section>

    <section v-else class="panel table-panel">
      <div class="section-bar"><div><small>PARTNERS</small><h2>供应商档案</h2></div><button v-if="auth.isManager" class="primary-button" @click="supplierOpen = true"><Plus :size="16" />创建供应商</button></div>
      <div class="table-wrap"><table><thead><tr><th>编号 / 名称</th><th>联系人</th><th>电话</th><th>地址</th><th>状态</th><th></th></tr></thead><tbody>
        <tr v-for="item in suppliers" :key="item.id"><td><strong>{{ item.name }}</strong><small class="block">{{ item.supplier_no }}</small></td><td>{{ item.contact_name || '—' }}</td><td>{{ item.phone || '—' }}</td><td>{{ item.address || '—' }}</td><td>{{ item.is_active ? '合作中' : '已停用' }}</td><td><button v-if="auth.isManager" class="text-button" @click="toggleSupplier(item)">{{ item.is_active ? '停用' : '启用' }}</button></td></tr>
      </tbody></table></div>
    </section>

    <ModalPanel title="创建供应商" :open="supplierOpen" @close="supplierOpen = false"><form class="form-grid" @submit.prevent="submitSupplier"><label>供应商名称<input v-model="supplierForm.name" required /></label><label>联系人<input v-model="supplierForm.contact_name" /></label><label>联系电话<input v-model="supplierForm.phone" /></label><label class="wide">地址<input v-model="supplierForm.address" /></label><button class="primary-button wide" :disabled="saving">确认创建</button></form></ModalPanel>
    <ModalPanel title="添加供应商商品" :open="catalogOpen" @close="catalogOpen = false"><form class="form-grid" @submit.prevent="submitCatalog"><label>供应商<select v-model="catalogForm.supplier_id" required><option value="">请选择</option><option v-for="item in suppliers.filter((row) => row.is_active)" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label>商品分类<select v-model="catalogForm.category_id" required><option value="">请选择</option><option v-for="item in categories" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label>商品名称<input v-model="catalogForm.name" required /></label><label>进货单价<input v-model="catalogForm.unit_cost" type="number" min="0" step="0.01" required /></label><label>默认保质期<input v-model.number="catalogForm.shelf_life_days" type="number" min="1" required /></label><button class="primary-button wide" :disabled="saving">保存目录商品</button></form></ModalPanel>
    <ModalPanel title="创建进货单" :open="purchaseOpen" @close="purchaseOpen = false"><form class="purchase-form" @submit.prevent="submitPurchase"><label>进货部门<select v-model="purchaseForm.department_id" required><option value="">请选择</option><option v-for="item in departments" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><div v-for="(line, index) in purchaseForm.items" :key="index" class="purchase-line"><select v-model="line.supplier_product_id" required><option value="">选择供应商品</option><option v-for="item in activeCatalog" :key="item.id" :value="item.id">{{ item.name }} · {{ item.supplier_name }} · {{ formatMoney(item.unit_cost) }}</option></select><input v-model.number="line.quantity" type="number" min="1" required /><button type="button" class="text-button" @click="removePurchaseLine(index)">移除</button></div><button type="button" class="secondary-button" @click="addPurchaseLine"><Plus :size="15" />增加一项</button><button class="primary-button" :disabled="saving">提交进货单</button><small>每日 12:00 起停止创建；未填日期时按预计到货日和默认保质期计算。</small></form></ModalPanel>
    <ModalPanel title="进货单详情" :open="detailOpen" @close="detailOpen = false"><div v-if="detail" class="detail-sheet"><div class="detail-hero"><span><Truck /></span><div><p>{{ detail.purchase_no }}</p><h3>{{ detail.department_name }}</h3></div></div><dl><div><dt>状态</dt><dd>{{ detail.status === 'arrived' ? '已到货' : '待到货' }}</dd></div><div><dt>总金额</dt><dd>{{ formatMoney(detail.total_amount) }}</dd></div><div><dt>创建人</dt><dd>{{ detail.created_by_name }}</dd></div><div><dt>签收人</dt><dd>{{ detail.received_by_name || '尚未签收' }}</dd></div></dl><div class="detail-items"><div v-for="item in detail.items" :key="item.id"><strong>{{ item.product_name }}</strong><span>{{ item.quantity }} 件 × {{ formatMoney(item.unit_cost) }}</span><b>{{ formatMoney(item.subtotal) }}</b></div></div></div></ModalPanel>
  </div>
</template>

<style scoped>
.procurement-tabs{display:flex;gap:8px;margin-bottom:18px}.procurement-tabs button{display:flex;align-items:center;gap:8px;padding:11px 18px;border:1px solid var(--line);border-radius:12px;background:var(--paper);color:var(--muted);cursor:pointer}.procurement-tabs button.active{background:var(--green);border-color:var(--green);color:#101508;font-weight:800}.section-bar{display:flex;justify-content:space-between;align-items:center;padding:22px 24px;border-bottom:1px solid var(--line)}.section-bar small{color:var(--green);font-weight:800;letter-spacing:.14em}.section-bar h2{margin:5px 0 0}.actions{display:flex;gap:9px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.form-grid label,.purchase-form>label{display:grid;gap:7px;color:var(--muted)}.form-grid input,.form-grid select,.purchase-form input,.purchase-form select{width:100%;padding:11px;border:1px solid var(--line);border-radius:9px;background:var(--paper);color:var(--ink)}.wide{grid-column:1/-1}.purchase-form{display:grid;gap:14px}.purchase-line{display:grid;grid-template-columns:1fr 100px auto;gap:9px;align-items:center}.detail-items{margin-top:18px;border-top:1px solid var(--line)}.detail-items>div{display:grid;grid-template-columns:1fr auto auto;gap:18px;padding:14px 0;border-bottom:1px solid var(--line)}.block{display:block;margin-top:4px;color:var(--muted)}@media(max-width:760px){.section-bar{align-items:flex-start;gap:14px}.actions,.procurement-tabs{flex-wrap:wrap}.form-grid{grid-template-columns:1fr}.wide{grid-column:auto}.purchase-line{grid-template-columns:1fr 80px}.purchase-line button{grid-column:1/-1}}
.schedule-note { margin: 7px 0 0; color: var(--muted); font-size: 12px; }
</style>
