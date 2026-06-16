<script setup lang="ts">
import { ref, computed } from 'vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'
import BotForm from './BotForm.vue'
import DocumentPanel from './DocumentPanel.vue'
import SkeletonList from './SkeletonList.vue'
import EmptyState from './EmptyState.vue'
import emptyBots from '@/assets/svg/empty-bots.svg'
import { useBotsStore } from '@/stores/bots'
import { useUserStore } from '@/stores/user'
import { ApiException, type Bot } from '@/api/client'

const store = useBotsStore()
const user = useUserStore()
const toast = useToast()
const showCreate = ref(false)
const creating = ref(false)
const step = ref<1 | 2>(1)
const newBotId = ref<string | null>(null)

// A new user only ever sees the shared demo bot (it's always in the list), so the
// empty-state never shows — surface a clear "create your own" prompt in that case.
const hasOwnBot = computed(() => store.bots.some((b) => b.owner_uid === user.uid))

const stepHeader = computed(() =>
  step.value === 1 ? 'Tạo bot mới · Bước 1/2: Thông tin' : 'Tạo bot mới · Bước 2/2: Tài liệu',
)

function openCreate() {
  step.value = 1
  newBotId.value = null
  showCreate.value = true
}

// Step 1 → create the bot, then move to the documents step (most important input).
async function onInfoSubmit(data: Partial<Bot>) {
  creating.value = true
  try {
    const bot = await store.createBot(data)
    await store.selectBot(bot.id)
    newBotId.value = bot.id
    step.value = 2
    toast.add({ severity: 'success', summary: 'Đã tạo bot — giờ thêm tài liệu nhé', life: 2500 })
  } catch (e) {
    const msg = e instanceof ApiException ? e.message : 'Tạo bot thất bại.'
    toast.add({ severity: 'error', summary: 'Lỗi', detail: msg, life: 5000 })
  } finally {
    creating.value = false
  }
}

function finish() {
  showCreate.value = false
}
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-head">
      <h2 class="sidebar-title">Bots</h2>
      <Button icon="pi pi-plus" aria-label="Tạo bot mới" rounded @click="openCreate" />
    </div>

    <SkeletonList v-if="store.loadingBots" :rows="4" :height="52" />

    <EmptyState
      v-else-if="store.bots.length === 0"
      :image="emptyBots"
      title="Chưa có bot nào"
      hint="Tạo một bot CS đầu tiên cho game của bạn."
    >
      <Button label="Tạo bot" icon="pi pi-plus" @click="openCreate" />
    </EmptyState>

    <template v-else>
      <div v-if="!hasOwnBot" class="own-cta">
        <span class="own-cta-title">Bạn chưa có bot nào</span>
        <span class="own-cta-hint">Tạo trợ lý CS cho game của bạn. Bot mẫu bên dưới chỉ để xem thử.</span>
        <Button label="Tạo bot của bạn" icon="pi pi-plus" size="small" @click="openCreate" />
      </div>
      <ul class="bot-list">
        <li v-for="b in store.bots" :key="b.id">
          <button
            type="button"
            class="bot-item"
            :class="{ active: store.currentBot?.id === b.id }"
            @click="store.selectBot(b.id)"
          >
            <span class="avatar" aria-hidden="true">{{ b.name.charAt(0).toUpperCase() }}</span>
            <span class="bot-info">
              <span class="bot-name">{{ b.name }}</span>
              <span v-if="b.is_shared" class="shared-tag">
                <i class="pi pi-users" aria-hidden="true" />
                {{ b.owner_uid === user.uid ? 'Dùng chung' : 'Dùng chung · chỉ xem' }}
              </span>
              <span class="muted bot-sub">
                <i class="pi pi-file" aria-hidden="true" /> {{ b.document_count ?? 0 }} tài liệu
              </span>
            </span>
          </button>
        </li>
      </ul>
    </template>

    <Dialog
      v-model:visible="showCreate"
      modal
      :header="stepHeader"
      :style="{ width: '38rem' }"
      :breakpoints="{ '640px': '95vw' }"
    >
      <template v-if="step === 1">
        <div class="needs">
          <span class="needs-title">Bạn sẽ cần:</span>
          <ol class="needs-list">
            <li>Mô tả + cách xưng hô (điền bên dưới)</li>
            <li><strong>Tài liệu</strong> (FAQ/hướng dẫn) — nguồn kiến thức của bot, <strong>quan trọng nhất</strong>, thêm ở bước sau</li>
          </ol>
        </div>
        <BotForm submit-label="Tiếp tục → Tài liệu" :submitting="creating" @submit="onInfoSubmit" />
      </template>

      <template v-else-if="step === 2">
        <p class="step2-hint">
          Nạp tài liệu để bot trả lời <strong>đúng game của bạn</strong> — chưa có thì bot chỉ trả lời chung
          chung. Có thể kéo-thả file hoặc <strong>dùng bộ mẫu sẵn</strong>.
        </p>
        <DocumentPanel v-if="newBotId" :bot-id="newBotId" />
        <div class="wizard-actions">
          <Button label="Bỏ qua" text severity="secondary" @click="finish" />
          <Button label="Hoàn tất" icon="pi pi-check" @click="finish" />
        </div>
      </template>
    </Dialog>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 300px;
  flex-shrink: 0;
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 16px;
  gap: 12px;
  overflow-y: auto;
}
.sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.sidebar-title {
  font-size: 1rem;
  font-weight: 700;
}
.own-cta {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding: 12px 14px;
  margin-bottom: 10px;
  background: var(--green-soft);
  border: 1px solid #cdf0dc;
  border-radius: var(--radius);
}
.own-cta-title {
  font-weight: 700;
  font-size: 0.9rem;
}
.own-cta-hint {
  font-size: 0.78rem;
  color: var(--text-muted);
  line-height: 1.45;
}
.bot-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.bot-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  cursor: pointer;
  text-align: left;
  font: inherit;
  color: inherit;
}
.bot-item:hover {
  background: var(--green-soft);
}
.bot-item.active {
  background: var(--green-soft);
  border-color: #b9ddc8;
}
.avatar {
  width: 38px;
  height: 38px;
  border-radius: 11px;
  background: var(--green);
  color: #fff;
  display: grid;
  place-items: center;
  font-weight: 700;
  flex-shrink: 0;
}
.bot-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.bot-name {
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bot-sub {
  font-size: 0.78rem;
}
.shared-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  align-self: flex-start;
  margin: 2px 0;
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--green-soft);
  color: var(--green);
  font-size: 0.68rem;
  font-weight: 600;
}
.needs {
  background: var(--green-soft);
  border-radius: 10px;
  padding: 10px 14px;
  margin-bottom: 14px;
  font-size: 0.84rem;
}
.needs-title {
  font-weight: 700;
}
.needs-list {
  margin: 6px 0 0;
  padding-left: 20px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  color: var(--text-muted);
}
.step2-hint {
  margin: 0 0 14px;
  font-size: 0.86rem;
  color: var(--text-muted);
  line-height: 1.5;
}
.wizard-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}
</style>
