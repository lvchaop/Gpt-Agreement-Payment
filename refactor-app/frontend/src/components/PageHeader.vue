<script setup lang="ts">
defineProps<{
  title: string;
  description?: string;
}>();
</script>

<template>
  <div class="page-header">
    <div>
      <h1>{{ title }}</h1>
      <p v-if="description">{{ description }}</p>
    </div>
    <div class="page-actions">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.page-header {
  align-items: flex-start;
  display: flex;
  gap: 18px;
  justify-content: space-between;
  margin-bottom: 12px;
}

h1 {
  font-size: 20px;
  letter-spacing: 0;
  line-height: 1.2;
  margin: 0;
}

p {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.45;
  margin: 5px 0 0;
  max-width: 760px;
}

.page-actions {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

@media (max-width: 767px) {
  .page-header {
    display: grid;
    gap: 12px;
  }

  .page-actions {
    justify-content: flex-start;
    width: 100%;
  }

  .page-actions :deep(.btn) {
    width: 100%;
  }
}
</style>
