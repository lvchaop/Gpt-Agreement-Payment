<script setup lang="ts">
defineProps<{
  label: string;
  value: string | number;
  helper?: string;
  tone?: "success" | "warning" | "danger" | "info" | "purple" | "neutral";
}>();
</script>

<template>
  <article class="metric" :class="tone ?? 'neutral'">
    <span class="label">{{ label }}</span>
    <strong>{{ value }}</strong>
    <small>{{ helper }}</small>
  </article>
</template>

<style scoped>
.metric {
  background: linear-gradient(180deg, rgba(23, 32, 51, 0.94), rgba(17, 24, 39, 0.94));
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  min-height: 116px;
  padding: 16px;
  position: relative;
  overflow: hidden;
}

.metric::after {
  background: currentColor;
  border-radius: 999px;
  content: "";
  height: 56px;
  opacity: 0.13;
  position: absolute;
  right: -16px;
  top: -18px;
  width: 56px;
}

.label {
  color: var(--text-muted);
  display: block;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

strong {
  display: block;
  font-size: 30px;
  letter-spacing: -0.04em;
  line-height: 1;
  margin-top: 16px;
}

small {
  color: var(--text-muted);
  display: block;
  font-size: 12px;
  margin-top: 9px;
}

.success {
  color: var(--success);
}

.warning {
  color: var(--warning);
}

.danger {
  color: var(--danger);
}

.info {
  color: var(--accent);
}

.purple {
  color: var(--purple);
}

.neutral {
  color: #94a3b8;
}
</style>
