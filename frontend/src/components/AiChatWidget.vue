<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { Bot, KeyRound, RotateCcw, Send, Settings, Sparkles, X } from '@lucide/vue'

import {
  cancelAiAction, confirmAiAction, deleteAiCredential, getAiCredentialStatus,
  saveAiCredential, sendAiChat,
} from '../api'
import { getErrorMessage } from '../api/http'
import type { AiChatMessage, AiPendingAction, AiProvider } from '../types/api'

const PROVIDER_STORAGE_KEY = 'marketflow_ai_provider'
const PROVIDER_DEFAULT_MODELS: Record<AiProvider, string> = {
  gemini: 'gemini-3.5-flash-lite',
  openai: 'gpt-5.6-luna',
}

function apiKeyStorageKey(provider: AiProvider) {
  return `marketflow_ai_${provider}_api_key`
}

function modelStorageKey(provider: AiProvider) {
  return `marketflow_ai_${provider}_model`
}

interface DisplayMessage extends AiChatMessage {
  id: number
  localOnly?: boolean
}

const isOpen = ref(false)
const showSettings = ref(false)
const isSending = ref(false)
const input = ref('')
const savedProvider = localStorage.getItem(PROVIDER_STORAGE_KEY)
const initialProvider: AiProvider = savedProvider === 'openai' ? 'openai' : 'gemini'
const provider = ref<AiProvider>(initialProvider)
const providerDraft = ref<AiProvider>(initialProvider)
// 升级后删除旧版本留在浏览器的明文密钥；用户只需重新配置一次。
localStorage.removeItem('marketflow_gemini_api_key')
localStorage.removeItem(apiKeyStorageKey('openai'))
const keyConfigured = ref(false)
const draftKeyConfigured = ref(false)
const apiKeyDraft = ref('')
const settingsError = ref('')
const model = ref(
  localStorage.getItem(modelStorageKey(initialProvider)) || PROVIDER_DEFAULT_MODELS[initialProvider],
)
const modelDraft = ref(model.value)
const messageList = ref<HTMLElement | null>(null)
const pendingActions = ref<AiPendingAction[]>([])
const actionBusyId = ref<number | null>(null)
let nextMessageId = 2

const messages = ref<DisplayMessage[]>([
  {
    id: 1,
    role: 'model',
    content: '你好，我是 MarketFlow 助手。可以查询实时业务数据，也可以协助处理商品、库存、供应商、进货、销售、员工和折扣；所有修改都要由你确认。',
    localOnly: true,
  },
])

const canSend = computed(() => Boolean(input.value.trim() && keyConfigured.value && !isSending.value))

async function refreshCredentialStatus(selectedProvider: AiProvider) {
  try {
    return (await getAiCredentialStatus(selectedProvider)).configured
  } catch (error) {
    settingsError.value = getErrorMessage(error)
    return false
  }
}

async function openWidget() {
  isOpen.value = true
  keyConfigured.value = await refreshCredentialStatus(provider.value)
  draftKeyConfigured.value = keyConfigured.value
  if (!keyConfigured.value) showSettings.value = true
}

async function saveSettings() {
  const cleanKey = apiKeyDraft.value.trim()
  const cleanModel = modelDraft.value.trim() || PROVIDER_DEFAULT_MODELS[providerDraft.value]
  settingsError.value = ''
  try {
    if (cleanKey) await saveAiCredential(providerDraft.value, cleanKey)
    else if (!(await getAiCredentialStatus(providerDraft.value)).configured) {
      settingsError.value = '请输入 API Key'
      return
    }
  } catch (error) {
    settingsError.value = getErrorMessage(error)
    return
  }
  provider.value = providerDraft.value
  keyConfigured.value = true
  draftKeyConfigured.value = true
  apiKeyDraft.value = ''
  model.value = cleanModel

  localStorage.setItem(PROVIDER_STORAGE_KEY, provider.value)
  localStorage.removeItem(apiKeyStorageKey(provider.value))
  localStorage.removeItem('marketflow_gemini_api_key')
  localStorage.setItem(modelStorageKey(provider.value), cleanModel)
  showSettings.value = false
}

async function removeApiKey() {
  settingsError.value = ''
  try {
    await deleteAiCredential(providerDraft.value)
  } catch (error) {
    settingsError.value = getErrorMessage(error)
    return
  }
  apiKeyDraft.value = ''
  localStorage.removeItem(apiKeyStorageKey(providerDraft.value))
  draftKeyConfigured.value = false
  if (providerDraft.value === provider.value) keyConfigured.value = false
}

async function loadProviderSettings() {
  apiKeyDraft.value = ''
  draftKeyConfigured.value = await refreshCredentialStatus(providerDraft.value)
  modelDraft.value =
    localStorage.getItem(modelStorageKey(providerDraft.value)) ||
    PROVIDER_DEFAULT_MODELS[providerDraft.value]
}

function clearConversation() {
  messages.value = [
    {
      id: nextMessageId++,
      role: 'model',
      content: '对话已清空。你可以继续询问 MarketFlow 的基础问题。',
      localOnly: true,
    },
  ]
  pendingActions.value = []
}

async function scrollToBottom() {
  await nextTick()
  if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
}

async function submitMessage() {
  const content = input.value.trim()
  if (!content || isSending.value) return
  if (!keyConfigured.value) {
    showSettings.value = true
    return
  }

  messages.value.push({ id: nextMessageId++, role: 'user', content })
  input.value = ''
  isSending.value = true
  await scrollToBottom()

  try {
    const history: AiChatMessage[] = []
    const actualMessages = messages.value.filter((message) => !message.localOnly).slice(-12)
    for (const message of actualMessages) {
      history.push({ role: message.role, content: message.content })
    }

    const result = await sendAiChat(provider.value, model.value, history)
    messages.value.push({ id: nextMessageId++, role: 'model', content: result.message })
    pendingActions.value.push(...result.pending_actions)
  } catch (error) {
    messages.value.push({
      id: nextMessageId++,
      role: 'model',
      content: `请求失败：${getErrorMessage(error)}`,
      localOnly: true,
    })
  } finally {
    isSending.value = false
    await scrollToBottom()
  }
}

async function handleAction(action: AiPendingAction, execute: boolean) {
  actionBusyId.value = action.id
  try {
    const result = execute ? await confirmAiAction(action.id) : await cancelAiAction(action.id)
    const index = pendingActions.value.findIndex((item) => item.id === action.id)
    if (index >= 0) pendingActions.value[index] = result.action
    let completionMessage = execute
      ? `操作已确认并执行：${action.summary}`
      : `操作已取消：${action.summary}`
    // AI创建员工时后端会返回一次性初始凭据，必须显示给执行操作的店长。
    if (execute && result.result) {
      const employeeNo = result.result.employee_no
      const temporaryPassword = result.result.temporary_password
      if (typeof employeeNo === 'string' && typeof temporaryPassword === 'string') {
        completionMessage += `\n员工编号：${employeeNo}\n临时密码：${temporaryPassword}\n请安全地交给员工，并要求首次登录后修改。`
      }
    }
    messages.value.push({
      id: nextMessageId++,
      role: 'model',
      content: completionMessage,
      localOnly: true,
    })
  } catch (error) {
    messages.value.push({
      id: nextMessageId++,
      role: 'model',
      content: `操作处理失败：${getErrorMessage(error)}`,
      localOnly: true,
    })
  } finally {
    actionBusyId.value = null
    await scrollToBottom()
  }
}

function handleEnter(event: KeyboardEvent) {
  if (event.shiftKey) return
  event.preventDefault()
  void submitMessage()
}
</script>

<template>
  <div class="ai-chat-widget">
    <Transition name="chat-panel">
      <section v-if="isOpen" class="ai-chat-panel" aria-label="MarketFlow AI 助手">
        <header class="ai-chat-header">
          <div class="assistant-identity">
            <span class="assistant-icon"><Sparkles :size="18" /></span>
            <div>
              <strong>MarketFlow 助手</strong>
              <span>{{ provider === 'gemini' ? 'Gemini' : 'OpenAI' }} · 实时业务助手</span>
            </div>
          </div>
          <div class="header-actions">
            <button type="button" title="清空对话" @click="clearConversation">
              <RotateCcw :size="17" />
            </button>
            <button type="button" title="API Key 设置" @click="showSettings = !showSettings">
              <Settings :size="18" />
            </button>
            <button type="button" title="关闭" @click="isOpen = false">
              <X :size="19" />
            </button>
          </div>
        </header>

        <div v-if="showSettings" class="ai-settings">
          <div class="settings-title"><KeyRound :size="17" /><strong>连接设置</strong></div>
          <label>
            模型供应商
            <select v-model="providerDraft" @change="loadProviderSettings">
              <option value="gemini">Google Gemini</option>
              <option value="openai">OpenAI</option>
            </select>
          </label>
          <label>
            {{ providerDraft === 'gemini' ? 'Gemini' : 'OpenAI' }} API Key
            <input v-model="apiKeyDraft" type="password" autocomplete="off" placeholder="输入你的 API Key" />
          </label>
          <label>
            模型名称
            <input v-model="modelDraft" type="text" :placeholder="PROVIDER_DEFAULT_MODELS[providerDraft]" />
          </label>
          <p>密钥加密保存在服务器，当前员工登录后自动使用。留空可只更新模型名称。</p>
          <p v-if="settingsError" class="form-error">{{ settingsError }}</p>
          <div class="settings-actions">
            <a
              :href="providerDraft === 'gemini' ? 'https://aistudio.google.com/apikey' : 'https://platform.openai.com/api-keys'"
              target="_blank"
              rel="noreferrer"
            >获取 API Key</a>
            <button v-if="draftKeyConfigured" class="danger-text" type="button" @click="removeApiKey">删除密钥</button>
            <button class="save-button" type="button" @click="saveSettings">保存</button>
          </div>
        </div>

        <div ref="messageList" class="ai-chat-messages">
          <article
            v-for="message in messages"
            :key="message.id"
            class="chat-message"
            :class="message.role"
          >
            <div class="message-label">{{ message.role === 'user' ? '你' : 'AI 助手' }}</div>
            <p>{{ message.content }}</p>
          </article>
          <article v-if="isSending" class="chat-message model">
            <div class="message-label">AI 助手</div>
            <p class="typing"><i /><i /><i /></p>
          </article>
          <article
            v-for="action in pendingActions"
            :key="`action-${action.id}`"
            class="action-card"
            :class="action.status"
          >
            <div class="action-card-title">
              <strong>{{ action.status === 'pending' ? '需要确认的修改' : '操作记录' }}</strong>
              <span>{{ action.status }}</span>
            </div>
            <p>{{ action.summary }}</p>
            <small v-if="action.status === 'pending'">10分钟内有效，确认时会重新检查权限和最新数据。</small>
            <small v-else-if="action.failure_reason">{{ action.failure_reason }}</small>
            <div v-if="action.status === 'pending'" class="action-buttons">
              <button
                type="button"
                :disabled="actionBusyId === action.id"
                @click="handleAction(action, false)"
              >取消</button>
              <button
                class="confirm-action"
                type="button"
                :disabled="actionBusyId === action.id"
                @click="handleAction(action, true)"
              >{{ actionBusyId === action.id ? '处理中…' : '确认执行' }}</button>
            </div>
          </article>
        </div>

        <footer class="ai-chat-composer">
          <div v-if="!keyConfigured" class="key-warning" @click="showSettings = true">
            请先设置模型供应商和 API Key
          </div>
          <div class="composer-row">
            <textarea
              v-model="input"
              rows="2"
              maxlength="4000"
              placeholder="询问系统功能或操作方法……"
              @keydown.enter="handleEnter"
            />
            <button class="send-button" type="button" :disabled="!canSend" title="发送" @click="submitMessage">
              <Send :size="19" />
            </button>
          </div>
          <small>实时数据来自受控工具；修改必须确认并遵守原有权限与审计规则。</small>
        </footer>
      </section>
    </Transition>

    <button v-if="!isOpen" class="ai-chat-trigger" type="button" aria-label="打开 AI 助手" @click="openWidget">
      <Bot :size="27" />
      <span>AI</span>
    </button>
  </div>
</template>

<style scoped>
.ai-chat-widget {
  position: fixed;
  z-index: 1200;
  right: 28px;
  bottom: 26px;
}

.ai-chat-trigger {
  width: 62px;
  height: 62px;
  border: 1px solid rgba(190, 255, 75, 0.65);
  border-radius: 50%;
  color: #10140b;
  background: #bdff4b;
  box-shadow: 0 14px 38px rgba(0, 0, 0, 0.42), 0 0 24px rgba(189, 255, 75, 0.2);
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}

.ai-chat-trigger span {
  position: absolute;
  right: -2px;
  top: -2px;
  min-width: 22px;
  height: 22px;
  padding: 0 5px;
  border-radius: 999px;
  background: #171a20;
  color: #bdff4b;
  font-size: 10px;
  font-weight: 800;
  display: grid;
  place-items: center;
}

.ai-chat-trigger:hover { transform: translateY(-3px); box-shadow: 0 18px 45px rgba(0, 0, 0, 0.5), 0 0 30px rgba(189, 255, 75, 0.28); }

.ai-chat-panel {
  width: min(390px, calc(100vw - 30px));
  height: min(620px, calc(100vh - 100px));
  border: 1px solid #2b3039;
  border-radius: 18px;
  overflow: hidden;
  background: #12151a;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.58);
  display: flex;
  flex-direction: column;
}

.ai-chat-header {
  min-height: 66px;
  padding: 12px 14px;
  border-bottom: 1px solid #292e36;
  background: #171a20;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.assistant-identity, .header-actions, .settings-title, .settings-actions, .composer-row { display: flex; align-items: center; }
.assistant-identity { gap: 10px; }
.assistant-icon { width: 36px; height: 36px; border-radius: 11px; background: #bdff4b; color: #10140b; display: grid; place-items: center; }
.assistant-identity div { display: flex; flex-direction: column; gap: 2px; }
.assistant-identity strong { color: #f5f7f0; font-size: 14px; }
.assistant-identity span { color: #89919e; font-size: 11px; }
.header-actions { gap: 4px; }
.header-actions button { width: 32px; height: 32px; border: 0; border-radius: 8px; background: transparent; color: #9099a5; display: grid; place-items: center; cursor: pointer; }
.header-actions button:hover { color: #bdff4b; background: #22272e; }

.ai-settings { padding: 14px; border-bottom: 1px solid #2a3038; background: #191d23; color: #dce1d8; }
.settings-title { gap: 7px; margin-bottom: 11px; color: #bdff4b; }
.ai-settings label { display: grid; gap: 6px; margin: 9px 0; font-size: 12px; color: #aab1bc; }
.ai-settings input, .ai-settings select { min-height: 38px; padding: 0 11px; border: 1px solid #343b45; border-radius: 8px; outline: 0; background: #111419; color: #eef2ea; }
.ai-settings input:focus, .ai-settings select:focus { border-color: #93c83c; }
.ai-settings p { margin: 9px 0; color: #7f8895; font-size: 11px; line-height: 1.55; }
.settings-actions { justify-content: flex-end; gap: 8px; }
.settings-actions a, .settings-actions button { border: 0; background: transparent; color: #9ca5b1; font-size: 12px; cursor: pointer; text-decoration: none; }
.settings-actions a:hover { color: #bdff4b; }
.settings-actions .danger-text { color: #ff8277; }
.settings-actions .save-button { padding: 7px 14px; border-radius: 7px; color: #11150c; background: #bdff4b; font-weight: 700; }

.ai-chat-messages { flex: 1; overflow-y: auto; padding: 18px 14px; display: flex; flex-direction: column; gap: 15px; }
.chat-message { max-width: 88%; }
.chat-message.user { align-self: flex-end; }
.message-label { margin: 0 4px 5px; color: #7e8793; font-size: 10px; }
.chat-message.user .message-label { text-align: right; }
.chat-message p { margin: 0; padding: 11px 13px; border: 1px solid #2d333c; border-radius: 4px 13px 13px 13px; background: #1b1f25; color: #e5e9e2; font-size: 13px; line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; }
.chat-message.user p { border-color: rgba(189, 255, 75, 0.32); border-radius: 13px 4px 13px 13px; background: rgba(152, 205, 61, 0.13); }
.typing { display: flex; gap: 5px; align-items: center; width: 50px; }
.typing i { width: 5px; height: 5px; border-radius: 50%; background: #bdff4b; animation: typing 1s infinite alternate; }
.typing i:nth-child(2) { animation-delay: 0.2s; }
.typing i:nth-child(3) { animation-delay: 0.4s; }

.action-card { width: 100%; padding: 13px; border: 1px solid rgba(189, 255, 75, 0.34); border-radius: 12px; background: rgba(189, 255, 75, 0.07); color: #e8ede3; }
.action-card.executed { border-color: rgba(91, 205, 126, 0.35); }
.action-card.cancelled, .action-card.failed, .action-card.expired { border-color: #343a43; opacity: 0.72; }
.action-card-title { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.action-card-title strong { font-size: 12px; color: #bdff4b; }
.action-card-title span { padding: 3px 7px; border-radius: 99px; background: #252b32; color: #aab2bd; font-size: 9px; text-transform: uppercase; }
.action-card p { margin: 8px 0 4px; font-size: 12px; line-height: 1.55; }
.action-card small { color: #858e9a; font-size: 10px; }
.action-buttons { display: flex; justify-content: flex-end; gap: 7px; margin-top: 11px; }
.action-buttons button { padding: 7px 11px; border: 1px solid #3a414b; border-radius: 7px; background: #171b20; color: #aeb6c1; font-size: 11px; cursor: pointer; }
.action-buttons .confirm-action { border-color: #bdff4b; background: #bdff4b; color: #11150c; font-weight: 700; }
.action-buttons button:disabled { opacity: 0.5; cursor: not-allowed; }

.ai-chat-composer { padding: 12px 13px 11px; border-top: 1px solid #292e36; background: #171a20; }
.key-warning { margin-bottom: 8px; padding: 7px 9px; border: 1px solid rgba(255, 178, 82, 0.3); border-radius: 7px; color: #ffbd68; background: rgba(255, 178, 82, 0.08); font-size: 11px; cursor: pointer; }
.composer-row { gap: 8px; }
.composer-row textarea { flex: 1; resize: none; padding: 9px 11px; border: 1px solid #333a44; border-radius: 10px; outline: 0; background: #101318; color: #edf1e9; font: inherit; font-size: 13px; line-height: 1.45; }
.composer-row textarea:focus { border-color: #91c33d; }
.send-button { flex: 0 0 40px; height: 40px; border: 0; border-radius: 10px; background: #bdff4b; color: #11150c; display: grid; place-items: center; cursor: pointer; }
.send-button:disabled { opacity: 0.32; cursor: not-allowed; }
.ai-chat-composer small { display: block; margin-top: 8px; color: #69727e; font-size: 10px; text-align: center; }

.chat-panel-enter-active, .chat-panel-leave-active { transition: opacity 0.18s ease, transform 0.18s ease; transform-origin: right bottom; }
.chat-panel-enter-from, .chat-panel-leave-to { opacity: 0; transform: translateY(12px) scale(0.97); }
@keyframes typing { from { opacity: 0.3; transform: translateY(1px); } to { opacity: 1; transform: translateY(-2px); } }

@media (max-width: 640px) {
  .ai-chat-widget { right: 14px; bottom: 14px; }
  .ai-chat-panel { width: calc(100vw - 28px); height: min(680px, calc(100vh - 28px)); }
}
</style>
