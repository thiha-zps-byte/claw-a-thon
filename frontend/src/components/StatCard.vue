<script setup lang="ts">
defineProps<{
  label: string
  value: string | number
  hint?: string
}>()
</script>

<template>
  <div class="stat-card">
    <span class="stat-label">{{ label }}</span>
    <div class="stat-value">{{ value }}</div>
    <div v-if="hint" class="stat-hint">{{ hint }}</div>
  </div>
</template>

<style scoped>
.stat-card {
  flex: 1 1 150px;
  min-width: 140px;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.stat-label {
  color: var(--text-muted);
  font-size: 0.76rem;
  font-weight: 600;
}
.stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text);
  line-height: 1.1;
}
.stat-hint {
  font-size: 0.74rem;
  color: var(--text-muted);
}
</style>
