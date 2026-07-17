<script setup lang="ts">
import { computed } from "vue";

import { formatDateTime, formatRelativeTime } from "../utils/time";

const props = defineProps<{ value?: unknown; relative?: boolean }>();
const exact = computed(() => formatDateTime(props.value));
const relativeText = computed(() => formatRelativeTime(props.value));
</script>

<template>
  <time class="date-time" :datetime="String(value ?? '')" :title="`${exact}（Asia/Shanghai）`">
    <span>{{ exact }}</span>
    <small v-if="relative && exact !== '-'">{{ relativeText }}</small>
  </time>
</template>

<style scoped>
.date-time {
  display: inline-grid;
  gap: 2px;
  white-space: nowrap;
}

.date-time small {
  color: var(--text-faint);
  font-size: 11px;
}
</style>
