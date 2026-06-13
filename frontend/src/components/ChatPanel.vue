<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import Button from 'primevue/button'
import Textarea from 'primevue/textarea'
import TypingIndicator from './TypingIndicator.vue'
import EmptyState from './EmptyState.vue'
import emptyChat from '@/assets/svg/empty-chat.svg'
import { api, ApiException, type Bot } from '@/api/client'
import { useBotsStore } from '@/stores/bots'

const props = defineProps<{ bot: Bot }>()
const store = useBotsStore()

// When the bot has no documents it can only answer generically — nudge toward adding
// knowledge instead of inviting a chat that will disappoint.
const emptyHint = computed(() =>
  store.documents.length === 0
    ? 'Bot chưa có tài liệu nên sẽ trả lời chung chung. Mở tab “Tài liệu” để nạp tài liệu (hoặc dùng bộ mẫu) — bot sẽ trả lời sát game của bạn.'
    : 'Thử hỏi như một người chơi thật: “alo”, “mình quên mật khẩu”, “nạp thẻ không nhận xu”…',
)

interface Msg {
  role: 'user' | 'bot'
  text: string
  failed?: boolean
}

const messages = ref<Msg[]>([])
const draft = ref('')
const typing = ref(false)
const scroller = ref<HTMLElement | null>(null)
const lastFailedInput = ref<string | null>(null)

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
}

async function scrollDown() {
  await nextTick()
  scroller.value?.scrollTo({ top: scroller.value.scrollHeight, behavior: 'smooth' })
}

function splitReply(text: string): string[] {
  // Human texting feel: split a long reply into at most 2 bubbles on a blank line.
  if (text.length < 220) return [text]
  const parts = text.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean)
  if (parts.length <= 1) return [text]
  return [parts[0], parts.slice(1).join('\n\n')]
}

async function send() {
  const text = draft.value.trim()
  if (!text || typing.value) return
  messages.value.push({ role: 'user', text })
  draft.value = ''
  lastFailedInput.value = null
  await scrollDown()
  typing.value = true
  try {
    const res = await api.chat(props.bot.id, text)
    // Human-like pause before the reply appears (already "thinking" while waiting).
    await sleep(Math.max(0, res.delay * 1000 - 200))
    const bubbles = splitReply(res.reply)
    for (let i = 0; i < bubbles.length; i++) {
      if (i > 0) await sleep(700)
      messages.value.push({ role: 'bot', text: bubbles[i] })
      await scrollDown()
    }
  } catch (e) {
    const msg = e instanceof ApiException ? e.message : 'Có lỗi xảy ra, vui lòng thử lại.'
    messages.value.push({ role: 'bot', text: msg, failed: true })
    lastFailedInput.value = text
  } finally {
    typing.value = false
    await scrollDown()
  }
}

function retry() {
  if (lastFailedInput.value) {
    draft.value = lastFailedInput.value
    send()
  }
}

function onEnter(e: KeyboardEvent) {
  // While a Vietnamese IME (Telex/VNI…) is composing, Enter commits the in-progress
  // character — don't send yet, or the just-committed text is left behind in the box.
  if (e.isComposing || e.keyCode === 229) return
  e.preventDefault()
  send()
}
</script>

<template>
  <div class="chat">
    <div ref="scroller" class="messages">
      <EmptyState
        v-if="messages.length === 0 && !typing"
        :image="emptyChat"
        :title="`Trò chuyện với ${bot.name}`"
        :hint="emptyHint"
      />
      <TransitionGroup name="bubble" tag="div" class="msg-list">
        <div v-for="(m, i) in messages" :key="i" class="row" :class="m.role">
          <div class="bubble" :class="{ failed: m.failed }">
            {{ m.text }}
            <Button
              v-if="m.failed && lastFailedInput"
              label="Thử lại"
              icon="pi pi-refresh"
              size="small"
              text
              class="retry"
              @click="retry"
            />
          </div>
        </div>
      </TransitionGroup>
      <div v-if="typing" class="row bot">
        <div class="bubble typing-bubble">
          <TypingIndicator :label="`${bot.name} đang soạn…`" />
        </div>
      </div>
    </div>

    <div class="composer">
      <Textarea
        v-model="draft"
        rows="1"
        auto-resize
        placeholder="Nhập tin nhắn như một người chơi…"
        aria-label="Tin nhắn"
        class="input"
        @keydown.enter.exact="onEnter"
      />
      <Button
        icon="pi pi-send"
        aria-label="Gửi tin nhắn"
        rounded
        :disabled="!draft.trim() || typing"
        @click="send"
      />
    </div>
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.msg-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.row {
  display: flex;
}
.row.user {
  justify-content: flex-end;
}
.row.bot {
  justify-content: flex-start;
}
.bubble {
  max-width: 78%;
  padding: 11px 15px;
  border-radius: 16px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
}
.row.user .bubble {
  background: var(--green);
  color: #fff;
  border-bottom-right-radius: 5px;
}
.row.bot .bubble {
  background: var(--surface);
  border: 1px solid var(--border);
  border-bottom-left-radius: 5px;
}
.bubble.failed {
  background: #fdecea;
  border-color: #f5c6cb;
  color: #a5342a;
}
.typing-bubble {
  padding: 0;
}
.retry {
  margin-top: 4px;
}
.composer {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 14px 16px;
  border-top: 1px solid var(--border);
  background: var(--surface);
}
.input {
  flex: 1;
  resize: none;
  max-height: 140px;
}
:deep(.input.p-textarea) {
  width: 100%;
}
</style>
