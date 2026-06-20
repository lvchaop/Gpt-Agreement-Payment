<script setup lang="ts">
import { computed, ref } from "vue";

const props = defineProps<{
  value: unknown;
  title?: string;
  collapsed?: boolean;
}>();

const open = ref(!props.collapsed);
const text = computed(() => JSON.stringify(props.value ?? {}, null, 2));

async function copy() {
  await navigator.clipboard.writeText(text.value);
}
</script>

<template>
  <section class="json-block">
    <header>
      <button class="toggle" @click="open = !open">{{ open ? "收起" : "展开" }}</button>
      <strong>{{ title ?? "JSON" }}</strong>
      <button class="copy" @click="copy">复制</button>
    </header>
    <pre v-if="open">{{ text }}</pre>
  </section>
</template>

<style scoped>
.json-block {
  background: #090f1d;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
}

header {
  align-items: center;
  background: rgba(23, 32, 51, 0.72);
  border-bottom: 1px solid var(--border);
  display: flex;
  gap: 10px;
  min-height: 38px;
  padding: 0 10px;
}

strong {
  flex: 1;
  font-size: 13px;
}

button {
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 12px;
  font-weight: 800;
}

pre {
  color: #cbd5e1;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
  line-height: 1.55;
  margin: 0;
  max-height: 360px;
  overflow: auto;
  padding: 14px;
}
</style>
