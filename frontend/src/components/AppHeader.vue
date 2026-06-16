<script setup lang="ts">
import { ref } from 'vue'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Dialog from 'primevue/dialog'
import logo from '@/assets/svg/logo.svg'
import { api } from '@/api/client'
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

// --- admin mode (edits the shared demo bot) ---
const showAdmin = ref(false)
const adminToken = ref('')
const adminError = ref('')
const adminLoading = ref(false)

function openAdmin() {
  adminToken.value = ''
  adminError.value = ''
  showAdmin.value = true
}
async function loginAdmin() {
  adminLoading.value = true
  adminError.value = ''
  try {
    const r = await api.adminLogin(adminToken.value)
    if (r.ok) {
      user.changeUid('admin')
      showAdmin.value = false
      emit('uid-changed')
    } else {
      adminError.value =
        r.reason === 'unset'
          ? 'Chưa cấu hình mật khẩu admin (ADMIN_TOKEN) trên máy chủ.'
          : 'Mật khẩu admin không đúng.'
    }
  } catch {
    adminError.value = 'Không kết nối được máy chủ. Vui lòng thử lại.'
  } finally {
    adminLoading.value = false
  }
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
        <button class="admin-link" type="button" @click="openAdmin">
          <i class="pi pi-shield" aria-hidden="true" /> Chế độ admin
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

    <Dialog v-model:visible="showAdmin" modal header="Chế độ admin" :style="{ width: '24rem' }">
      <p class="muted dialog-hint">
        Nhập mật khẩu admin để chỉnh sửa bot dùng chung. (Người thường vẫn xem & chat thử được bình thường.)
      </p>
      <InputText
        v-model="adminToken"
        type="password"
        class="w-full"
        aria-label="Mật khẩu admin"
        autofocus
        @keyup.enter="loginAdmin"
      />
      <p v-if="adminError" class="admin-error">{{ adminError }}</p>
      <template #footer>
        <Button label="Hủy" severity="secondary" text @click="showAdmin = false" />
        <Button label="Vào admin" icon="pi pi-shield" :loading="adminLoading" @click="loginAdmin" />
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
.admin-error {
  color: #c0392b;
  font-size: 0.82rem;
  margin: 8px 0 0;
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
