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
    <slot name="actions" :reload="load" />
    <button class="btn primary" @click="load">刷新</button>
  </PageHeader>
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
