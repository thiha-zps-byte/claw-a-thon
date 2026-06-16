<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Tabs from 'primevue/tabs'
import TabList from 'primevue/tablist'
import Tab from 'primevue/tab'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'
import ChatPanel from './ChatPanel.vue'
import DocumentPanel from './DocumentPanel.vue'
import BotForm from './BotForm.vue'
import IntegrationForm from './IntegrationForm.vue'
import StatsPanel from './StatsPanel.vue'
import { useBotsStore } from '@/stores/bots'
import { useUserStore } from '@/stores/user'
import { ApiException, type Bot } from '@/api/client'

const props = defineProps<{ bot: Bot }>()
const store = useBotsStore()
const user = useUserStore()
const toast = useToast()
const activeTab = ref('chat')
const saving = ref(false)
const confirmDelete = ref(false)

// A shared "dùng chung" bot is read-only for everyone except its owner (UID "admin").
const editable = computed(() => props.bot.owner_uid === user.uid)
const readonly = computed(() => !editable.value)

watch(
  () => props.bot.id,
  () => {
    activeTab.value = 'chat'
    store.loadDocuments(props.bot.id)
  },
  { immediate: true },
)

async function save(data: Partial<Bot>) {
  saving.value = true
  try {
    await store.updateBot(props.bot.id, data)
    toast.add({ severity: 'success', summary: 'Đã lưu cấu hình', life: 2500 })
  } catch (e) {
    const msg = e instanceof ApiException ? e.message : 'Lưu thất bại.'
    toast.add({ severity: 'error', summary: 'Lỗi', detail: msg, life: 5000 })
  } finally {
    saving.value = false
  }
}

async function remove() {
  try {
    await store.removeBot(props.bot.id)
    confirmDelete.value = false
    toast.add({ severity: 'success', summary: 'Đã xóa bot', life: 2500 })
  } catch {
    toast.add({ severity: 'error', summary: 'Không xóa được bot', life: 4000 })
  }
}
</script>

<template>
  <section class="workspace">
    <div class="ws-head">
      <div class="ws-title">
        <span class="ws-avatar" aria-hidden="true">{{ bot.name.charAt(0).toUpperCase() }}</span>
        <div>
          <h2 class="ws-name">
            {{ bot.name }}
            <Tag
              v-if="bot.is_shared"
              :value="editable ? 'Dùng chung' : 'Dùng chung · Chỉ xem'"
              :icon="editable ? 'pi pi-users' : 'pi pi-lock'"
              severity="info"
              rounded
            />
          </h2>
          <span class="muted ws-sub">
            Gọi người chơi là «{{ bot.player_term }}» · tự xưng «{{ bot.self_term }}»
          </span>
        </div>
      </div>
    </div>

    <p v-if="bot.is_shared && readonly" class="shared-banner">
      <i class="pi pi-info-circle" aria-hidden="true" />
      Đây là bot dùng chung để xem thử — chỉ admin chỉnh sửa được. Bạn vẫn xem đầy đủ và chat thử được.
    </p>

    <Tabs v-model:value="activeTab" class="ws-tabs">
      <TabList>
        <Tab value="chat"><i class="pi pi-comments" aria-hidden="true" /> Chat</Tab>
        <Tab value="docs"><i class="pi pi-folder" aria-hidden="true" /> Tài liệu</Tab>
        <Tab value="config"><i class="pi pi-cog" aria-hidden="true" /> Cấu hình</Tab>
        <Tab value="connect"><i class="pi pi-facebook" aria-hidden="true" /> Kết nối</Tab>
        <Tab value="stats"><i class="pi pi-chart-bar" aria-hidden="true" /> Thống kê</Tab>
      </TabList>
    </Tabs>
    <!-- Content driven by a keyed transition so switching tabs fades instead of
         popping abruptly (PrimeVue TabPanels swap content with no transition). -->
    <div class="ws-panels">
      <Transition name="fade" mode="out-in">
        <ChatPanel v-if="activeTab === 'chat'" key="chat" :bot="bot" class="panel-chat" />
        <div v-else-if="activeTab === 'docs'" key="docs" class="panel-scroll">
          <DocumentPanel :bot-id="bot.id" :readonly="readonly" />
        </div>
        <div v-else-if="activeTab === 'config'" key="config" class="panel-scroll">
          <BotForm
            :initial="bot"
            submit-label="Lưu thay đổi"
            :submitting="saving"
            :readonly="readonly"
            @submit="save"
          />
          <div v-if="editable && !bot.is_shared" class="danger-zone">
            <span class="muted">Xóa bot sẽ xóa luôn toàn bộ tài liệu của bot.</span>
            <Button
              label="Xóa bot"
              icon="pi pi-trash"
              severity="danger"
              outlined
              @click="confirmDelete = true"
            />
          </div>
        </div>
        <div v-else-if="activeTab === 'connect'" key="connect" class="panel-scroll">
          <IntegrationForm
            :bot-id="bot.id"
            :initial="bot"
            submit-label="Lưu kết nối"
            :submitting="saving"
            :readonly="readonly"
            @submit="save"
          />
        </div>
        <div v-else key="stats" class="panel-scroll">
          <StatsPanel :bot-id="bot.id" />
        </div>
      </Transition>
    </div>

    <Dialog v-model:visible="confirmDelete" modal header="Xóa bot?" :style="{ width: '24rem' }">
      <p>Bạn chắc chắn muốn xóa bot «{{ bot.name }}»? Hành động này không thể hoàn tác.</p>
      <template #footer>
        <Button label="Hủy" text severity="secondary" @click="confirmDelete = false" />
        <Button label="Xóa" icon="pi pi-trash" severity="danger" @click="remove" />
      </template>
    </Dialog>
  </section>
</template>

<style scoped>
.workspace {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
}
.ws-head {
  padding: 16px 22px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}
.ws-title {
  display: flex;
  align-items: center;
  gap: 12px;
}
.ws-avatar {
  width: 44px;
  height: 44px;
  border-radius: 13px;
  background: var(--green);
  color: #fff;
  display: grid;
  place-items: center;
  font-weight: 700;
  font-size: 1.1rem;
}
.ws-name {
  font-size: 1.1rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.ws-name :deep(.p-tag) {
  font-size: 0.72rem;
}
.ws-sub {
  font-size: 0.82rem;
}
.shared-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 10px 22px;
  background: var(--green-soft);
  color: var(--text-muted);
  font-size: 0.84rem;
  border-bottom: 1px solid var(--border);
}
.shared-banner .pi {
  color: var(--green);
}
.ws-tabs {
  flex: 0 0 auto;
}
.ws-panels {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.ws-panels > * {
  flex: 1;
  min-height: 0;
}
.panel-chat {
  padding: 0;
  height: 100%;
}
.panel-scroll {
  overflow-y: auto;
  padding: 20px 22px;
  max-width: 760px;
}
.danger-zone {
  margin-top: 26px;
  padding-top: 18px;
  border-top: 1px dashed var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
</style>
