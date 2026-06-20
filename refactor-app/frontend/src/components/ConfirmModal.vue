<script setup lang="ts">
defineProps<{
  open: boolean;
  title: string;
  summary?: Record<string, unknown>;
  confirmText?: string;
  danger?: boolean;
}>();

const emit = defineEmits<{
  close: [];
  confirm: [];
}>();
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="overlay" @click.self="emit('close')">
      <section class="modal panel">
        <h2>{{ title }}</h2>
        <dl v-if="summary">
          <template v-for="(value, key) in summary" :key="key">
            <dt>{{ key }}</dt>
            <dd>{{ value }}</dd>
          </template>
        </dl>
        <div class="actions">
          <button class="btn" @click="emit('close')">取消</button>
          <button class="btn" :class="{ danger, primary: !danger }" @click="emit('confirm')">
            {{ confirmText ?? "Confirm" }}
          </button>
        </div>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.overlay {
  align-items: center;
  background: rgba(2, 6, 23, 0.68);
  display: flex;
  inset: 0;
  justify-content: center;
  padding: 24px;
  position: fixed;
  z-index: 40;
}

.modal {
  max-width: 520px;
  padding: 20px;
  width: 100%;
}

h2 {
  font-size: 20px;
  margin: 0 0 16px;
}

dl {
  background: rgba(15, 23, 42, 0.72);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  display: grid;
  grid-template-columns: 150px 1fr;
  margin: 0 0 18px;
  overflow: hidden;
}

dt,
dd {
  border-bottom: 1px solid var(--border);
  margin: 0;
  padding: 10px;
}

dt {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 900;
}

dd {
  overflow-wrap: anywhere;
}

.actions {
  justify-content: flex-end;
}
</style>
