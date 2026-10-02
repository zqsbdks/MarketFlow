<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { getNoticeSummary } from "../api/contactNotices";
import { language } from "../i18n";
const pending = ref(0),
  unread = ref(0);
let timer: ReturnType<typeof setInterval> | undefined;
async function refresh() {
  try {
    const summary = await getNoticeSummary();
    pending.value = summary.pending;
    unread.value = summary.unread;
  } catch {
    /* 主页面正常使用，下次轮询重试。 */
  }
}
onMounted(() => {
  void refresh();
  timer = setInterval(refresh, 60000);
});
onUnmounted(() => {
  if (timer) clearInterval(timer);
});
</script>
<template>
  <RouterLink v-if="pending > 0" class="notice-reminder" to="/contact-notices"
    >{{
      language === "ja"
        ? `連絡事項：未確認 ${pending} 件・未読 ${unread} 件`
        : language === "en"
          ? `Notices: ${pending} unconfirmed · ${unread} unread`
          : `联络事项：待确认 ${pending} 条 · 未读 ${unread} 条`
    }}
    →</RouterLink
  >
</template>
<style scoped>
.notice-reminder {
  display: block;
  padding: 14px 20px;
  border: 1px solid #7c9e45;
  border-radius: 10px;
  margin-bottom: 20px;
  color: var(--ink);
  background: var(--panel);
}
</style>
