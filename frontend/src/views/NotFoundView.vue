<script setup lang="ts">
import { ArrowLeft, Store } from '@lucide/vue'
</script>

<template>
  <main class="not-found">
    <Store :size="34" />
    <p class="eyebrow">ERROR 404</p>
    <h1>这条通道还没有开业</h1>
    <p>你访问的页面不存在，返回经营管理台继续工作。</p>
    <RouterLink class="primary-button" to="/dashboard"><ArrowLeft :size="18" />返回店铺总览</RouterLink>
  </main>
</template>
