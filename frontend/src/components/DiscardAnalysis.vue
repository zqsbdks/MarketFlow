<script setup lang="ts">
import type { LossAnalysisGroup } from '../types/api'
import { formatMoney } from '../utils'
defineProps<{ groups: { title: string; items: LossAnalysisGroup[]; literal: boolean }[]; showTables: boolean; showCharts: boolean }>()
</script>

<template>
  <section v-if="groups.length" class="loss-groups">
    <article v-for="group in groups" :key="group.title" class="panel loss-panel">
      <h2>{{ group.title }}</h2>
      <p v-if="!group.items.length" class="empty-row">所选日期内暂无废弃记录</p>
      <template v-else>
        <div v-if="showTables" class="table-scroll"><table class="data-table">
          <thead><tr><th>名称</th><th>废弃数量</th><th>损耗金额</th><th>成本占比</th></tr></thead>
          <tbody><tr v-for="item in group.items" :key="item.key"><td :data-no-translate="group.literal ? '' : undefined">{{ item.name }}</td><td>{{ item.quantity }}</td><td>{{ formatMoney(item.cost) }}</td><td>{{ item.cost_share }}%</td></tr></tbody>
        </table></div>
        <div v-if="showCharts" class="loss-bars">
          <div v-for="item in group.items" :key="item.key" class="loss-bar">
            <span :data-no-translate="group.literal ? '' : undefined">{{ item.name }}</span>
            <meter min="0" max="100" :value="Number(item.cost_share)" :aria-label="item.name" />
            <strong>{{ formatMoney(item.cost) }} · {{ item.cost_share }}%</strong>
          </div>
        </div>
      </template>
    </article>
  </section>
</template>

<style scoped>
.loss-groups { display: grid; gap: 18px; margin: 22px 0; }
.loss-panel { padding: 24px; min-width: 0; }
.table-scroll { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; }
th, td { padding: 12px; text-align: left; border-bottom: 1px solid var(--line); white-space: nowrap; }
.loss-bars { display: grid; gap: 14px; margin-top: 20px; }
.loss-bar { display: grid; grid-template-columns: minmax(100px, 1fr) 2fr auto; gap: 16px; align-items: center; }
.loss-bar span, .loss-bar strong { overflow-wrap: anywhere; min-width: 0; }
meter { width: 100%; min-width: 0; accent-color: var(--green); }
@media (max-width: 600px) { .loss-panel { padding: 16px; } .loss-bar { grid-template-columns: 1fr 1fr; } .loss-bar strong { grid-column: 1 / -1; } }
</style>
