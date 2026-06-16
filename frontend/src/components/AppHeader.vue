<script setup lang="ts">
import { ref } from 'vue'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Dialog from 'primevue/dialog'
import logo from '@/assets/svg/logo.svg'
import { useUserStore } from '@/stores/user'

const emit = defineEmits<{ (e: 'uid-changed'): void }>()
const user = useUserStore()
const showUid = ref(false)
const draft = ref(user.uid)

function openUid() {
  draft.value = user.uid
  showUid.value = true
}
function saveUid() {
  user.changeUid(draft.value)
  showUid.value = false
  emit('uid-changed')
}

// --- admin mode: switch identity to "admin" (no password — UID-based access) ---
const showAdmin = ref(false)
function enterAdmin() {
  user.changeUid('admin')
  showAdmin.value = false
  emit('uid-changed')
}
</script>

<template>
  <header class="header">
    <div class="brand">
      <img :src="logo" alt="CS Agent Studio" width="34" height="34" />
      <div>
        <h1 class="title">CS Agent Studio</h1>
        <span class="muted subtitle">Tạo trợ lý chăm sóc khách hàng cho game</span>
      </div>
    </div>
    <div class="uid">
      <span class="muted uid-label">Người dùng</span>
      <div class="uid-actions">
        <button class="uid-chip" type="button" @click="openUid" aria-label="Đổi định danh người dùng (UID)">
          <i class="pi pi-user" aria-hidden="true" />
          <span class="uid-value">{{ user.uid }}</span>
          <i class="pi pi-pencil" aria-hidden="true" />
        </button>
        <button class="admin-link" type="button" @click="showAdmin = true">
          <i class="pi pi-shield" aria-hidden="true" /> Chế độ quản trị
        </button>
      </div>
    </div>

    <Dialog v-model:visible="showUid" modal header="Đổi định danh người dùng" :style="{ width: '24rem' }">
      <p class="muted dialog-hint">
        Định danh dùng để phân biệt người dùng (giai đoạn này chưa cần đăng nhập). Đặt một tên dễ nhớ —
        <strong>bot gắn với định danh này</strong>; đổi trình duyệt hoặc xoá dữ liệu sẽ cần nhập lại đúng
        định danh để thấy lại bot của bạn.
      </p>
      <InputText v-model="draft" class="w-full" aria-label="Định danh" autofocus @keyup.enter="saveUid" />
      <template #footer>
        <Button label="Hủy" severity="secondary" text @click="showUid = false" />
        <Button label="Lưu" icon="pi pi-check" @click="saveUid" />
      </template>
    </Dialog>

    <Dialog v-model:visible="showAdmin" modal header="Chế độ quản trị" :style="{ width: '24rem' }">
      <p class="muted dialog-hint">
        Chuyển sang định danh <strong>quản trị viên</strong> để chỉnh sửa trợ lý dùng chung.
        Người dùng thường vẫn xem đầy đủ và dùng thử bình thường.
      </p>
      <template #footer>
        <Button label="Hủy" severity="secondary" text @click="showAdmin = false" />
        <Button label="Vào chế độ quản trị" icon="pi pi-shield" @click="enterAdmin" />
      </template>
    </Dialog>
  </header>
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 22px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}
.title {
  font-size: 1.15rem;
  font-weight: 700;
}
.subtitle {
  font-size: 0.82rem;
}
.uid {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 3px;
}
.uid-label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.uid-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.admin-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: none;
  border: none;
  padding: 0;
  font: inherit;
  font-size: 0.78rem;
  color: var(--text-muted);
  cursor: pointer;
}
.admin-link:hover {
  color: var(--green);
}
.uid-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: var(--green-soft);
  color: var(--green);
  border: 1px solid #cdf0dc;
  border-radius: 999px;
  padding: 6px 12px;
  font: inherit;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
}
.uid-chip:hover {
  background: #dcf5e7;
}
.w-full {
  width: 100%;
}
.dialog-hint {
  margin-top: 0;
  font-size: 0.85rem;
}
</style>
