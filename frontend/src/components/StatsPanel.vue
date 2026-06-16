<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Chart from 'primevue/chart'
import Dialog from 'primevue/dialog'
import SelectButton from 'primevue/selectbutton'
import Button from 'primevue/button'
import StatCard from './StatCard.vue'
import SkeletonList from './SkeletonList.vue'
import {
  api,
  ApiException,
  type StatsOverview,
  type PlayerRow,
  type ConversationTurn,
} from '@/api/client'

const props = defineProps<{ botId: string }>()

const ranges = [
  { label: '7 ngày', value: '7d' },
  { label: '30 ngày', value: '30d' },
  { label: 'Tất cả', value: 'all' },
]
const range = ref('7d')

const overview = ref<StatsOverview | null>(null)
const players = ref<PlayerRow[]>([])
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [ov, pl] = await Promise.all([
      api.getStatsOverview(props.botId, range.value),
      api.getPlayers(props.botId, range.value),
    ])
    overview.value = ov
    players.value = pl
  } catch (e) {
    error.value = e instanceof ApiException ? e.message : 'Không tải được thống kê.'
  } finally {
    loading.value = false
  }
}

watch([() => props.botId, range], load, { immediate: true })

const isEmpty = computed(() => !!overview.value && overview.value.totals.messages === 0)

// --- formatting ---
function fmtMs(n: number) {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}s` : `${n}ms`
}
function fmtTime(iso: string) {
  return new Date(iso).toLocaleString('vi-VN', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}
const channelLabel: Record<string, string> = { web: 'Web', messenger: 'Messenger' }
function chLabel(c: string) {
  return channelLabel[c] ?? c
}
const channelLine = computed(() =>
  (overview.value?.by_channel ?? []).map((c) => `${chLabel(c.channel)} ${c.count}`).join(' · '),
)

// --- charts (only where a chart adds insight: trend + ranking) ---
const css = getComputedStyle(document.documentElement)
const GREEN = css.getPropertyValue('--green').trim() || '#0f7f4d'
const baseOptions = {
  animation: { duration: 300 },
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
}

const lineData = computed(() => ({
  labels: (overview.value?.messages_per_day ?? []).map((d) => d.date.slice(5)),
  datasets: [
    {
      data: (overview.value?.messages_per_day ?? []).map((d) => d.count),
      borderColor: GREEN,
      backgroundColor: 'rgba(15,127,77,0.10)',
      fill: true,
      tension: 0.3,
      pointRadius: 2,
    },
  ],
}))

const categoryData = computed(() => ({
  labels: (overview.value?.top_categories ?? []).map((c) => c.category),
  datasets: [
    { data: (overview.value?.top_categories ?? []).map((c) => c.count), backgroundColor: GREEN },
  ],
}))
const barOptions = {
  ...baseOptions,
  indexAxis: 'y' as const,
  scales: { x: { ticks: { precision: 0 } } },
}

// --- per-player conversation viewer ---
const dialogOpen = ref(false)
const activePlayer = ref<PlayerRow | null>(null)
const convo = ref<ConversationTurn[]>([])
const convoLoading = ref(false)

async function openPlayer(p: PlayerRow) {
  activePlayer.value = p
  dialogOpen.value = true
  convoLoading.value = true
  convo.value = []
  try {
    convo.value = await api.getConversation(props.botId, p.channel, p.sender_id)
  } finally {
    convoLoading.value = false
  }
}
</script>

<template>
  <div class="stats">
    <div class="stats-head">
      <h3 class="stats-title">Thống kê vận hành</h3>
      <SelectButton v-model="range" :options="ranges" option-label="label" option-value="value"
                    :allow-empty="false" aria-label="Khoảng thời gian" />
    </div>

    <SkeletonList v-if="loading && !overview" :rows="3" :height="72" />
    <p v-else-if="error" class="stats-error">{{ error }}</p>
    <p v-else-if="isEmpty" class="stats-empty muted">
      Chưa có dữ liệu trong khoảng này. Chat với bot ở tab «Chat», hoặc chọn «Tất cả».
    </p>

    <template v-else-if="overview">
      <!-- KPI: just the numbers an operator acts on -->
      <section class="kpi-row">
        <StatCard label="Người chơi" :value="overview.totals.players"
                  :hint="`${overview.totals.new_players} mới · ${overview.totals.returning_players} quay lại`" />
        <StatCard label="Tin nhắn" :value="overview.totals.messages" :hint="channelLine" />
        <StatCard label="Bot tự trả lời" :value="overview.totals.auto_answer_rate + '%'"
                  :hint="`${overview.totals.degraded_count} câu bot bí`" />
        <StatCard label="Phản hồi p50 / p95"
                  :value="fmtMs(overview.totals.latency_p50_ms)"
                  :hint="`p95 ${fmtMs(overview.totals.latency_p95_ms)}`" />
      </section>

      <!-- Trend + category ranking -->
      <section class="charts">
        <div class="chart-card">
          <h4>Tin nhắn / ngày</h4>
          <Chart type="line" :data="lineData" :options="baseOptions" class="chart-canvas" />
        </div>
        <div class="chart-card">
          <h4>Chủ đề hỏi nhiều</h4>
          <Chart type="bar" :data="categoryData" :options="barOptions" class="chart-canvas" />
        </div>
      </section>

      <!-- Knowledge gaps -->
      <section v-if="overview.unanswered.length" class="block">
        <h4>Câu bot chưa trả lời được ({{ overview.unanswered.length }})</h4>
        <p class="muted block-hint">Bổ sung những câu này vào tài liệu để bot trả lời được.</p>
        <ul class="plain-list">
          <li v-for="(u, i) in overview.unanswered" :key="i">
            <span class="q">{{ u.question }}</span>
            <span class="meta">{{ chLabel(u.channel) }} · {{ fmtTime(u.created_at) }}</span>
          </li>
        </ul>
      </section>

      <!-- Players -->
      <section class="block">
        <h4>Người chơi ({{ players.length }})</h4>
        <p class="muted block-hint">Bấm để xem lại hội thoại.</p>
        <table class="data-table">
          <thead>
            <tr><th>Người chơi</th><th>Kênh</th><th class="num">Số tin</th><th>Lần cuối</th></tr>
          </thead>
          <tbody>
            <tr v-for="p in players" :key="p.channel + p.sender_id" class="row-click"
                tabindex="0" @click="openPlayer(p)" @keydown.enter="openPlayer(p)">
              <td class="sid">{{ p.sender_id }}</td>
              <td>{{ chLabel(p.channel) }}</td>
              <td class="num">{{ p.message_count }}</td>
              <td>{{ fmtTime(p.last_at) }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>

    <!-- Conversation replay: plain transcript -->
    <Dialog v-model:visible="dialogOpen" modal :style="{ width: '40rem' }"
            :breakpoints="{ '640px': '95vw' }"
            :header="activePlayer ? `Hội thoại · ${activePlayer.sender_id}` : 'Hội thoại'">
      <SkeletonList v-if="convoLoading" :rows="3" :height="44" />
      <p v-else-if="!convo.length" class="muted">Không có tin nhắn.</p>
      <div v-else class="convo">
        <div v-for="(t, i) in convo" :key="i" class="turn">
          <div class="line"><span class="who">Người chơi</span>{{ t.question }}</div>
          <div class="line"><span class="who">Bot<template v-if="t.degraded"> (bí)</template></span>{{ t.reply }}</div>
          <div class="turn-meta muted">{{ t.category || 'khác' }} · {{ fmtTime(t.created_at) }}</div>
        </div>
      </div>
      <template #footer>
        <Button label="Đóng" text @click="dialogOpen = false" />
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
.stats {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.stats-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.stats-title {
  font-size: 1rem;
  font-weight: 700;
}
.stats-error {
  color: #c0392b;
}
.stats-empty {
  padding: 32px 4px;
}
.kpi-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.charts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.chart-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
}
.chart-card h4 {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 8px;
}
.chart-canvas {
  height: 220px;
}
.block h4 {
  font-size: 0.9rem;
  font-weight: 700;
}
.block-hint {
  font-size: 0.78rem;
  margin: 3px 0 8px;
}
.plain-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
}
.plain-list li {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
}
.plain-list li:last-child {
  border-bottom: none;
}
.plain-list .q {
  font-size: 0.86rem;
}
.plain-list .meta {
  font-size: 0.74rem;
  color: var(--text-muted);
  white-space: nowrap;
}
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.86rem;
}
.data-table th {
  text-align: left;
  font-size: 0.74rem;
  color: var(--text-muted);
  font-weight: 600;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
}
.data-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
}
.data-table .num {
  text-align: right;
}
.data-table .sid {
  font-family: ui-monospace, monospace;
  font-size: 0.8rem;
}
.row-click {
  cursor: pointer;
}
.row-click:hover,
.row-click:focus-visible {
  background: var(--bg);
  outline: none;
}
.convo {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-height: 60vh;
  overflow-y: auto;
}
.turn {
  display: flex;
  flex-direction: column;
  gap: 3px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 10px;
}
.line {
  font-size: 0.88rem;
  line-height: 1.5;
  white-space: pre-wrap;
}
.line .who {
  font-weight: 700;
  color: var(--text-muted);
  margin-right: 6px;
}
.turn-meta {
  font-size: 0.72rem;
}
@media (max-width: 640px) {
  .charts {
    grid-template-columns: 1fr;
  }
}
</style>
