<script setup lang="ts">
import type { Component } from 'vue'

defineProps<{
  label: string
  value: string
  hint: string
  icon: Component
  tone?: 'green' | 'orange' | 'blue' | 'ink'
}>()
</script>

<template>
  <article class="stat-card" :class="`tone-${tone || 'green'}`">
    <div class="stat-icon"><component :is="icon" :size="19" /></div>
    <p>{{ label }}</p>
    <strong>{{ value }}</strong>
    <span>{{ hint }}</span>
  </article>
</template>
