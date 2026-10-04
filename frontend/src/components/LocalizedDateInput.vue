<script setup lang="ts">
import { computed, useAttrs } from 'vue'
import { displayLocale } from '../utils'

defineOptions({ inheritAttrs: false })
const props = withDefaults(defineProps<{
  modelValue?: string | null
  type?: 'date' | 'datetime-local'
}>(), { modelValue: '', type: 'date' })
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const attrs = useAttrs()
const caption = computed(() => {
  if (!props.modelValue) return props.type === 'date' ? 'YYYY-MM-DD' : 'YYYY-MM-DD HH:mm'
  const value = props.type === 'date' ? `${props.modelValue}T00:00:00Z` : `${props.modelValue}Z`
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return props.modelValue
  return new Intl.DateTimeFormat(displayLocale(), {
    year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'UTC',
    ...(props.type === 'datetime-local' ? { hour: '2-digit', minute: '2-digit', hour12: false } : {}),
  }).format(date)
})
</script>

<template>
  <span class="locale-date-input" :class="attrs.class">
    <input v-bind="attrs" :type="type" :value="modelValue ?? ''"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)" />
    <span class="locale-date-caption" data-no-translate aria-hidden="true">{{ caption }}</span>
  </span>
</template>

<style scoped>
.locale-date-input { display: inline-block; position: relative; min-width: 0; }
.locale-date-input input { width: 100%; color: transparent !important; caret-color: transparent; }
.locale-date-input input::-webkit-datetime-edit { opacity: 0; }
.locale-date-caption { position: absolute; inset: 0 34px 0 12px; display: flex; align-items: center;
  color: var(--ink); font: inherit; font-size: 13px; pointer-events: none; white-space: nowrap; overflow: hidden; }
.locale-date-input:has(input:disabled) { opacity: .55; }
</style>
