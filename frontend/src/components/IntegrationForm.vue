<script setup lang="ts">
import { reactive, ref, watch, computed } from 'vue'
import InputText from 'primevue/inputtext'
import ToggleSwitch from 'primevue/toggleswitch'
import Button from 'primevue/button'
import { api, type Bot } from '@/api/client'

const props = defineProps<{
  botId: string
  initial?: Partial<Bot>
  submitLabel: string
  submitting?: boolean
  readonly?: boolean
}>()
const emit = defineEmits<{ (e: 'submit', data: Partial<Bot>): void }>()

// Secrets are write-only: the server only tells us whether one is stored, never its
// value. We keep these inputs blank and only send a value when the operator types a
// new one (blank = keep the stored secret).
const form = reactive({
  messenger_enabled: false,
  messenger_page_id: '',
  messenger_verify_token: '',
  messenger_page_token: '',
  messenger_app_secret: '',
})
const pageTokenSet = ref(false)
const appSecretSet = ref(false)

watch(
  () => props.initial,
  (v) => {
    if (!v) return
    form.messenger_enabled = !!v.messenger_enabled
    form.messenger_page_id = v.messenger_page_id ?? ''
    form.messenger_verify_token = v.messenger_verify_token ?? ''
    form.messenger_page_token = ''
    form.messenger_app_secret = ''
    pageTokenSet.value = !!v.messenger_page_token_set
    appSecretSet.value = !!v.messenger_app_secret_set
  },
  { immediate: true },
)

const callbackUrl = computed(() =>
  typeof window !== 'undefined' ? window.location.origin + '/api/webhooks/messenger' : '',
)
const copied = ref(false)
async function copyCallback() {
  try {
    await navigator.clipboard.writeText(callbackUrl.value)
    copied.value = true
    setTimeout(() => (copied.value = false), 1800)
  } catch {
    /* clipboard blocked — user can select manually */
  }
}

// --- validate (ID + token against Graph API) ---
const validating = ref(false)
const validateResult = ref<{ ok: boolean; message: string } | null>(null)
async function validate() {
  validating.value = true
  validateResult.value = null
  try {
    const r = await api.validateMessenger(props.botId, {
      page_id: form.messenger_page_id,
      page_token: form.messenger_page_token,
    })
    validateResult.value = r.ok
      ? { ok: true, message: `Đã xác minh Page «${r.page_name || form.messenger_page_id}»` }
      : { ok: false, message: r.error || 'Không xác minh được.' }
  } catch (e) {
    validateResult.value = { ok: false, message: (e as Error).message || 'Không xác minh được.' }
  } finally {
    validating.value = false
  }
}

// --- auto-subscribe the Page to message events ---
const subscribing = ref(false)
const subscribeResult = ref<{ ok: boolean; message: string } | null>(null)
async function subscribe() {
  subscribing.value = true
  subscribeResult.value = null
  try {
    const r = await api.subscribeMessenger(props.botId, { page_token: form.messenger_page_token })
    subscribeResult.value = r.ok
      ? { ok: true, message: 'Đã đăng ký Page nhận tin nhắn' }
      : { ok: false, message: r.error || 'Đăng ký thất bại.' }
  } catch (e) {
    subscribeResult.value = { ok: false, message: (e as Error).message || 'Đăng ký thất bại.' }
  } finally {
    subscribing.value = false
  }
}

// --- simulate (dry-run inbound message) ---
const testText = ref('')
const testing = ref(false)
const testReply = ref<string | null>(null)
async function runTest() {
  if (!testText.value.trim()) return
  testing.value = true
  testReply.value = null
  try {
    const r = await api.simulateMessenger(props.botId, testText.value.trim())
    testReply.value = r.reply
  } catch (e) {
    testReply.value = '⚠️ ' + ((e as Error).message || 'Gửi thử thất bại.')
  } finally {
    testing.value = false
  }
}

function submit() {
  emit('submit', { ...form })
}
</script>

<template>
  <form class="integration-form" @submit.prevent="submit">
    <label class="switch-row">
      <ToggleSwitch v-model="form.messenger_enabled" :disabled="readonly" />
      <span class="field-label">Bật kết nối Facebook Messenger</span>
    </label>

    <label class="field">
      <span class="field-label">Page ID</span>
      <InputText v-model="form.messenger_page_id" :disabled="readonly" placeholder="VD: 102345678901234" aria-label="Page ID" />
      <span class="field-hint">ID của Facebook Page (Trang) sẽ kết nối với bot này.</span>
    </label>

    <label class="field">
      <span class="field-label">Verify Token</span>
      <InputText
        v-model="form.messenger_verify_token"
        :disabled="readonly"
        placeholder="Chuỗi bạn tự đặt, dùng khi cấu hình webhook"
        aria-label="Verify Token"
      />
      <span class="field-hint">Tự đặt — dán đúng chuỗi này vào Meta App khi thêm webhook.</span>
    </label>

    <label class="field">
      <span class="field-label">Page Access Token</span>
      <InputText
        v-model="form.messenger_page_token"
        :disabled="readonly"
        type="password"
        :placeholder="pageTokenSet ? '•••••••• (đã lưu — để trống nếu giữ nguyên)' : 'EAAB...'"
        aria-label="Page Access Token"
      />
    </label>

    <label class="field">
      <span class="field-label">App Secret</span>
      <InputText
        v-model="form.messenger_app_secret"
        :disabled="readonly"
        type="password"
        :placeholder="appSecretSet ? '•••••••• (đã lưu — để trống nếu giữ nguyên)' : 'App Secret của Meta App'"
        aria-label="App Secret"
      />
      <span class="field-hint">Dùng để xác minh chữ ký request từ Facebook (an toàn hơn).</span>
    </label>

    <!-- Validate ID + token -->
    <div v-if="!readonly" class="inline-action">
      <Button
        type="button"
        label="Kiểm tra kết nối"
        icon="pi pi-shield"
        outlined
        size="small"
        :loading="validating"
        @click="validate"
      />
      <Transition name="fade">
        <span
          v-if="validateResult"
          class="result-chip"
          :class="validateResult.ok ? 'ok' : 'err'"
        >
          <i :class="validateResult.ok ? 'pi pi-check-circle' : 'pi pi-times-circle'" aria-hidden="true" />
          {{ validateResult.message }}
        </span>
      </Transition>
    </div>

    <!-- Auto-subscribe the Page (skips the manual Meta dashboard step) -->
    <div v-if="!readonly" class="inline-action">
      <Button
        type="button"
        label="Đăng ký Page nhận tin"
        icon="pi pi-bolt"
        outlined
        size="small"
        :loading="subscribing"
        @click="subscribe"
      />
      <Transition name="fade">
        <span
          v-if="subscribeResult"
          class="result-chip"
          :class="subscribeResult.ok ? 'ok' : 'err'"
        >
          <i :class="subscribeResult.ok ? 'pi pi-check-circle' : 'pi pi-times-circle'" aria-hidden="true" />
          {{ subscribeResult.message }}
        </span>
      </Transition>
    </div>

    <!-- Callback URL helper -->
    <div class="callback">
      <span class="field-label">Callback URL (dán vào Meta App → Webhooks)</span>
      <div class="callback-row">
        <code class="callback-url">{{ callbackUrl }}</code>
        <Button
          type="button"
          :icon="copied ? 'pi pi-check' : 'pi pi-copy'"
          :label="copied ? 'Đã chép' : 'Chép'"
          text
          size="small"
          @click="copyCallback"
        />
      </div>
    </div>

    <!-- Self-test before connecting a real Page -->
    <div v-if="!readonly" class="test-box">
      <span class="field-label">Gửi thử (giả lập Messenger)</span>
      <span class="field-hint">
        Kiểm tra bot trả lời thế nào mà chưa cần Page thật — chạy đúng luồng như tin nhắn Messenger.
      </span>
      <div class="test-row">
        <InputText
          v-model="testText"
          placeholder="VD: cho mình hỏi cách nạp thẻ"
          aria-label="Tin nhắn thử"
          @keydown.enter.prevent="runTest"
        />
        <Button
          type="button"
          label="Gửi thử"
          icon="pi pi-send"
          size="small"
          :loading="testing"
          :disabled="!testText.trim()"
          @click="runTest"
        />
      </div>
      <Transition name="fade">
        <div v-if="testReply !== null" class="test-reply">
          <span class="muted">Bot trả lời:</span>
          <p>{{ testReply }}</p>
        </div>
      </Transition>
    </div>

    <div v-if="!readonly" class="actions">
      <Button type="submit" :label="submitLabel" icon="pi pi-check" :loading="submitting" />
    </div>
  </form>
</template>

<style scoped>
.integration-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field-label {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-muted);
}
.field-hint {
  font-size: 0.76rem;
  color: var(--text-muted);
}
.switch-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
:deep(.p-inputtext) {
  width: 100%;
}
.inline-action {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.result-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.82rem;
  padding: 4px 10px;
  border-radius: 999px;
}
.result-chip.ok {
  background: var(--green-soft);
  color: var(--green);
}
.result-chip.err {
  background: #fdecea;
  color: #c0392b;
}
.callback {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.callback-row {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--green-soft);
  border-radius: 10px;
  padding: 8px 10px;
}
.callback-url {
  flex: 1;
  font-size: 0.8rem;
  word-break: break-all;
  color: var(--text);
}
.test-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border: 1px dashed var(--border);
  border-radius: 10px;
}
.test-row {
  display: flex;
  gap: 8px;
}
.test-row :deep(.p-inputtext) {
  flex: 1;
}
.test-reply {
  font-size: 0.86rem;
  line-height: 1.5;
}
.test-reply p {
  margin: 4px 0 0;
  white-space: pre-wrap;
}
.actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 4px;
}
/* Fade so results ease in instead of popping (avoids abrupt motion). */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
