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
    <span class="metric-accent" />
    <div><span class="label">{{ label }}</span><small v-if="helper">{{ helper }}</small></div>
    <strong>{{ value }}</strong>
  </article>
</template>

<style scoped>
.metric {
  align-items: center;
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  display: grid;
  gap: 10px;
  grid-template-columns: 3px 1fr auto;
  min-height: 76px;
  padding: 12px;
}
.metric-accent { background: currentColor; border-radius: 2px; height: 34px; width: 3px; }
.label { color: var(--text-muted); display: block; font-size: 11px; font-weight: 700; }
strong { color: var(--text-primary); font-size: 24px; font-variant-numeric: tabular-nums; }
small { color: var(--text-faint); display: block; font-size: 10px; margin-top: 3px; }
.success { color: var(--success); }.warning { color: var(--warning); }.danger { color: var(--danger); }
.info { color: var(--accent); }.purple { color: var(--purple); }.neutral { color: var(--text-faint); }
</style>
