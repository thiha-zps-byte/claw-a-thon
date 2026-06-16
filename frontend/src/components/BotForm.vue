<script setup lang="ts">
import { reactive, watch } from 'vue'
import InputText from 'primevue/inputtext'
import Textarea from 'primevue/textarea'
import Button from 'primevue/button'
import type { Bot } from '@/api/client'

const props = defineProps<{
  initial?: Partial<Bot>
  submitLabel: string
  submitting?: boolean
  readonly?: boolean
}>()
const emit = defineEmits<{ (e: 'submit', data: Partial<Bot>): void }>()

// Skills are not user-selectable — the backend applies a fixed default. Knowledge
// comes from the bot's documents, so this form only captures persona/voice.
const form = reactive<Partial<Bot>>({
  name: '',
  description: '',
  persona: '',
  player_term: 'bạn',
  self_term: 'mình',
  tone: 'thân thiện, chuyên nghiệp',
})

watch(
  () => props.initial,
  (v) => {
    if (v) Object.assign(form, v)
  },
  { immediate: true },
)

function submit() {
  emit('submit', { ...form })
}
</script>

<template>
  <form class="bot-form" @submit.prevent="submit">
    <label class="field">
      <span class="field-label">Tên game / bot <span class="req">*</span></span>
      <InputText v-model="form.name" :disabled="readonly" placeholder="VD: Tên game của bạn" aria-label="Tên bot" />
    </label>

    <label class="field">
      <span class="field-label">Mô tả vai trò</span>
      <Textarea
        v-model="form.description"
        :disabled="readonly"
        rows="2"
        auto-resize
        placeholder="VD: Hỗ trợ người chơi về tài khoản, nạp thẻ, sự kiện…"
        aria-label="Mô tả vai trò"
      />
    </label>

    <div class="row">
      <label class="field">
        <span class="field-label">Gọi người chơi là</span>
        <InputText v-model="form.player_term" :disabled="readonly" placeholder="bạn" aria-label="Cách gọi người chơi" />
      </label>
      <label class="field">
        <span class="field-label">Bot tự xưng là</span>
        <InputText v-model="form.self_term" :disabled="readonly" placeholder="mình" aria-label="Cách bot tự xưng" />
      </label>
    </div>

    <label class="field">
      <span class="field-label">Tông giọng</span>
      <InputText v-model="form.tone" :disabled="readonly" placeholder="thân thiện, chuyên nghiệp" aria-label="Tông giọng" />
    </label>

    <label class="field">
      <span class="field-label">Tính cách / chỉ dẫn riêng (persona)</span>
      <Textarea
        v-model="form.persona"
        :disabled="readonly"
        rows="3"
        auto-resize
        placeholder="Mô tả thêm cách bot nên cư xử, ưu tiên gì…"
        aria-label="Persona"
      />
    </label>

    <p class="skills-note">
      <i class="pi pi-info-circle" aria-hidden="true" />
      <span>
        Bot trả lời dựa trên <strong>Tài liệu</strong> bạn nạp. Với việc nhạy cảm (mất tiền,
        khóa tài khoản…), bot thu thập thông tin và chuyển bộ phận hỗ trợ chứ không tự xử lý.
      </span>
    </p>

    <div v-if="!readonly" class="actions">
      <Button
        type="submit"
        :label="submitLabel"
        icon="pi pi-check"
        :loading="submitting"
        :disabled="!form.name?.trim()"
      />
    </div>
  </form>
</template>

<style scoped>
.bot-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field-label {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-muted);
}
.req {
  color: #c0392b;
}
.row {
  display: flex;
  gap: 12px;
}
.row .field {
  flex: 1;
}
.actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 4px;
}
:deep(.p-inputtext),
:deep(.p-textarea) {
  width: 100%;
}
.skills-note {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin: 0;
  padding: 10px 12px;
  background: var(--green-soft);
  border-radius: 10px;
  font-size: 0.82rem;
  color: var(--text-muted);
  line-height: 1.5;
}
.skills-note .pi {
  color: var(--green);
  margin-top: 2px;
}
</style>
