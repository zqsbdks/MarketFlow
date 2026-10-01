<script setup lang="ts">
import { Moon, Sun } from '@lucide/vue'

import { setTheme, theme } from '../theme'

function toggleTheme() {
  setTheme(theme.value === 'dark' ? 'light' : 'dark')
}
</script>

<template>
  <button
    class="theme-switcher"
    type="button"
    :title="theme === 'dark' ? '切换到日间模式' : '切换到夜间模式'"
    :aria-label="theme === 'dark' ? '切换到日间模式' : '切换到夜间模式'"
    @click="toggleTheme"
  >
    <Sun v-if="theme === 'dark'" :size="17" />
    <Moon v-else :size="17" />
  </button>
</template>

<style scoped>
.theme-switcher {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  width: 34px;
  height: 34px;
  padding: 0;
  color: var(--muted);
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
}
.theme-switcher:hover { color: var(--green); border-color: var(--green); }
</style>
