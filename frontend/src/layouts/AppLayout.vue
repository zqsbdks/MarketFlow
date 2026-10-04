<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  BarChart3,
  ChartNoAxesCombined,
  BadgePercent,
  Boxes,
  Layers3,
  History,
  ChevronDown,
  LayoutDashboard,
  LogOut,
  Menu,
  ReceiptText,
  ScanLine,
  Truck,
  Store,
  Users,
  X,
} from '@lucide/vue'

import { useAuthStore } from '../stores/auth'
import { useStoreScope } from '../stores/storeScope'
import AiChatWidget from '../components/AiChatWidget.vue'
import LanguageSwitcher from '../components/LanguageSwitcher.vue'
import ThemeSwitcher from '../components/ThemeSwitcher.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const scope = useStoreScope()
const sidebarOpen = ref(false)
const navigationMedia = window.matchMedia('(max-width: 1000px)')
const compactNavigation = ref(navigationMedia.matches)
function updateNavigationSize() {
  compactNavigation.value = navigationMedia.matches
  if (!compactNavigation.value) sidebarOpen.value = false
}
let employeeRefresh: ReturnType<typeof setInterval> | undefined

async function refreshAssignment() {
  const previous = auth.employee?.store_id
  try {
    await auth.refreshEmployee()
    if (previous !== auth.employee?.store_id) {
      await scope.load()
      if (auth.employee?.store_id) scope.choose(auth.employee.store_id)
    }
  } catch {
    // 路由和服务端会继续检查登录状态。
  }
}

onMounted(async () => {
  navigationMedia.addEventListener('change', updateNavigationSize)
  try { await scope.load() } catch { /* 页面其他查询会显示具体错误。 */ }
  employeeRefresh = setInterval(() => { void refreshAssignment() }, 60_000)
})
onUnmounted(() => {
  if (employeeRefresh) clearInterval(employeeRefresh)
  navigationMedia.removeEventListener('change', updateNavigationSize)
})

const navItems = computed(() => {
  const items = [
    { to: '/dashboard', label: '店铺总览', icon: LayoutDashboard },
    { to: '/contact-notices', label: '联络事项', icon: ReceiptText },
    { to: '/departments/1', label: '部门经营', icon: BarChart3 },
    { to: '/analytics', label: '经营分析', icon: ChartNoAxesCombined },
    { to: '/products', label: '商品查询', icon: Boxes },
    { to: '/discount-rules', label: '折扣管理', icon: BadgePercent },
    { to: '/sales', label: '销售记录', icon: ReceiptText },
    { to: '/procurement', label: '进货管理', icon: Truck },
    { to: '/inventory-batches', label: '库存批次', icon: Layers3 },
  ]
  if (scope.canWriteStore) items.push({ to: '/shopping', label: '模拟购物', icon: ScanLine })
  if (auth.isManager && scope.canWriteStore) {
    items.push({ to: '/inventory-movements', label: '库存流水', icon: History })
    items.push({ to: '/employees', label: '员工管理', icon: Users })
  }
  if (auth.isHeadquarters) items.push({ to: '/stores', label: '门店与总部', icon: Store })
  if (auth.employee) items.push({ to: `/employees/${auth.employee.id}`, label: '我的档案', icon: Users })
  return items
})

function isActive(path: string) {
  if (path.startsWith('/departments')) return route.path.startsWith('/departments')
  return route.path === path
}

async function logout() {
  await auth.signOut()
  scope.clear()
  router.push('/login')
}
</script>

<template>
  <div class="app-shell">
    <div v-if="sidebarOpen" class="sidebar-scrim" @click="sidebarOpen = false" />
    <aside class="sidebar" :class="{ open: sidebarOpen }" :inert="compactNavigation && !sidebarOpen" @keydown.esc="sidebarOpen = false">
      <div class="brand-block">
        <div class="brand-mark"><Store :size="22" /></div>
        <div>
          <strong>MarketFlow</strong>
          <span>STORE OPERATIONS</span>
        </div>
        <button class="sidebar-close" type="button" aria-label="关闭菜单" @click="sidebarOpen = false">
          <X :size="20" />
        </button>
      </div>

      <div class="store-chip">
        <span class="live-dot" />
        <div><small>查询门店</small><strong :data-no-translate="scope.selected?.name ? '' : undefined">{{ scope.selected?.store_no }} {{ scope.selected?.name || '加载中' }}</strong></div>
        <select :value="scope.selectedId ?? ''" aria-label="选择查询门店" @change="scope.choose(Number(($event.target as HTMLSelectElement).value))">
          <option v-for="store in scope.stores.filter((item) => item.is_active)" :key="store.id" :value="store.id">{{ store.store_no }} {{ store.name }}</option>
        </select>
        <ChevronDown :size="16" />
      </div>

      <nav id="main-navigation" class="main-nav">
        <p>经营工作台</p>
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          :class="{ active: isActive(item.to) }"
          @click="sidebarOpen = false"
        >
          <component :is="item.icon" :size="19" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <div class="sidebar-footer">
        <LanguageSwitcher />
        <ThemeSwitcher />
        <div class="employee-avatar">{{ auth.employee?.name?.slice(0, 1) || '员' }}</div>
        <div class="employee-meta">
          <strong v-if="auth.employee?.name" data-no-translate>{{ auth.employee.name }}</strong>
          <strong v-else>当前员工</strong>
          <span>{{ auth.employee?.role }} · {{ auth.employee?.employee_no }}</span>
        </div>
        <button class="icon-button dark" title="退出登录" type="button" @click="logout">
          <LogOut :size="18" />
        </button>
      </div>
    </aside>

    <main class="main-area">
      <header class="mobile-bar">
        <button class="icon-button" type="button" aria-label="打开菜单" :aria-expanded="sidebarOpen" aria-controls="main-navigation" @click="sidebarOpen = true">
          <Menu :size="21" />
        </button>
        <strong>MarketFlow</strong>
        <LanguageSwitcher />
        <ThemeSwitcher />
      </header>
      <div class="page-container">
        <p v-if="!scope.canWriteStore" class="store-readonly-banner">{{ auth.isHeadquarters ? '总部账号：门店业务仅供查看' : '正在查看其他门店：不能修改该店业务数据' }}</p>
        <RouterView :key="`${route.fullPath}:${scope.selectedId}`" />
      </div>
    </main>
    <AiChatWidget v-if="auth.isAuthenticated && !auth.employee?.must_change_password" :key="`${auth.employee?.id}:${scope.selectedId}`" />
  </div>
</template>
