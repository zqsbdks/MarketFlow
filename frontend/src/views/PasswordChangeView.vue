<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { KeyRound, ShieldCheck, Store } from '@lucide/vue'

import { changePassword } from '../api'
import { getErrorMessage } from '../api/http'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  if (newPassword.value !== confirmPassword.value) {
    error.value = '两次输入的新密码不一致'
    return
  }
  loading.value = true
  try {
    await changePassword(oldPassword.value, newPassword.value)
    await auth.refreshEmployee()
    await router.push('/dashboard')
  } catch (reason) {
    error.value = getErrorMessage(reason)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="password-page">
    <div class="password-shell">
      <div class="login-brand dark-text"><Store :size="24" /><strong>MarketFlow</strong></div>
      <section class="password-card">
        <div class="password-icon"><ShieldCheck :size="26" /></div>
        <p class="eyebrow">FIRST LOGIN SECURITY</p>
        <h1>先设置你的新密码</h1>
        <p>这是该账号首次登录。完成密码修改后，才可以进入经营管理台。</p>
        <form @submit.prevent="submit">
          <label><span>当前临时密码</span><input v-model="oldPassword" type="password" required /></label>
          <label><span>新密码</span><input v-model="newPassword" type="password" minlength="3" required /></label>
          <label><span>确认新密码</span><input v-model="confirmPassword" type="password" required /></label>
          <p v-if="error" class="form-error">{{ error }}</p>
          <button class="primary-button full" :disabled="loading">
            <KeyRound :size="18" />{{ loading ? '正在保存…' : '保存新密码并进入' }}
          </button>
        </form>
      </section>
    </div>
  </main>
</template>
