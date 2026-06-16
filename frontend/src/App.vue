<script setup lang="ts">
import { onMounted } from 'vue'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'
import AppHeader from '@/components/AppHeader.vue'
import BotSidebar from '@/components/BotSidebar.vue'
import BotWorkspace from '@/components/BotWorkspace.vue'
import EmptyState from '@/components/EmptyState.vue'
import emptyBots from '@/assets/svg/empty-bots.svg'
import { useBotsStore } from '@/stores/bots'

const store = useBotsStore()
const toast = useToast()

async function bootstrap() {
  store.clearSelection()
  try {
    await store.loadBots()
    // Land the user in a working bot instead of a blank screen. List order is
    // "own bots (newest first) → shared", so returning users get their latest bot
    // and newcomers get the shared demo.
    if (!store.currentBot && store.bots.length) {
      await store.selectBot(store.bots[0].id)
    }
  } catch {
    toast.add({ severity: 'error', summary: 'Không tải được danh sách bot', life: 4000 })
  }
}

function reloadForUser() {
  bootstrap()
}

onMounted(bootstrap)
</script>

<template>
  <div class="app">
    <AppHeader @uid-changed="reloadForUser" />
    <main class="body">
      <BotSidebar />
      <BotWorkspace v-if="store.currentBot" :bot="store.currentBot" />
      <div v-else class="placeholder">
        <EmptyState
          :image="emptyBots"
          title="Chọn hoặc tạo một bot để bắt đầu"
          hint="Mỗi bot là một trợ lý CS cho một game, có tài liệu và cách xưng hô riêng."
        />
      </div>
    </main>
  </div>
  <Toast position="top-right" />
</template>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.body {
  flex: 1;
  display: flex;
  min-height: 0;
}
.placeholder {
  flex: 1;
  display: grid;
  place-items: center;
}
</style>
