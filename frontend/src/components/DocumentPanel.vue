<script setup lang="ts">
import { ref } from 'vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import Checkbox from 'primevue/checkbox'
import { useToast } from 'primevue/usetoast'
import EmptyState from './EmptyState.vue'
import SkeletonList from './SkeletonList.vue'
import emptyDocs from '@/assets/svg/empty-docs.svg'
import { useBotsStore } from '@/stores/bots'
import { api, ApiException, fetchWithTimeout, getUid, type Sample } from '@/api/client'
import { renderMarkdown } from '@/utils/markdown'

type PreviewKind = 'image' | 'pdf' | 'markdown' | 'csv' | 'text' | 'docx'

const props = defineProps<{ botId: string; readonly?: boolean }>()
const store = useBotsStore()
const toast = useToast()
const dragging = ref(false)
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

// --- sample picker ---
const showPicker = ref(false)
const samples = ref<Sample[]>([])
const loadingSamples = ref(false)
const selectedIds = ref<string[]>([])
const addingSamples = ref(false)

// --- content preview (shared by samples + uploaded docs) — render real format ---
const showPreview = ref(false)
const previewTitle = ref('')
const previewKind = ref<PreviewKind>('text')
const previewUrl = ref('') // raw url for image/pdf/download
const previewText = ref('') // text for md/csv/txt/docx-fallback
const previewHtml = ref('') // rendered markdown
const previewRows = ref<string[][]>([]) // parsed csv
const previewNote = ref('') // failed-ingest note, if any
const previewLoading = ref(false)

function kindOf(filename: string, mime = ''): PreviewKind {
  const n = filename.toLowerCase()
  if (/\.(png|jpe?g|webp|gif)$/.test(n) || mime.startsWith('image/')) return 'image'
  if (n.endsWith('.pdf') || mime === 'application/pdf') return 'pdf'
  if (/\.(md|markdown)$/.test(n)) return 'markdown'
  if (n.endsWith('.csv')) return 'csv'
  if (n.endsWith('.docx')) return 'docx'
  return 'text'
}

function parseCsv(text: string): string[][] {
  return text
    .replace(/\r\n/g, '\n')
    .split('\n')
    .filter((l) => l.trim())
    .slice(0, 200)
    .map((l) => l.split(','))
}

async function fetchText(url: string): Promise<string> {
  const resp = await fetchWithTimeout(url, { headers: { 'X-UID': getUid() } })
  if (!resp.ok) throw new Error('raw fetch failed')
  return resp.text()
}

function resetPreview(title: string, kind: PreviewKind, url: string) {
  previewTitle.value = title
  previewKind.value = kind
  previewUrl.value = url
  previewText.value = ''
  previewHtml.value = ''
  previewRows.value = []
  previewNote.value = ''
  showPreview.value = true
}

async function loadTextInto(url: string, kind: PreviewKind) {
  previewLoading.value = true
  try {
    const text = await fetchText(url)
    if (kind === 'markdown') previewHtml.value = renderMarkdown(text)
    else if (kind === 'csv') previewRows.value = parseCsv(text)
    else previewText.value = text
  } catch {
    previewText.value = '(Không tải được nội dung)'
  } finally {
    previewLoading.value = false
  }
}

function pick() {
  fileInput.value?.click()
}

async function handleFiles(fileList: FileList | null) {
  if (!fileList || fileList.length === 0) return
  uploading.value = true
  try {
    const added = await store.uploadDocuments(props.botId, Array.from(fileList))
    reportIngest(added)
  } catch (e) {
    const msg = e instanceof ApiException ? e.message : 'Tải tài liệu thất bại.'
    toast.add({ severity: 'error', summary: 'Lỗi', detail: msg, life: 5000 })
  } finally {
    uploading.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

function reportIngest(added: { filename: string; status: string; note: string }[]) {
  const failed = added.filter((d) => d.status !== 'ready')
  if (failed.length) {
    toast.add({
      severity: 'warn',
      summary: 'Một số file chưa đọc được',
      detail: failed.map((f) => `${f.filename}: ${f.note}`).join('; '),
      life: 6000,
    })
  } else {
    toast.add({ severity: 'success', summary: 'Đã tải tài liệu', life: 2500 })
  }
}

function onDrop(e: DragEvent) {
  dragging.value = false
  handleFiles(e.dataTransfer?.files ?? null)
}

async function remove(docId: string) {
  try {
    await store.removeDocument(props.botId, docId)
  } catch {
    toast.add({ severity: 'error', summary: 'Không xóa được tài liệu', life: 4000 })
  }
}

async function openPicker() {
  showPicker.value = true
  selectedIds.value = []
  if (samples.value.length === 0) {
    loadingSamples.value = true
    try {
      samples.value = await api.listSamples()
    } catch {
      toast.add({ severity: 'error', summary: 'Không tải được danh sách tài liệu mẫu', life: 4000 })
    } finally {
      loadingSamples.value = false
    }
  }
}

async function addSelected() {
  if (selectedIds.value.length === 0) return
  addingSamples.value = true
  try {
    const added = await store.addSampleDocuments(props.botId, selectedIds.value)
    showPicker.value = false
    reportIngest(added)
  } catch (e) {
    const msg = e instanceof ApiException ? e.message : 'Thêm tài liệu mẫu thất bại.'
    toast.add({ severity: 'error', summary: 'Lỗi', detail: msg, life: 5000 })
  } finally {
    addingSamples.value = false
  }
}

async function previewSample(s: Sample) {
  const kind = kindOf(s.filename)
  resetPreview(s.title || s.filename, kind, api.sampleRawUrl(s.id))
  if (kind === 'markdown' || kind === 'csv' || kind === 'text') {
    await loadTextInto(previewUrl.value, kind)
  }
}

async function previewDoc(doc: { id: string; filename: string; mime: string; status: string; note: string }) {
  const kind = kindOf(doc.filename, doc.mime)
  resetPreview(doc.filename, kind, api.documentRawUrl(props.botId, doc.id))
  if (kind === 'docx') {
    // Browsers can't render .docx — show the extracted text + offer download.
    previewLoading.value = true
    try {
      const data = await api.getDocument(props.botId, doc.id)
      previewText.value = data.extracted_text || (doc.note ? doc.note : '(Không có nội dung trích xuất.)')
    } catch {
      previewText.value = '(Không tải được nội dung)'
    } finally {
      previewLoading.value = false
    }
  } else if (kind === 'markdown' || kind === 'csv' || kind === 'text') {
    await loadTextInto(previewUrl.value, kind)
  }
  // image / pdf → rendered directly from previewUrl in the template.
}

function iconFor(name: string): string {
  if (/\.(png|jpe?g|webp|gif)$/i.test(name)) return 'pi pi-image'
  if (/\.pdf$/i.test(name)) return 'pi pi-file-pdf'
  if (/\.(docx?|md|txt)$/i.test(name)) return 'pi pi-file'
  if (/\.csv$/i.test(name)) return 'pi pi-table'
  return 'pi pi-file'
}
</script>

<template>
  <div class="docs">
    <div
      v-if="!readonly"
      class="dropzone"
      :class="{ dragging }"
      role="button"
      tabindex="0"
      aria-label="Tải tài liệu lên"
      @click="pick"
      @keyup.enter="pick"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <i class="pi pi-cloud-upload drop-icon" aria-hidden="true" />
      <p class="drop-title">Kéo thả hoặc bấm để tải tài liệu</p>
      <p class="muted drop-hint">
        Hỗ trợ .md .txt .pdf .docx .csv và ảnh (.png .jpg) · chọn nhiều file cùng lúc
      </p>
      <input
        ref="fileInput"
        type="file"
        multiple
        hidden
        accept=".md,.txt,.pdf,.docx,.csv,.png,.jpg,.jpeg,.webp,.gif"
        @change="handleFiles(($event.target as HTMLInputElement).files)"
      />
    </div>

    <div v-if="!readonly" class="sample-row">
      <Button
        label="Dùng tài liệu mẫu"
        icon="pi pi-sparkles"
        severity="secondary"
        outlined
        size="small"
        @click="openPicker"
      />
      <span class="muted sample-hint">Chưa có tài liệu? Thử ngay bộ tài liệu mẫu để xem bot hoạt động.</span>
    </div>

    <div v-if="uploading" class="uploading muted">
      <i class="pi pi-spin pi-spinner" aria-hidden="true" /> Đang xử lý tài liệu…
    </div>

    <SkeletonList v-if="store.loadingDocs" :rows="3" :height="48" />

    <EmptyState
      v-else-if="store.documents.length === 0"
      :image="emptyDocs"
      title="Chưa có tài liệu nào"
      hint="Tải tài liệu để bot trả lời người chơi dựa trên nội dung đó."
    />

    <ul v-else class="doc-list">
      <li v-for="d in store.documents" :key="d.id" class="doc-item card">
        <i :class="iconFor(d.filename)" class="doc-icon" aria-hidden="true" />
        <div class="doc-meta">
          <span class="doc-name">{{ d.filename }}</span>
          <span class="muted doc-sub">
            <template v-if="d.status === 'ready'">{{ d.char_count }} ký tự</template>
            <template v-else><i class="pi pi-exclamation-triangle" aria-hidden="true" /> {{ d.note }}</template>
          </span>
        </div>
        <span v-if="d.status !== 'ready'" class="badge-failed">lỗi</span>
        <Button
          icon="pi pi-eye"
          text
          rounded
          aria-label="Xem nội dung"
          title="Xem nhanh nội dung"
          @click="previewDoc(d)"
        />
        <Button
          v-if="!readonly"
          icon="pi pi-trash"
          severity="danger"
          text
          rounded
          aria-label="Xóa tài liệu"
          @click="remove(d.id)"
        />
      </li>
    </ul>

    <!-- Sample picker -->
    <Dialog
      v-model:visible="showPicker"
      modal
      header="Tài liệu mẫu"
      :style="{ width: '34rem', maxWidth: '94vw' }"
    >
      <p class="muted picker-intro">
        Chọn một hoặc nhiều file mẫu để nạp vào bot. Bấm <i class="pi pi-eye" /> để xem nhanh nội dung trước.
      </p>
      <SkeletonList v-if="loadingSamples" :rows="4" :height="40" />
      <ul v-else class="sample-list">
        <li v-for="s in samples" :key="s.id" class="sample-item">
          <Checkbox v-model="selectedIds" :value="s.id" :input-id="`s-${s.id}`" />
          <label :for="`s-${s.id}`" class="sample-label">
            <span class="sample-title">{{ s.title }}</span>
            <span class="muted sample-sub">{{ s.filename }} · {{ s.char_count }} ký tự</span>
          </label>
          <Button
            icon="pi pi-eye"
            text
            rounded
            size="small"
            aria-label="Xem nội dung mẫu"
            @click="previewSample(s)"
          />
        </li>
      </ul>
      <template #footer>
        <Button label="Đóng" text severity="secondary" @click="showPicker = false" />
        <Button
          :label="`Thêm ${selectedIds.length} file đã chọn`"
          icon="pi pi-check"
          :disabled="selectedIds.length === 0"
          :loading="addingSamples"
          @click="addSelected"
        />
      </template>
    </Dialog>

    <!-- Content preview — render the real file format -->
    <Dialog
      v-model:visible="showPreview"
      modal
      :header="previewTitle"
      :style="{ width: '52rem', maxWidth: '94vw' }"
    >
      <div class="preview-toolbar">
        <span class="preview-kind">{{ previewKind }}</span>
        <a :href="previewUrl" target="_blank" rel="noopener" download class="preview-download">
          <i class="pi pi-download" aria-hidden="true" /> Tải về
        </a>
      </div>

      <div v-if="previewLoading" class="muted preview-loading">
        <i class="pi pi-spin pi-spinner" aria-hidden="true" /> Đang tải nội dung…
      </div>

      <template v-else>
        <img v-if="previewKind === 'image'" :src="previewUrl" :alt="previewTitle" class="preview-img" />
        <iframe
          v-else-if="previewKind === 'pdf'"
          :src="previewUrl"
          class="preview-pdf"
          :title="previewTitle"
        />
        <!-- eslint-disable-next-line vue/no-v-html (escaped + sanitized in renderMarkdown) -->
        <div v-else-if="previewKind === 'markdown'" class="preview-md" v-html="previewHtml" />
        <div v-else-if="previewKind === 'csv'" class="preview-csv-wrap">
          <table class="preview-csv">
            <tbody>
              <tr v-for="(row, ri) in previewRows" :key="ri">
                <td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <template v-else-if="previewKind === 'docx'">
          <p class="muted preview-docx-note">
            File .docx không xem trực tiếp được — dưới đây là nội dung trích xuất; bấm “Tải về” để mở bằng Word.
          </p>
          <pre class="preview-body">{{ previewText }}</pre>
        </template>
        <pre v-else class="preview-body">{{ previewText }}</pre>
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
.docs {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.dropzone {
  border: 2px dashed #b9ddc8;
  border-radius: var(--radius);
  background: var(--green-soft);
  padding: 26px;
  text-align: center;
  cursor: pointer;
  transition: all 0.15s;
}
.dropzone.dragging,
.dropzone:hover {
  border-color: var(--green);
  background: #dcf5e7;
}
.drop-icon {
  font-size: 1.8rem;
  color: var(--green);
}
.drop-title {
  font-weight: 600;
  margin: 8px 0 2px;
}
.drop-hint {
  font-size: 0.82rem;
  margin: 0;
}
.sample-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.sample-hint {
  font-size: 0.8rem;
}
.uploading {
  font-size: 0.9rem;
}
.doc-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.doc-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
}
.doc-icon {
  color: var(--green);
  font-size: 1.2rem;
}
.doc-meta {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}
.doc-name {
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.doc-sub {
  font-size: 0.8rem;
}
.badge-failed {
  background: #fdecea;
  color: #c0392b;
  font-size: 0.72rem;
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 600;
}
.picker-intro {
  font-size: 0.85rem;
  margin: 0 0 12px;
}
.sample-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sample-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
}
.sample-label {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  cursor: pointer;
}
.sample-title {
  font-weight: 600;
}
.sample-sub {
  font-size: 0.78rem;
}
.preview-loading {
  padding: 20px 0;
  text-align: center;
}
.preview-body {
  margin: 0;
  max-height: 60vh;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 0.88rem;
  line-height: 1.55;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
}
.preview-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.preview-kind {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 700;
  color: var(--green);
  background: var(--green-soft);
  padding: 2px 8px;
  border-radius: 999px;
}
.preview-download {
  font-size: 0.82rem;
  color: var(--green);
  text-decoration: none;
  font-weight: 600;
}
.preview-img {
  display: block;
  max-width: 100%;
  max-height: 64vh;
  margin: 0 auto;
  border-radius: 10px;
  background: #0001;
}
.preview-pdf {
  width: 100%;
  height: 64vh;
  border: 1px solid var(--border);
  border-radius: 10px;
}
.preview-md {
  max-height: 62vh;
  overflow: auto;
  line-height: 1.6;
  font-size: 0.92rem;
  padding: 4px 2px;
}
.preview-md :deep(h1),
.preview-md :deep(h2),
.preview-md :deep(h3) {
  margin: 0.8em 0 0.3em;
  line-height: 1.3;
}
.preview-md :deep(ul),
.preview-md :deep(ol) {
  padding-left: 1.4em;
}
.preview-md :deep(blockquote) {
  margin: 0.5em 0;
  padding-left: 12px;
  border-left: 3px solid var(--border);
  color: var(--text-muted);
}
.preview-md :deep(code) {
  background: var(--bg);
  padding: 1px 5px;
  border-radius: 5px;
  font-size: 0.9em;
}
.preview-md :deep(a) {
  color: var(--green);
}
.preview-csv-wrap {
  max-height: 62vh;
  overflow: auto;
}
.preview-csv {
  border-collapse: collapse;
  width: 100%;
  font-size: 0.86rem;
}
.preview-csv td {
  border: 1px solid var(--border);
  padding: 5px 9px;
}
.preview-csv tr:first-child td {
  font-weight: 700;
  background: var(--green-soft);
}
.preview-docx-note {
  font-size: 0.82rem;
  margin: 0 0 8px;
}
</style>
