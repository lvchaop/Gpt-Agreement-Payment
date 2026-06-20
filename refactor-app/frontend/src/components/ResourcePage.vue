<script setup lang="ts">
import { onMounted, ref } from "vue";

import type { Column, TableFilter } from "./DataTable.vue";
import DataTable from "./DataTable.vue";
import PageHeader from "./PageHeader.vue";
import { useOpsStore } from "../stores/ops";

const props = defineProps<{
  title: string;
  description: string;
  columns: Column[];
  loader: () => Promise<Record<string, unknown>[]>;
  emptyText: string;
  filters?: TableFilter[];
  selectable?: boolean;
}>();

defineEmits<{
  rowClick: [row: Record<string, unknown>];
  selectionChange: [rows: Record<string, unknown>[]];
}>();

const rows = ref<Record<string, unknown>[]>([]);
const loading = ref(false);
const error = ref("");
const store = useOpsStore();

async function load() {
  loading.value = true;
  error.value = "";
  try {
    rows.value = await props.loader();
    store.touchRefresh();
  } catch (err) {
    error.value = String((err as Error).message ?? err);
  } finally {
    loading.value = false;
  }
}

onMounted(load);
defineExpose({ load });
</script>

<template>
  <PageHeader :title="title" :description="description">
    <button class="btn primary" @click="load">刷新</button>
  </PageHeader>
  <slot v-if="$slots.actionCards" name="actionCards" :reload="load" />
  <section v-else-if="$slots.actions" class="panel resource-actions-card">
    <div class="resource-actions-heading">
      <div>
        <h2>功能操作</h2>
        <p>功能按钮和可选入参集中放在这里，不和表格搜索条件混在一起。</p>
      </div>
    </div>
    <div class="resource-actions-body">
      <slot name="actions" :reload="load" />
    </div>
  </section>
  <slot name="before" :reload="load" />
  <DataTable
    :columns="columns"
    :rows="rows"
    :loading="loading"
    :error="error"
    :empty-text="emptyText"
    :filters="filters"
    :selectable="selectable"
    @refresh="load"
    @row-click="(row) => $emit('rowClick', row)"
    @selection-change="(rows) => $emit('selectionChange', rows)"
  >
    <template v-if="$slots.rowActions" #actions="{ row }">
      <slot name="rowActions" :row="row" :reload="load" />
    </template>
  </DataTable>
</template>

<style scoped>
.resource-actions-card {
  margin-bottom: 18px;
  overflow: hidden;
  padding: 0;
}

.resource-actions-heading {
  border-bottom: 1px solid var(--border);
  padding: 14px 16px;
}

.resource-actions-heading h2 {
  font-size: 14px;
  letter-spacing: -0.01em;
  margin: 0;
}

.resource-actions-heading p {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.45;
  margin: 5px 0 0;
}

.resource-actions-body {
  align-items: end;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 14px 16px 16px;
}

.resource-actions-body :deep(.action-group) {
  align-items: end;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.resource-actions-body :deep(.action-spacer) {
  flex: 1 1 auto;
}

@media (max-width: 767px) {
  .resource-actions-body,
  .resource-actions-body :deep(.action-group) {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
