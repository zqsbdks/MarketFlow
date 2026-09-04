import { createRouter, createWebHistory } from 'vue-router'

import AppLayout from '../layouts/AppLayout.vue'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { public: true, title: '员工登录' },
    },
    {
      path: '/change-password',
      name: 'change-password',
      component: () => import('../views/PasswordChangeView.vue'),
      meta: { title: '修改初始密码' },
    },
    {
      path: '/',
      component: AppLayout,
      children: [
        { path: '', redirect: '/dashboard' },
        {
          path: 'dashboard',
          name: 'dashboard',
          component: () => import('../views/DashboardView.vue'),
          meta: { title: '店铺总览' },
        },
        {
          path: 'departments/:id',
          name: 'department',
          component: () => import('../views/DepartmentView.vue'),
          meta: { title: '部门经营' },
        },
        {
          path: 'products',
          name: 'products',
          component: () => import('../views/ProductsView.vue'),
          meta: { title: '商品查询' },
        },
        {
          path: 'sales',
          name: 'sales',
          component: () => import('../views/SalesView.vue'),
          meta: { title: '销售记录' },
        },
        {
          path: 'employees',
          name: 'employees',
          component: () => import('../views/EmployeesView.vue'),
          meta: { title: '员工管理', managerOnly: true },
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      component: () => import('../views/NotFoundView.vue'),
      meta: { public: true, title: '页面不存在' },
    },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  document.title = `${String(to.meta.title || '经营管理台')} · MarketFlow`

  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && auth.isAuthenticated) {
    return auth.employee?.must_change_password ? '/change-password' : '/dashboard'
  }
  if (to.meta.managerOnly && !auth.isManager) {
    return '/dashboard'
  }
  if (
    auth.employee?.must_change_password &&
    to.name !== 'change-password' &&
    to.name !== 'login'
  ) {
    return '/change-password'
  }
  return true
})

export default router
