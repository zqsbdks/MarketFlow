<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { Bot, KeyRound, RotateCcw, Send, Settings, Sparkles, X } from '@lucide/vue'

import { sendAiChat } from '../api'
import { getErrorMessage } from '../api/http'
import type { AiChatMessage } from '../types/api'

const API_KEY_STORAGE_KEY = 'marketflow_gemini_api_key'
const MODEL_STORAGE_KEY = 'marketflow_gemini_model'
const DEFAULT_MODEL = 'gemini-3.5-flash-lite'

interface DisplayMessage extends AiChatMessage {
  id: number
  localOnly?: boolean
}

const isOpen = ref(false)
const showSettings = ref(false)
const isSending = ref(false)
const input = ref('')
const apiKey = ref(localStorage.getItem(API_KEY_STORAGE_KEY) || '')
const apiKeyDraft = ref(apiKey.value)
const model = ref(localStorage.getItem(MODEL_STORAGE_KEY) || DEFAULT_MODEL)
const modelDraft = ref(model.value)
const messageList = ref<HTMLElement | null>(null)
let nextMessageId = 2

const messages = ref<DisplayMessage[]>([
  {
    id: 1,
    role: 'model',
    content: '你好，我是 MarketFlow 助手。你可以问我系统各模块的用途、操作流程或页面使用方法。',
    localOnly: true,
  },
])

const canSend = computed(() => Boolean(input.value.trim() && apiKey.value && !isSending.value))

function openWidget() {
  isOpen.value = true
  if (!apiKey.value) showSettings.value = true
}

function saveSettings() {
  const cleanKey = apiKeyDraft.value.trim()
  const cleanModel = modelDraft.value.trim() || DEFAULT_MODEL
  apiKey.value = cleanKey
  model.value = cleanModel

  if (cleanKey) localStorage.setItem(API_KEY_STORAGE_KEY, cleanKey)
  else localStorage.removeItem(API_KEY_STORAGE_KEY)
  localStorage.setItem(MODEL_STORAGE_KEY, cleanModel)
  showSettings.value = false
}

function removeApiKey() {
  apiKey.value = ''
  apiKeyDraft.value = ''
  localStorage.removeItem(API_KEY_STORAGE_KEY)
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
}

async function scrollToBottom() {
  await nextTick()
  if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
}

async function submitMessage() {
  const content = input.value.trim()
  if (!content || isSending.value) return
  if (!apiKey.value) {
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

    const result = await sendAiChat(apiKey.value, model.value, history)
    messages.value.push({ id: nextMessageId++, role: 'model', content: result.message })
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
              <span>Gemini 基础问答</span>
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
            Gemini API Key
            <input v-model="apiKeyDraft" type="password" autocomplete="off" placeholder="输入你的 API Key" />
          </label>
          <label>
            模型名称
            <input v-model="modelDraft" type="text" placeholder="gemini-3.5-flash-lite" />
          </label>
          <p>密钥只保存在当前浏览器；请仅在可信设备上使用，线上部署必须启用 HTTPS。</p>
          <div class="settings-actions">
            <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">获取 API Key</a>
            <button v-if="apiKey" class="danger-text" type="button" @click="removeApiKey">删除密钥</button>
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
        </div>

        <footer class="ai-chat-composer">
          <div v-if="!apiKey" class="key-warning" @click="showSettings = true">
            请先设置 Gemini API Key
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
          <small>AI 可能出错，经营数据请以系统页面显示为准。</small>
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
.ai-settings input { min-height: 38px; padding: 0 11px; border: 1px solid #343b45; border-radius: 8px; outline: 0; background: #111419; color: #eef2ea; }
.ai-settings input:focus { border-color: #93c83c; }
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
