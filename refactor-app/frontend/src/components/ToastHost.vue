<script setup lang="ts">
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();
</script>

<template>
  <div class="toasts">
    <article v-for="toast in store.toasts" :key="toast.id" class="toast" :class="toast.tone">
      <strong>{{ toast.title }}</strong>
      <span>{{ toast.message }}</span>
      <button @click="store.dismissToast(toast.id)">×</button>
    </article>
  </div>
</template>

<style scoped>
.toasts {
  bottom: 18px;
  display: grid;
  gap: 10px;
  position: fixed;
  right: 18px;
  z-index: 50;
}

.toast {
  background: rgba(17, 24, 39, 0.96);
  border: 1px solid var(--border);
  border-left: 4px solid var(--accent);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow);
  display: grid;
  gap: 3px;
  min-width: 280px;
  padding: 12px 42px 12px 14px;
  position: relative;
}

.toast.success {
  border-left-color: var(--success);
}

.toast.error {
  border-left-color: var(--danger);
}

.toast.warning {
  border-left-color: var(--warning);
}

strong {
  font-size: 13px;
}

span {
  color: var(--text-muted);
  font-size: 12px;
}

button {
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 20px;
  position: absolute;
  right: 10px;
  top: 8px;
}

@media (max-width: 767px) {
  .toasts {
    bottom: 12px;
    left: 12px;
    right: 12px;
  }

  .toast {
    min-width: 0;
    width: 100%;
  }
}
</style>
