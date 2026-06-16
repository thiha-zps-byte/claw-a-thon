<script setup lang="ts">
import { ref, watch } from 'vue'
import Button from 'primevue/button'
import SelectButton from 'primevue/selectbutton'
import { api, type LogRecord } from '@/api/client'

const logs = ref<LogRecord[]>([])
const loading = ref(false)
const level = ref('')
const view = ref<'pretty' | 'raw'>('pretty')

const levelOptions = [
  { label: 'Tất cả', value: '' },
  { label: 'INFO', value: 'INFO' },
  { label: 'WARNING', value: 'WARNING' },
  { label: 'ERROR', value: 'ERROR' },
]
const viewOptions = [
  { label: 'Đẹp', value: 'pretty' },
  { label: 'Raw', value: 'raw' },
]

async function load() {
  loading.value = true
  try {
    logs.value = await api.getDebugLogs(level.value || undefined)
  } catch {
    logs.value = []
  } finally {
    loading.value = false
  }
}

// Split "k=v k2=v2 free text" into chips for the pretty single-line view.
function kvPairs(message: string): { k: string; v: string }[] {
  return message
    .split(' ')
    .map((tok) => {
      const i = tok.indexOf('=')
      return i > 0 ? { k: tok.slice(0, i), v: tok.slice(i + 1) } : null
    })
    .filter((p): p is { k: string; v: string } => p !== null)
}
function plainText(message: string): string {
  return message.split(' ').filter((tok) => tok.indexOf('=') <= 0).join(' ')
}

watch(level, load)
load()
</script>

<template>
  <section class="logs-panel">
    <div class="logs-head">
      <h3 class="logs-title">Nhật ký hệ thống</h3>
      <div class="logs-controls">
        <SelectButton v-model="level" :options="levelOptions" option-label="label" option-value="value" :allow-empty="false" />
        <SelectButton v-model="view" :options="viewOptions" option-label="label" option-value="value" :allow-empty="false" />
        <Button label="Làm mới" icon="pi pi-refresh" size="small" text :loading="loading" @click="load" />
      </div>
    </div>
    <p class="muted hint">Log gần đây của máy chủ (đọc từ file trên đĩa). Log đầy đủ ở console GreenNode.</p>

    <p v-if="!logs.length" class="muted empty">Chưa có log.</p>
    <ul v-else class="logs">
      <li v-for="(l, i) in logs" :key="i" class="log-row">
        <div class="log-meta">
          <span class="lvl" :class="l.level.toLowerCase()">{{ l.level }}</span>
          <span class="log-time muted">{{ l.time?.slice(11, 19) }}</span>
          <span class="log-logger">{{ l.logger }}</span>
        </div>
        <div class="log-body">
          <template v-if="view === 'pretty' && !l.message.includes('\n')">
            <span v-if="plainText(l.message)" class="log-msg">{{ plainText(l.message) }}</span>
            <span v-for="(p, k) in kvPairs(l.message)" :key="k" class="kv"><b>{{ p.k }}</b>={{ p.v }}</span>
          </template>
          <pre v-else class="log-raw">{{ l.message }}</pre>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.logs-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.logs-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.logs-title {
  font-size: 1.05rem;
  font-weight: 700;
}
.logs-controls {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.logs-controls :deep(.p-selectbutton .p-button) {
  font-size: 0.78rem;
  padding: 5px 10px;
}
.hint {
  font-size: 0.78rem;
  margin: -4px 0 0;
}
.empty {
  padding: 24px 4px;
}
.logs {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.log-row {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
}
.log-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}
.lvl {
  font-size: 0.66rem;
  font-weight: 700;
  padding: 1px 7px;
  border-radius: 5px;
  background: var(--bg);
  color: var(--text-muted);
}
.lvl.warning {
  background: #fff4e5;
  color: #b9770e;
}
.lvl.error {
  background: #fdecea;
  color: #c0392b;
}
.lvl.info {
  background: var(--green-soft);
  color: var(--green);
}
.log-time {
  font-size: 0.74rem;
}
.log-logger {
  font-weight: 600;
  color: var(--text-muted);
  font-size: 0.8rem;
}
.log-body {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
  font-size: 0.82rem;
}
.kv {
  font-size: 0.76rem;
  background: var(--bg);
  border-radius: 5px;
  padding: 0 6px;
}
.kv b {
  color: var(--text-muted);
}
.log-raw {
  margin: 0;
  width: 100%;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.76rem;
  line-height: 1.45;
  background: var(--bg);
  border-radius: 6px;
  padding: 8px 10px;
  max-height: 260px;
  overflow: auto;
}
</style>
