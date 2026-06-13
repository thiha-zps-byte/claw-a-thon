<script setup lang="ts">
defineProps<{ image: string; title: string; hint?: string }>()
</script>

<template>
  <div class="empty">
    <img :src="image" :alt="title" class="empty-img" />
    <p class="empty-title">{{ title }}</p>
    <p v-if="hint" class="muted empty-hint">{{ hint }}</p>
    <slot />
  </div>
</template>

<style scoped>
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 40px 20px;
  gap: 6px;
}
.empty-img {
  width: 150px;
  height: auto;
  margin-bottom: 8px;
}
.empty-title {
  font-weight: 600;
  font-size: 1.05rem;
  margin: 0;
}
.empty-hint {
  max-width: 320px;
  margin: 0;
}
</style>
