<script setup lang="ts">
import LocalizedDateInput from '../components/LocalizedDateInput.vue'
import { computed, onMounted, ref } from "vue";
import { useAuthStore } from "../stores/auth";
import { useStoreScope } from "../stores/storeScope";
import { language } from "../i18n";
import { getErrorMessage } from "../api/http";
import {
  getNotice,
  getNoticeAudience,
  getNotices,
  noticeAction,
  saveNotice,
} from "../api/contactNotices";
import type { Notice, NoticePayload } from "../api/contactNotices";

// region 页面文案：直接使用三语言词典，正文和员工姓名保持原文。
const words: Record<string, [string, string, string]> = {
  title: ["連絡事項", "Notices", "联络事项"],
  received: ["受信した連絡", "Received", "我收到的"],
  published: ["自分の連絡", "My notices", "我发布的"],
  management: ["全件管理", "Manage all", "全部管理"],
  headquarters: ["本部から", "Headquarters", "来自总部"],
  storeScope: ["対象店舗", "Target stores", "目标门店"],
  all: ["全員", "All staff", "全体"],
  department: ["部門", "Department", "部门"],
  personal: ["個人", "Personal", "个人"],
  create: ["連絡を作成", "Create notice", "发布事项"],
  search: ["検索", "Search", "查询"],
  keyword: [
    "タイトル・本文を検索",
    "Search title or content",
    "搜索标题或正文",
  ],
  draft: ["下書き", "Draft", "草稿"],
  publishedStatus: ["公開中", "Published", "已发布"],
  closed: ["終了", "Closed", "已关闭"],
  withdrawn: ["取り下げ", "Withdrawn", "已撤回"],
  normal: ["通常", "Normal", "普通"],
  important: ["重要", "Important", "重要"],
  urgent: ["緊急", "Urgent", "紧急"],
  confirm: ["確認する", "Confirm", "确认"],
  confirmed: ["確認済み", "Confirmed", "已确认"],
  pending: ["未確認", "Unconfirmed", "待确认"],
  overdue: ["期限超過・未確認", "Overdue, unconfirmed", "逾期未确认"],
  recipients: [
    "受信者の確認状況",
    "Recipient confirmations",
    "接收员工确认情况",
  ],
  empty: ["連絡事項はありません", "No notices found", "暂无联络事项"],
  titleField: ["件名", "Title", "标题"],
  content: ["本文", "Content", "正文"],
  priority: ["優先度", "Priority", "优先级"],
  scope: ["公開範囲", "Audience", "接收范围"],
  start: ["公開開始（任意）", "Start time (optional)", "开始时间（可选）"],
  deadline: ["期限（任意）", "Deadline (optional)", "期限（可选）"],
  autoClose: [
    "全員が確認したら自動終了",
    "Close when everyone confirms",
    "全员确认后自动关闭",
  ],
  save: ["下書き保存", "Save draft", "保存草稿"],
  publish: ["公開する", "Publish", "发布"],
  edit: ["編集", "Edit", "修改"],
  close: ["終了する", "Close", "关闭"],
  withdraw: ["取り下げる", "Withdraw", "撤回"],
  delete: ["下書き削除", "Delete draft", "删除草稿"],
  cancel: ["キャンセル", "Cancel", "取消"],
  prev: ["前へ", "Previous", "上一页"],
  next: ["次へ", "Next", "下一页"],
  total: ["件数", "Total", "总数"],
  explanation: [
    "期限または全員確認で終了します。履歴は保存されます。",
    "Closes at the deadline or after everyone confirms. History is retained.",
    "到达期限或全员确认后自动关闭，保留历史记录。",
  ],
  deadlineReason: ["期限到達", "Deadline reached", "到达期限"],
  allReason: ["全員確認済み", "Everyone confirmed", "全员已确认"],
  manual: ["手動終了", "Closed manually", "手动关闭"],
  reason: ["変更理由（任意）", "Reason (optional)", "修改理由（可选）"],
  actionConfirm: [
    "この操作を実行しますか？",
    "Perform this action?",
    "确认执行此操作？",
  ],
  anyStatus: ["すべての状態", "All statuses", "所有状态"],
  anyConfirmation: ["すべての確認状況", "All confirmations", "所有确认状态"],
};
function t(key: string) {
  const entry = words[key];
  return (
    entry?.[language.value === "ja" ? 0 : language.value === "en" ? 1 : 2] ||
    key
  );
}
// endregion

// region 列表和表单状态
const auth = useAuthStore();
const storeScope = useStoreScope();
const view = ref("received"),
  scope = ref("all"),
  keyword = ref(""),
  page = ref(1);
const headquartersOnly = ref(false);
const status = ref(""),
  confirmation = ref("");
const items = ref<Notice[]>([]),
  total = ref(0),
  pages = ref(1),
  selected = ref<Notice | null>(null);
const error = ref(""),
  busy = ref(false),
  editing = ref(false),
  editId = ref<number | undefined>();
const audience = ref<Awaited<ReturnType<typeof getNoticeAudience>>>({
  employees: [],
  departments: [],
});
const form = ref<NoticePayload>(blankForm());
function blankForm(): NoticePayload {
  return {
    title: "",
    content: "",
    priority: "normal",
    target_type: auth.isManager || auth.isHeadquarters ? "all" : "department",
    store_ids: [],
    department_id: auth.employee?.department?.id || null,
    employee_ids: [],
    starts_at: null,
    deadline_at: null,
    close_on_all_confirmed: true,
  };
}
const employees = computed(() => audience.value.employees);
function statusText(notice: Notice) {
  return t(notice.status === "published" ? "publishedStatus" : notice.status);
}
function date(value: string | null) {
  return value ? value.replace("T", " ").slice(0, 16) : "—";
}
async function load() {
  error.value = "";
  try {
    const result = await getNotices({
      view: view.value,
      source: headquartersOnly.value ? "headquarters" : undefined,
      target_type: scope.value,
      keyword: keyword.value || undefined,
      status: status.value || undefined,
      confirmed:
        view.value === "received" && confirmation.value
          ? confirmation.value === "yes"
          : undefined,
      page: page.value,
      page_size: 10,
    });
    items.value = result.items;
    total.value = result.total;
    pages.value = Math.max(1, result.total_pages);
  } catch (e) {
    error.value = getErrorMessage(e);
  }
}
function filter() {
  page.value = 1;
  void load();
}
async function open(id: number) {
  try {
    selected.value = await getNotice(id);
  } catch (e) {
    error.value = getErrorMessage(e);
  }
}
function startEdit(notice?: Notice) {
  editId.value = notice?.id;
  form.value = notice
    ? {
        title: notice.title,
        content: notice.content,
        priority: notice.priority,
        target_type: notice.target_type,
        department_id: notice.department_id,
        employee_ids: notice.employee_ids || [],
        store_ids: notice.target_store_ids || [],
        starts_at: notice.starts_at.slice(0, 16),
        deadline_at: notice.deadline_at?.slice(0, 16) || null,
        close_on_all_confirmed: notice.close_on_all_confirmed,
        expected_version: notice.version,
      }
    : blankForm();
  editing.value = true;
}
async function submit(publish: boolean) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    const payload = {
      ...form.value,
      starts_at: form.value.starts_at || null,
      deadline_at: form.value.deadline_at || null,
      employee_ids:
        form.value.target_type === "personal" ? form.value.employee_ids : [],
    };
    let notice = await saveNotice(payload, editId.value);
    // 保存成功后保留ID；发布失败再次提交会更新原草稿。
    editId.value = notice.id;
    form.value.expected_version = notice.version;
    if (publish) notice = await noticeAction(notice, "publish");
    editing.value = false;
    selected.value = notice;
    view.value = "published";
    scope.value = notice.target_type;
    await load();
  } catch (e) {
    error.value = getErrorMessage(e);
  } finally {
    busy.value = false;
  }
}
async function act(action: string) {
  if (!selected.value || busy.value) return;
  if (
    ["delete", "withdraw", "close"].includes(action) &&
    !window.confirm(t("actionConfirm"))
  )
    return;
  busy.value = true;
  error.value = "";
  try {
    const result = await noticeAction(selected.value, action);
    selected.value = action === "delete" ? null : result;
    await load();
  } catch (e) {
    error.value = getErrorMessage(e);
  } finally {
    busy.value = false;
  }
}
onMounted(async () => {
  await load();
  try {
    audience.value = await getNoticeAudience();
  } catch (e) {
    error.value = getErrorMessage(e);
  }
});
// endregion
</script>

<template>
  <section class="notice-page">
    <header class="notice-heading">
      <div>
        <h1>{{ t("title") }}</h1>
        <p>{{ t("explanation") }}</p>
      </div>
      <button @click="startEdit()">＋ {{ t("create") }}</button>
    </header>
    <p v-if="error" role="alert" class="notice-error">{{ error }}</p>
    <nav class="notice-tabs">
      <button
        v-for="tab in [
          'received',
          'published',
          ...(auth.isManager || auth.isHeadquarters ? ['management'] : []),
          'headquarters',
        ]"
        :key="tab"
        :class="{ active: tab === 'headquarters' ? headquartersOnly : view === tab && !headquartersOnly }"
        @click="
          headquartersOnly = tab === 'headquarters';
          view = tab === 'headquarters' ? (auth.isManager || auth.isHeadquarters ? 'management' : 'received') : tab;
          filter();
        "
      >
        {{ t(tab) }}
      </button>
    </nav>
    <div class="notice-filters">
      <button
        v-for="target in ['all', 'department', 'personal']"
        :key="target"
        class="scope"
        :class="[target, { active: scope === target }]"
        @click="
          scope = target;
          filter();
        "
      >
        {{ t(target) }}</button
      ><input
        v-model="keyword"
        :placeholder="t('keyword')"
        @keyup.enter="filter"
      /><select v-model="status" @change="filter">
        <option value="">{{ t("anyStatus") }}</option>
        <option
          v-for="state in ['draft', 'published', 'closed', 'withdrawn']"
          :key="state"
          :value="state"
        >
          {{ t(state === "published" ? "publishedStatus" : state) }}
        </option></select
      ><select
        v-if="view === 'received'"
        v-model="confirmation"
        @change="filter"
      >
        <option value="">{{ t("anyConfirmation") }}</option>
        <option value="yes">{{ t("confirmed") }}</option>
        <option value="no">{{ t("pending") }}</option></select
      ><button @click="filter">{{ t("search") }}</button>
    </div>
    <div class="notice-list">
      <button
        v-for="notice in items"
        :key="notice.id"
        class="notice-card"
        @click="open(notice.id)"
      >
        <div class="notice-row">
          <span v-if="notice.source === 'headquarters'" class="hq-badge">本部</span>
          <span class="scope" :class="notice.target_type"
            >{{ t(notice.target_type)
            }}{{
              notice.department_name ? " · " + notice.department_name : ""
            }}</span
          ><span>{{ statusText(notice) }}</span
          ><strong
            v-if="notice.priority !== 'normal'"
            :class="notice.priority"
            >{{ t(notice.priority) }}</strong
          >
        </div>
        <h2 data-no-translate>{{ notice.title }}</h2>
        <p class="notice-preview" data-no-translate>{{ notice.content }}</p>
        <div class="notice-row">
          <span
            >{{ notice.publisher_name }} · {{ date(notice.created_at) }}</span
          ><span
            >{{ notice.confirmed_count }} / {{ notice.recipient_count }}
            {{ t("confirmed") }}</span
          >
        </div>
        <small v-if="notice.deadline_at"
          >{{ t("deadline") }}: {{ date(notice.deadline_at) }}</small
        >
      </button>
      <p v-if="!items.length">{{ t("empty") }}</p>
    </div>
    <footer class="notice-row">
      <span>{{ t("total") }}: {{ total }} · {{ page }} / {{ pages }}</span>
      <div>
        <button
          :disabled="page <= 1"
          @click="
            page--;
            load();
          "
        >
          {{ t("prev") }}</button
        ><button
          :disabled="page >= pages"
          @click="
            page++;
            load();
          "
        >
          {{ t("next") }}
        </button>
      </div>
    </footer>

    <div
      v-if="selected && !editing"
      class="notice-overlay"
      @click.self="selected = null"
    >
      <article
        class="notice-dialog"
        role="dialog"
        aria-modal="true"
        :aria-label="selected.title"
      >
        <div class="notice-row">
          <span class="scope" :class="selected.target_type">{{
            t(selected.target_type)
          }}</span
          ><button @click="selected = null">×</button>
        </div>
        <h2 data-no-translate>{{ selected.title }}</h2>
        <p v-if="error" role="alert" class="notice-error">{{ error }}</p>
        <p>
          {{ selected.publisher_name }} · {{ statusText(selected) }} ·
          {{ t(selected.priority) }}
        </p>
        <p>{{ t("deadline") }}: {{ date(selected.deadline_at) }}</p>
        <p v-if="selected.close_reason">
          {{
            t(
              selected.close_reason === "deadline"
                ? "deadlineReason"
                : selected.close_reason === "all_confirmed"
                  ? "allReason"
                  : selected.close_reason === "manual"
                    ? "manual"
                    : "withdrawn",
            )
          }}
          · {{ date(selected.closed_at) }}
        </p>
        <div class="notice-body">{{ selected.content }}</div>
        <button
          v-if="selected.can_confirm"
          :disabled="busy"
          @click="act('confirm')"
        >
          {{ t("confirm") }}
        </button>
        <p v-else-if="selected.confirmed_at">
          <span class="lamp green" /> {{ t("confirmed") }} ·
          {{ date(selected.confirmed_at) }}
        </p>
        <section v-if="selected.can_view_recipients">
          <h3>
            {{ t("recipients") }} · {{ selected.confirmed_count }}/{{
              selected.recipient_count
            }}
          </h3>
          <div
            v-for="recipient in selected.recipients"
            :key="recipient.employee_id"
            class="recipient"
          >
            <span class="lamp" :class="recipient.light" /><strong>{{
              recipient.name
            }}</strong
            ><span>{{ recipient.department_name }} · {{ storeScope.stores.find((item) => item.id === recipient.store_id)?.store_no || '' }}</span
            ><span>{{
              t(
                recipient.light === "green"
                  ? "confirmed"
                  : recipient.light === "red"
                    ? "overdue"
                    : "pending",
              )
            }}</span
            ><small>{{ date(recipient.confirmed_at) }}</small>
          </div>
          <div v-if="selected.can_manage" class="notice-actions">
            <template v-if="selected.status === 'draft'"
              ><button @click="startEdit(selected)">{{ t("edit") }}</button
              ><button :disabled="busy" @click="act('publish')">
                {{ t("publish") }}</button
              ><button :disabled="busy" @click="act('delete')">
                {{ t("delete") }}
              </button></template
            ><template v-if="selected.status === 'withdrawn'"
              ><button @click="startEdit(selected)">{{ t("edit") }}</button
              ><button :disabled="busy" @click="act('publish')">
                {{ t("publish") }}
              </button></template
            ><button
              v-if="selected.status === 'published'"
              :disabled="busy"
              @click="act('close')"
            >
              {{ t("close") }}</button
            ><button
              v-if="['published', 'closed'].includes(selected.status)"
              :disabled="busy"
              @click="act('withdraw')"
            >
              {{ t("withdraw") }}
            </button>
          </div>
        </section>
      </article>
    </div>

    <div v-if="editing" class="notice-overlay">
      <form class="notice-dialog notice-form" @submit.prevent="submit(false)">
        <h2>{{ t("create") }}</h2>
        <p v-if="error" role="alert" class="notice-error">{{ error }}</p>
        <label
          >{{ t("titleField")
          }}<input v-model="form.title" required maxlength="100" /></label
        ><label
          >{{ t("content")
          }}<textarea
            v-model="form.content"
            required
            maxlength="10000"
            rows="6"
          /></label
        ><label
          >{{ t("priority")
          }}<select v-model="form.priority">
            <option
              v-for="priority in ['normal', 'important', 'urgent']"
              :key="priority"
              :value="priority"
            >
              {{ t(priority) }}
            </option>
          </select></label
        ><label
          >{{ t("scope")
          }}<select v-model="form.target_type">
            <option v-if="auth.isManager || auth.isHeadquarters" value="all">{{ t("all") }}</option>
            <option value="department">{{ t("department") }}</option>
            <option value="personal">{{ t("personal") }}</option>
          </select></label
        ><fieldset v-if="auth.isHeadquarters">
          <legend>{{ t('storeScope') }}（空欄＝全店舗）</legend>
          <label v-for="store in storeScope.stores.filter((item) => item.is_active)" :key="store.id" class="checkbox"><input v-model="form.store_ids" type="checkbox" :value="store.id" />{{ store.store_no }} {{ store.name }}</label>
        </fieldset><label v-if="form.target_type === 'department'"
          >{{ t("department")
          }}<select v-model="form.department_id" required>
            <option
              v-for="department in audience.departments"
              :key="department.id"
              :value="department.id"
            >
              {{ department.name }}
            </option>
          </select></label
        >
        <fieldset v-if="form.target_type === 'personal'">
          <legend>{{ t("personal") }}</legend>
          <label
            v-for="employee in employees"
            :key="employee.id"
            class="checkbox"
            ><input
              v-model="form.employee_ids"
              type="checkbox"
              :value="employee.id"
            />{{ employee.name }}</label
          >
        </fieldset>
        <label
          >{{ t("start")
          }}<LocalizedDateInput v-model="form.starts_at" type="datetime-local" /></label
        ><label
          >{{ t("deadline")
          }}<LocalizedDateInput v-model="form.deadline_at" type="datetime-local" /></label
        ><label class="checkbox"
          ><input v-model="form.close_on_all_confirmed" type="checkbox" />{{
            t("autoClose")
          }}</label
        ><label
          >{{ t("reason") }}<input v-model="form.reason" maxlength="500"
        /></label>
        <div class="notice-actions">
          <button type="button" @click="editing = false">
            {{ t("cancel") }}</button
          ><button type="submit" :disabled="busy">{{ t("save") }}</button
          ><button
            type="button"
            :disabled="busy || !form.title.trim() || !form.content.trim()"
            @click="submit(true)"
          >
            {{ t("publish") }}
          </button>
        </div>
      </form>
    </div>
  </section>
</template>

<style scoped>
.notice-page {
  max-width: 1120px;
  margin: 32px auto;
  padding: 0 20px;
  color: var(--text-primary, #e8eee5);
}
.notice-heading,
.notice-row,
.notice-tabs,
.notice-filters,
.notice-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}
.notice-heading {
  margin-bottom: 24px;
}
.notice-tabs,
.notice-filters,
.notice-actions {
  justify-content: flex-start;
  margin: 18px 0;
}
h1 {
  font-size: 36px;
}
h2 {
  font-size: 22px;
}
p {
  line-height: 1.6;
}
button,
input,
select,
textarea {
  font: inherit;
  color: inherit;
  border: 1px solid var(--border-color, #384237);
  border-radius: 8px;
  padding: 10px 14px;
  background: var(--notice-field, #20271e);
}
button {
  cursor: pointer;
}
button:disabled {
  opacity: 0.5;
  cursor: default;
}
.active {
  outline: 2px solid #91b64e;
}
.notice-filters input {
  flex: 1;
  min-width: 180px;
}
.notice-list {
  display: grid;
  gap: 14px;
}
.notice-card {
  text-align: start;
  width: 100%;
  background: var(--notice-panel, #151b14);
  padding: 22px;
}
.notice-preview {
  white-space: pre-line;
  max-height: 4.8em;
  overflow: hidden;
}
.scope {
  display: inline-block;
  border-radius: 7px;
  padding: 6px 12px;
  font-size: 14px;
}
.scope.all {
  background: #dceaff;
  color: #184884;
}
.scope.department {
  background: #ece2ff;
  color: #593686;
}
.scope.personal {
  background: #ffead4;
  color: #824719;
}
.urgent,
.notice-error {
  color: #ec7666;
}
.important {
  color: #d9a539;
}
.notice-overlay {
  position: fixed;
  inset: 0;
  background: #0009;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  z-index: 1100;
}
.notice-dialog {
  width: min(780px, 100%);
  max-height: 90vh;
  overflow: auto;
  background: var(--notice-panel, #151b14);
  border: 1px solid var(--border-color, #384237);
  border-radius: 16px;
  padding: 26px;
  color: var(--text-primary, #e8eee5);
}
.notice-body {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  padding: 20px 0;
  margin: 15px 0;
  border-block: 1px solid #66735f55;
}
.recipient {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  padding: 12px 0;
  border-bottom: 1px solid #66735f33;
}
.lamp {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
}
.green {
  background: #45b86a;
}
.yellow {
  background: #e7b837;
}
.red {
  background: #e15b51;
}
.notice-form label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 14px 0;
}
.notice-form .checkbox {
  flex-direction: row;
  align-items: center;
}
.checkbox input {
  width: auto;
}
.notice-form input,
.notice-form textarea,
.notice-form select {
  width: 100%;
  box-sizing: border-box;
}
.notice-form .checkbox input {
  width: auto;
}
fieldset {
  max-height: 230px;
  overflow: auto;
  border: 1px solid #66735f55;
}
.notice-error {
  padding: 12px;
  border: 1px solid currentColor;
  border-radius: 8px;
}
:global(html[data-theme="light"]) .notice-page,
:global(html[data-theme="light"]) .notice-dialog {
  --notice-panel: #fff;
  --notice-field: #f5f8f2;
  color: #233020;
  --text-primary: #233020;
  --border-color: #d3dccd;
}
@media (max-width: 600px) {
  .notice-dialog {
    padding: 18px;
  }
  .notice-heading h1 {
    font-size: 28px;
  }
  .recipient {
    gap: 8px;
  }
}
</style>
