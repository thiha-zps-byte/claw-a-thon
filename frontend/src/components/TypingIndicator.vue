<script setup lang="ts">
defineProps<{ label?: string }>()
</script>

<template>
  <div class="typing" role="status" :aria-label="label || 'Đang soạn tin nhắn'">
    <span class="dot" />
    <span class="dot" />
    <span class="dot" />
    <span v-if="label" class="typing-label muted">{{ label }}</span>
  </div>
</template>

<style scoped>
.typing {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 10px 14px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--green);
  animation: typing-bounce 1.3s infinite ease-in-out;
}
.dot:nth-child(2) {
  animation-delay: 0.18s;
}
.dot:nth-child(3) {
  animation-delay: 0.36s;
}
.typing-label {
  margin-left: 6px;
  font-size: 0.85rem;
}
</style>
