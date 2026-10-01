<script setup lang="ts">
import { computed } from 'vue'

import { language, setLanguage, type Language } from '../i18n'

const selected = computed<Language>({
  get: () => language.value,
  set: (value) => setLanguage(value),
})
</script>

<template>
  <label class="language-switcher" data-no-translate>
    <span class="sr-only">Language / 言語 / 语言</span>
    <select v-model="selected" aria-label="Language / 言語 / 语言">
      <option value="ja">日本語</option>
      <option value="en">English</option>
      <option value="zh">中文</option>
    </select>
  </label>
</template>

<style scoped>
.language-switcher select {
  color: var(--text-primary, #eef1f5);
  background: #181c23;
  border: 1px solid #343943;
  border-radius: 8px;
  padding: 6px 8px;
  font-size: 12px;
  cursor: pointer;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
}
</style>
