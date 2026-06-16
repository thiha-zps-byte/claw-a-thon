<script setup lang="ts">
import { ref, watch } from 'vue'
import Button from 'primevue/button'
import { api, type WebhookDebugResult, type WebhookEvent } from '@/api/client'

const props = defineProps<{ botId: string }>()

const data = ref<WebhookDebugResult | null>(null)
const loading = ref(false)
const expanded = ref<number | null>(null)

async function load() {
  loading.value = true
  try {
    data.value = await api.getWebhookDebug(props.botId)
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
}

// --- validate + subscribe (moved here from the form) ---
const validating = ref(false)
const subscribing = ref(false)
const actionResult = ref<{ ok: boolean; message: string } | null>(null)

async function validate() {
  validating.value = true
  actionResult.value = null
  try {
    const r = await api.validateMessenger(props.botId, {})
    actionResult.value = {
      ok: r.ok,
      message: r.ok ? `Đã xác minh Page «${r.page_name || ''}»` : (r.error || 'Không xác minh được.'),
    }
  } catch (e) {
    actionResult.value = { ok: false, message: (e as Error).message }
  } finally {
    validating.value = false
  }
}
async function subscribe() {
  subscribing.value = true
  actionResult.value = null
  try {
    const r = await api.subscribeMessenger(props.botId, {})
    actionResult.value = {
      ok: r.ok,
      message: r.ok ? 'Đã đăng ký Page nhận tin (messages + feed)' : (r.error || 'Đăng ký thất bại.'),
    }
    await load()
  } catch (e) {
    actionResult.value = { ok: false, message: (e as Error).message }
  } finally {
    subscribing.value = false
  }
}

function eventKind(e: WebhookEvent): string {
  if (e.kind === 'verify') return 'Xác minh webhook'
  if (e.messaging) return `Tin nhắn ×${e.messaging}`
  if (e.changes) return `Bình luận ×${e.changes}`
  return 'Sự kiện'
}
function sigLabel(e: WebhookEvent): string {
  if (e.kind === 'verify') return e.token_matched ? 'token ✓' : 'token ✗'
  if (e.signature_valid === true) return 'chữ ký ✓'
  if (e.signature_valid === false) return 'chữ ký ✗'
  return 'không ký'
}

watch(() => props.botId, load, { immediate: true })
</script>

<template>
  <section class="dbg">
    <div class="dbg-head">
      <h3 class="dbg-title"><i class="pi pi-wrench" aria-hidden="true" /> Debug webhook</h3>
      <Button label="Làm mới" icon="pi pi-refresh" size="small" text :loading="loading" @click="load" />
    </div>

    <div class="status">
      <template v-if="data?.subscribed?.ok">
        <span class="muted">Đã subscribe:</span>
        <span v-for="f in data.subscribed.fields" :key="f" class="chip ok">{{ f }}</span>
        <span v-if="!data.subscribed.fields.length" class="chip warn">chưa có field nào</span>
      </template>
      <span v-else class="chip warn">
        Chưa subscribe được{{ data?.subscribed?.error ? `: ${data.subscribed.error}` : '' }}
      </span>
    </div>

    <div class="actions">
      <Button label="Kiểm tra kết nối" icon="pi pi-shield" outlined size="small" :loading="validating" @click="validate" />
      <Button label="Đăng ký Page nhận tin" icon="pi pi-bolt" outlined size="small" :loading="subscribing" @click="subscribe" />
      <span v-if="actionResult" class="chip" :class="actionResult.ok ? 'ok' : 'err'">{{ actionResult.message }}</span>
    </div>

    <h4 class="sub">Sự kiện Facebook gửi tới ({{ data?.events?.length || 0 }})</h4>
    <p v-if="!data?.events?.length" class="muted empty">
      Chưa nhận webhook nào — hãy nhắn / bình luận thử tới Page rồi bấm «Làm mới».
    </p>
    <ul v-else class="events">
      <li v-for="(e, i) in data.events" :key="i">
        <button type="button" class="ev-row" @click="expanded = expanded === i ? null : i">
          <span class="ev-kind">{{ eventKind(e) }}</span>
          <span class="chip" :class="(e.signature_valid === false || e.token_matched === false) ? 'err' : 'ok'">{{ sigLabel(e) }}</span>
          <span v-if="e.matched === false" class="chip warn">page lạ</span>
          <span class="ev-time muted">{{ e.time?.slice(11, 19) }}</span>
          <i :class="expanded === i ? 'pi pi-chevron-up' : 'pi pi-chevron-down'" aria-hidden="true" />
        </button>
        <pre v-if="expanded === i" class="json">{{ JSON.stringify(e.payload ?? e, null, 2) }}</pre>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.dbg {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.dbg-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.dbg-title {
  font-size: 0.98rem;
  font-weight: 700;
}
.sub {
  font-size: 0.86rem;
  font-weight: 700;
  margin: 4px 0 0;
}
.status,
.actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.chip {
  display: inline-flex;
  align-items: center;
  font-size: 0.74rem;
  font-weight: 600;
  padding: 2px 9px;
  border-radius: 999px;
  background: var(--bg);
  color: var(--text-muted);
}
.chip.ok {
  background: var(--green-soft);
  color: var(--green);
}
.chip.err {
  background: #fdecea;
  color: #c0392b;
}
.chip.warn {
  background: #fff4e5;
  color: #b9770e;
}
.empty {
  font-size: 0.82rem;
}
.events {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ev-row {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  cursor: pointer;
  font: inherit;
  text-align: left;
}
.ev-row:hover {
  background: var(--bg);
}
.ev-kind {
  font-weight: 600;
  font-size: 0.85rem;
}
.ev-time {
  margin-left: auto;
  font-size: 0.78rem;
}
.json {
  margin: 4px 0 0;
  max-height: 300px;
  overflow: auto;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  font-size: 0.76rem;
  line-height: 1.45;
}
</style>
