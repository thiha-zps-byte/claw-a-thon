import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, type Bot, type DocumentItem } from '@/api/client'

export const useBotsStore = defineStore('bots', () => {
  const bots = ref<Bot[]>([])
  const currentBot = ref<Bot | null>(null)
  const documents = ref<DocumentItem[]>([])
  const loadingBots = ref(false)
  const loadingDocs = ref(false)

  async function loadBots() {
    loadingBots.value = true
    try {
      bots.value = await api.listBots()
    } finally {
      loadingBots.value = false
    }
  }

  async function createBot(data: Partial<Bot>): Promise<Bot> {
    const bot = await api.createBot(data)
    bots.value = [bot, ...bots.value]
    return bot
  }

  async function selectBot(id: string) {
    currentBot.value = await api.getBot(id)
    documents.value = currentBot.value.documents ?? []
  }

  function clearSelection() {
    currentBot.value = null
    documents.value = []
  }

  // Keep the sidebar "N tài liệu" count in sync with the loaded documents so it never
  // shows a stale 0 after the operator adds files in the wizard.
  function syncDocCount(botId: string) {
    const n = documents.value.length
    bots.value = bots.value.map((b) => (b.id === botId ? { ...b, document_count: n } : b))
    if (currentBot.value?.id === botId) currentBot.value.document_count = n
  }

  async function updateBot(id: string, data: Partial<Bot>) {
    const bot = await api.updateBot(id, data)
    currentBot.value = bot
    bots.value = bots.value.map((b) => (b.id === id ? { ...b, ...bot } : b))
  }

  async function removeBot(id: string) {
    await api.deleteBot(id)
    bots.value = bots.value.filter((b) => b.id !== id)
    if (currentBot.value?.id === id) clearSelection()
  }

  async function loadDocuments(botId: string) {
    loadingDocs.value = true
    try {
      documents.value = await api.listDocuments(botId)
      syncDocCount(botId)
    } finally {
      loadingDocs.value = false
    }
  }

  async function uploadDocuments(botId: string, files: File[]) {
    const added = await api.uploadDocuments(botId, files)
    documents.value = [...documents.value, ...added]
    syncDocCount(botId)
    return added
  }

  async function addSampleDocuments(botId: string, sampleIds: string[]) {
    const added = await api.addSampleDocuments(botId, sampleIds)
    documents.value = [...documents.value, ...added]
    syncDocCount(botId)
    return added
  }

  async function removeDocument(botId: string, docId: string) {
    await api.deleteDocument(botId, docId)
    documents.value = documents.value.filter((d) => d.id !== docId)
    syncDocCount(botId)
  }

  return {
    bots,
    currentBot,
    documents,
    loadingBots,
    loadingDocs,
    loadBots,
    createBot,
    selectBot,
    clearSelection,
    updateBot,
    removeBot,
    loadDocuments,
    uploadDocuments,
    addSampleDocuments,
    removeDocument,
  }
})
