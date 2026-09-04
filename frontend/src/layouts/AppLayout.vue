<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  BarChart3,
  Boxes,
  ChevronDown,
  LayoutDashboard,
  LogOut,
  Menu,
  ReceiptText,
  Store,
  Users,
  X,
} from '@lucide/vue'

import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const sidebarOpen = ref(false)

const navItems = computed(() => {
  const items = [
    { to: '/dashboard', label: '店铺总览', icon: LayoutDashboard },
    { to: '/departments/1', label: '部门经营', icon: BarChart3 },
    { to: '/products', label: '商品查询', icon: Boxes },
    { to: '/sales', label: '销售记录', icon: ReceiptText },
  ]
  if (auth.isManager) items.push({ to: '/employees', label: '员工管理', icon: Users })
  return items
})

function isActive(path: string) {
  if (path.startsWith('/departments')) return route.path.startsWith('/departments')
  return route.path === path
}

function logout() {
  auth.signOut()
  router.push('/login')
}
</script>

<template>
  <div class="app-shell">
    <div v-if="sidebarOpen" class="sidebar-scrim" @click="sidebarOpen = false" />
    <aside class="sidebar" :class="{ open: sidebarOpen }">
      <div class="brand-block">
        <div class="brand-mark"><Store :size="22" /></div>
        <div>
          <strong>MarketFlow</strong>
          <span>STORE OPERATIONS</span>
        </div>
        <button class="sidebar-close" type="button" @click="sidebarOpen = false">
          <X :size="20" />
        </button>
      </div>

      <div class="store-chip">
        <span class="live-dot" />
        <div><small>当前门店</small><strong>MarketFlow 本店</strong></div>
        <ChevronDown :size="16" />
      </div>

      <nav class="main-nav">
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
        <div class="employee-avatar">{{ auth.employee?.name?.slice(0, 1) || '员' }}</div>
        <div class="employee-meta">
          <strong>{{ auth.employee?.name || '当前员工' }}</strong>
          <span>{{ auth.employee?.role }} · {{ auth.employee?.employee_no }}</span>
        </div>
        <button class="icon-button dark" title="退出登录" type="button" @click="logout">
          <LogOut :size="18" />
        </button>
      </div>
    </aside>

    <main class="main-area">
      <header class="mobile-bar">
        <button class="icon-button" type="button" @click="sidebarOpen = true">
          <Menu :size="21" />
        </button>
        <strong>MarketFlow</strong>
        <span />
      </header>
      <div class="page-container">
        <RouterView />
      </div>
    </main>
  </div>
</template>
