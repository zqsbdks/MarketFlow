<script setup lang="ts">
import { X } from '@lucide/vue'

defineProps<{ title: string; open: boolean }>()
defineEmits<{ close: [] }>()
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="modal-backdrop" @click.self="$emit('close')">
      <section class="modal-panel" role="dialog" aria-modal="true">
        <header>
          <h2>{{ title }}</h2>
          <button class="icon-button" type="button" aria-label="关闭" @click="$emit('close')">
            <X :size="20" />
          </button>
        </header>
        <div class="modal-content"><slot /></div>
      </section>
    </div>
  </Teleport>
</template>
