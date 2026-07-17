<script setup lang="ts">
import { RefreshCw } from "@lucide/vue";
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { loadAllPages, type PagedResult, type PageQuery } from "../api/types";
import { useOpsStore } from "../stores/ops";
import DataTable, { type Column, type TableFilter } from "./DataTable.vue";
import PageHeader from "./PageHeader.vue";

const props = withDefaults(defineProps<{
  title: string;
  description?: string;
  columns: Column[];
  loader: (query: PageQuery) => Promise<PagedResult<Record<string, unknown>>>;
  emptyText: string;
  filters?: TableFilter[];
  selectable?: boolean;
  defaultSort?: string;
}>(), {
  description: "",
  filters: () => [],
  selectable: true,
  defaultSort: "-created_at",
});

defineEmits<{
  rowClick: [row: Record<string, unknown>];
  selectionChange: [rows: Record<string, unknown>[]];
}>();

const result = ref<PagedResult<Record<string, unknown>>>({
  items: [], page: 1, page_size: 50, total: 0, total_pages: 1, sort: props.defaultSort,
});
const route = useRoute();
const router = useRouter();

function initialValue(key: string) {
  const value = route.query[key];
  return Array.isArray(value) ? value[0] : value;
}

const query = ref<PageQuery>({
  page: Number(initialValue("page") || 1),
  page_size: Number(initialValue("page_size") || 50),
  sort: initialValue("sort") || props.defaultSort,
  q: initialValue("q") || "",
  ...Object.fromEntries(props.filters.map((filter) => [filter.key, initialValue(filter.key) || ""])),
});
const loading = ref(false);
const error = ref("");
const store = useOpsStore();
const tableRef = ref<InstanceType<typeof DataTable> | null>(null);

async function load(next: PageQuery = {}) {
  query.value = { ...query.value, ...next };
  const routeQuery: Record<string, string> = {};
  for (const key of ["page", "page_size", "sort", "q", ...props.filters.map((filter) => filter.key)]) {
    const value = query.value[key];
    if (value !== undefined && String(value).trim()) routeQuery[key] = String(value);
  }
  void router.replace({ query: routeQuery });
  loading.value = true;
  error.value = "";
  try {
    result.value = await props.loader(query.value);
    query.value.page = result.value.page;
    query.value.page_size = result.value.page_size;
    query.value.sort = result.value.sort;
    store.touchRefresh();
  } catch (err) {
    error.value = String((err as Error).message ?? err);
  } finally {
    loading.value = false;
  }
}

function loadAllRows(selectionQuery: PageQuery) {
  return loadAllPages(props.loader, { ...query.value, ...selectionQuery });
}

function clearSelection() {
  tableRef.value?.clearSelection();
}

onMounted(() => load());
defineExpose({ load, clearSelection });
</script>

<template>
  <PageHeader :title="title" :description="description">
    <slot name="headerActions" :reload="load" />
    <button class="icon-btn labeled" title="刷新当前数据" @click="load()">
      <RefreshCw :size="16" :class="{ spin: loading }" />刷新
    </button>
  </PageHeader>
  <slot v-if="$slots.actionCards" name="actionCards" :reload="load" />
  <section v-else-if="$slots.actions" class="operation-bar">
    <slot name="actions" :reload="load" />
  </section>
  <slot name="before" :reload="load" />
  <DataTable
    ref="tableRef"
    :columns="columns"
    :rows="result.items"
    :total="result.total"
    :page="result.page"
    :page-size="result.page_size"
    :sort="result.sort"
    :loading="loading"
    :error="error"
    :empty-text="emptyText"
    :filters="filters"
    :selectable="selectable"
    :all-rows-loader="loadAllRows"
    remote
    @refresh="load()"
    @query-change="load"
    @row-click="(row) => $emit('rowClick', row)"
    @selection-change="(rows) => $emit('selectionChange', rows)"
  >
    <template v-if="$slots.rowActions" #actions="{ row }">
      <slot name="rowActions" :row="row" :reload="load" />
    </template>
  </DataTable>
</template>

<style scoped>
.operation-bar {
  align-items: center;
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  min-height: 52px;
  padding: 8px 10px;
}

.operation-bar :deep(.action-group) { align-items: center; display: flex; flex-wrap: wrap; gap: 8px; }
.operation-bar :deep(.action-hint) { color: var(--text-muted); font-size: 12px; }
.spin { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
