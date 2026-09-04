<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, BarChart3, Boxes, Eye, EyeOff, LockKeyhole, Store } from '@lucide/vue'

import { getErrorMessage } from '../api/http'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const employeeNo = ref('')
const password = ref('')
const showPassword = ref(false)
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  loading.value = true
  try {
    const employee = await auth.signIn(employeeNo.value.trim(), password.value)
    if (employee.must_change_password) {
      await router.push('/change-password')
    } else {
      const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
      await router.push(redirect)
    }
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-story">
      <div class="login-brand"><Store :size="24" /><strong>MarketFlow</strong></div>
      <div class="story-copy">
        <p class="eyebrow light">RETAIL OPERATING SYSTEM / 01</p>
        <h1>掌控门店<br /><em>每一次流动</em></h1>
        <p>销售、商品、部门与团队，在同一个实时经营界面中保持清晰。</p>
      </div>
      <div class="story-metrics">
        <div><b>04</b><span>经营部门</span></div>
        <div><BarChart3 :size="21" /><span>实时经营概览</span></div>
        <div><Boxes :size="21" /><span>商品库存脉搏</span></div>
      </div>
      <p class="story-footnote">MARKETFLOW · RETAIL OPERATIONS SYSTEM</p>
    </section>

    <section class="login-form-side">
      <form class="login-card" @submit.prevent="submit">
        <div class="mobile-login-brand"><Store :size="22" /><strong>MarketFlow</strong></div>
        <p class="eyebrow">SECURE ACCESS</p>
        <h2>登录工作台</h2>
        <p class="form-intro">使用门店分配的员工凭据继续。</p>

        <label>
          <span>员工编号</span>
          <input v-model="employeeNo" autocomplete="username" placeholder="例如 E00001" required />
        </label>
        <label>
          <span>登录密码</span>
          <div class="password-input">
            <LockKeyhole :size="18" />
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              autocomplete="current-password"
              placeholder="请输入密码"
              required
            />
            <button type="button" @click="showPassword = !showPassword">
              <EyeOff v-if="showPassword" :size="18" />
              <Eye v-else :size="18" />
            </button>
          </div>
        </label>

        <p v-if="error" class="form-error">{{ error }}</p>
        <button class="primary-button login-submit" type="submit" :disabled="loading">
          <span>{{ loading ? '正在验证…' : '进入经营台' }}</span>
          <ArrowRight :size="18" />
        </button>
        <p class="security-note">账号由店长统一创建。如无法登录，请联系门店管理员。</p>
      </form>
    </section>
  </main>
</template>
