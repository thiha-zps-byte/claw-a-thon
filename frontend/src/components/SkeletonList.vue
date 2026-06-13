<script setup lang="ts">
withDefaults(defineProps<{ rows?: number; height?: number }>(), { rows: 4, height: 56 })
</script>

<template>
  <div class="skeleton-list" aria-hidden="true">
    <div
      v-for="n in rows"
      :key="n"
      class="skeleton skeleton-row"
      :style="{ height: height + 'px' }"
    />
  </div>
</template>

<style scoped>
.skeleton-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px;
}
.skeleton-row {
  width: 100%;
}
</style>
