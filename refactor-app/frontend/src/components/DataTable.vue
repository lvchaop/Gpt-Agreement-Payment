<script setup lang="ts">
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Copy,
  RefreshCw,
  Search,
  X,
} from "@lucide/vue";
import { computed, ref, watch } from "vue";

import type { PageQuery } from "../api/types";
import { formatDuration } from "../utils/time";
import DateTimeText from "./DateTimeText.vue";
import EntitySelect from "./EntitySelect.vue";
import StatusBadge from "./StatusBadge.vue";

export type Column = {
  key: string;
  label: string;
  badge?: boolean;
  mono?: boolean;
  summary?: boolean | number;
  sortable?: boolean;
  copyable?: boolean;
  type?: "text" | "datetime" | "duration" | "boolean" | "number";
  relativeTime?: boolean;
};

export type FilterOption = {
  label: string;
  value: string;
  description?: string;
  status?: string;
};
export type TableFilter = {
  key: string;
  label: string;
  options?: FilterOption[];
  loader?: (query: string, values: Readonly<Record<string, string>>) => Promise<FilterOption[]>;
  placeholder?: string;
  dependsOn?: string;
};

const props = withDefaults(defineProps<{
  columns: Column[];
  rows: Record<string, unknown>[];
  loading?: boolean;
  error?: string;
  emptyText?: string;
  filters?: TableFilter[];
  selectable?: boolean;
  remote?: boolean;
  total?: number;
  page?: number;
  pageSize?: number;
  sort?: string;
  allRowsLoader?: (query: PageQuery) => Promise<Record<string, unknown>[]>;
}>(), {
  loading: false,
  error: "",
  emptyText: "暂无数据。",
  filters: () => [],
  selectable: true,
  remote: false,
  total: 0,
  page: 1,
  pageSize: 50,
  sort: "",
});

const emit = defineEmits<{
  rowClick: [row: Record<string, unknown>];
  refresh: [];
  selectionChange: [rows: Record<string, unknown>[]];
  queryChange: [query: PageQuery];
}>();

const search = ref("");
const internalPage = ref(props.page);
const internalPageSize = ref(props.pageSize);
const internalSort = ref(props.sort);
const filterValues = ref<Record<string, string>>({});
const selectedRowsById = ref(new Map<string, Record<string, unknown>>());
const selectingAllRows = ref(false);
const selectionError = ref("");
let selectionRequestId = 0;

function rowKey(row: Record<string, unknown>, index = 0) {
  return String(row.id ?? row.space_credential_id ?? `${row.email ?? "row"}-${index}`);
}

const localFilteredRows = computed(() => {
  if (props.remote) return props.rows;
  const needle = search.value.trim().toLowerCase();
  return props.rows.filter((row) => {
    const matchesSearch = !needle || JSON.stringify(row).toLowerCase().includes(needle);
    const matchesFilters = Object.entries(filterValues.value).every(([key, value]) =>
      !value || String(row[key] ?? "") === value,
    );
    return matchesSearch && matchesFilters;
  });
});

const effectiveTotal = computed(() => props.remote ? props.total : localFilteredRows.value.length);
const totalPages = computed(() => Math.max(1, Math.ceil(effectiveTotal.value / internalPageSize.value)));
const visibleRows = computed(() => {
  if (props.remote) return props.rows;
  const start = (internalPage.value - 1) * internalPageSize.value;
  return localFilteredRows.value.slice(start, start + internalPageSize.value);
});
const rangeStart = computed(() => effectiveTotal.value === 0 ? 0 : (internalPage.value - 1) * internalPageSize.value + 1);
const rangeEnd = computed(() => Math.min(internalPage.value * internalPageSize.value, effectiveTotal.value));
const pageRowKeys = computed(() => visibleRows.value.map((row, index) => rowKey(row, index)));
const allPageSelected = computed(() =>
  pageRowKeys.value.length > 0 && pageRowKeys.value.every((key) => selectedRowsById.value.has(key)),
);
const somePageSelected = computed(() =>
  !allPageSelected.value && pageRowKeys.value.some((key) => selectedRowsById.value.has(key)),
);
const selectedRows = computed(() => Array.from(selectedRowsById.value.values()));
const canSelectAllRows = computed(() => !props.remote || Boolean(props.allRowsLoader));
const allRowsSelected = computed(() =>
  effectiveTotal.value > 0 && selectedRowsById.value.size === effectiveTotal.value,
);
const hasActiveFilters = computed(() =>
  Boolean(search.value.trim()) || Object.values(filterValues.value).some(Boolean),
);

watch(() => props.page, (value) => { internalPage.value = value; });
watch(() => props.pageSize, (value) => { internalPageSize.value = value; });
watch(() => props.sort, (value) => { internalSort.value = value; });
watch(search, () => { if (!props.remote) clearSelection(); });
watch(selectedRows, (rows) => emit("selectionChange", rows));
watch(totalPages, (value) => {
  if (!props.remote && internalPage.value > value) internalPage.value = value;
});

function emitQuery(overrides: PageQuery = {}) {
  emit("queryChange", currentQuery(overrides));
}

function currentQuery(overrides: PageQuery = {}): PageQuery {
  return {
    page: internalPage.value,
    page_size: internalPageSize.value,
    sort: internalSort.value,
    q: search.value.trim(),
    ...filterValues.value,
    ...overrides,
  };
}

function applyFilters() {
  if (props.remote) clearSelection();
  internalPage.value = 1;
  if (props.remote) emitQuery({ page: 1 });
}

function updateFilterValue(filter: TableFilter, value: string) {
  clearSelection();
  filterValues.value[filter.key] = value;
  for (const dependent of props.filters) {
    if (dependent.dependsOn === filter.key) filterValues.value[dependent.key] = "";
  }
}

function loadFilterOptions(filter: TableFilter, query: string) {
  if (!filter.loader) return Promise.resolve([]);
  return filter.loader(query, filterValues.value);
}

function resetFilters() {
  clearSelection();
  search.value = "";
  filterValues.value = {};
  internalPage.value = 1;
  if (props.remote) emitQuery({ page: 1, q: "" });
}

function setPage(page: number) {
  internalPage.value = Math.min(totalPages.value, Math.max(1, page));
  if (props.remote) emitQuery({ page: internalPage.value });
}

function setPageSize() {
  internalPage.value = 1;
  if (props.remote) emitQuery({ page: 1, page_size: internalPageSize.value });
}

function setSort(column: Column) {
  if (!column.sortable) return;
  const current = internalSort.value;
  internalSort.value = current === column.key ? `-${column.key}` : column.key;
  internalPage.value = 1;
  if (props.remote) emitQuery({ page: 1, sort: internalSort.value });
}

function sortIcon(column: Column) {
  if (internalSort.value === column.key) return ArrowUp;
  if (internalSort.value === `-${column.key}`) return ArrowDown;
  return ArrowUpDown;
}

function toggleRow(row: Record<string, unknown>, index: number) {
  selectionError.value = "";
  const next = new Map(selectedRowsById.value);
  const key = rowKey(row, index);
  if (next.has(key)) next.delete(key);
  else next.set(key, row);
  selectedRowsById.value = next;
}

function toggleCurrentPage() {
  selectionError.value = "";
  const next = new Map(selectedRowsById.value);
  visibleRows.value.forEach((row, index) => {
    const key = rowKey(row, index);
    if (allPageSelected.value) next.delete(key);
    else next.set(key, row);
  });
  selectedRowsById.value = next;
}

function clearSelection() {
  selectionRequestId += 1;
  selectingAllRows.value = false;
  selectionError.value = "";
  selectedRowsById.value = new Map();
}

async function selectAllRows() {
  if (!canSelectAllRows.value || selectingAllRows.value) return;
  const requestId = ++selectionRequestId;
  selectingAllRows.value = true;
  selectionError.value = "";
  try {
    const rows = props.remote
      ? await props.allRowsLoader!(currentQuery({ page: 1 }))
      : localFilteredRows.value;
    if (requestId !== selectionRequestId) return;
    const next = new Map<string, Record<string, unknown>>();
    rows.forEach((row, index) => next.set(rowKey(row, index), row));
    selectedRowsById.value = next;
  } catch (err) {
    if (requestId === selectionRequestId) {
      selectionError.value = String((err as Error).message ?? err);
    }
  } finally {
    if (requestId === selectionRequestId) selectingAllRows.value = false;
  }
}

function displayValue(column: Column, value: unknown) {
  if (column.type === "duration") return formatDuration(value);
  if (column.type === "boolean") return value ? "是" : "否";
  const text = String(value ?? "") || "-";
  if (!column.summary || text === "-") return text;
  const limit = typeof column.summary === "number" ? column.summary : 28;
  if (text.length <= limit) return text;
  const head = Math.max(6, Math.floor((limit - 1) * 0.58));
  return `${text.slice(0, head)}…${text.slice(-(limit - head - 1))}`;
}

function isDateColumn(column: Column) {
  return column.type === "datetime" || (!column.type && /(_at|_time)$/.test(column.key));
}

async function copy(value: unknown) {
  await navigator.clipboard.writeText(String(value ?? ""));
}

defineExpose({ clearSelection });
</script>

<template>
  <section class="table-shell">
    <form class="table-toolbar" @submit.prevent="applyFilters">
      <label class="search-control">
        <Search :size="16" aria-hidden="true" />
        <input v-model="search" placeholder="搜索 ID、邮箱、名称或错误信息" aria-label="关键词" />
      </label>
      <div v-for="filter in filters" :key="filter.key" class="filter-control">
        <span>{{ filter.label }}</span>
        <EntitySelect
          v-if="filter.loader"
          :model-value="filterValues[filter.key] || ''"
          :loader="(query) => loadFilterOptions(filter, query)"
          :placeholder="filter.placeholder || `搜索${filter.label}`"
          @update:model-value="(value) => updateFilterValue(filter, String(value))"
        />
        <select
          v-else
          :value="filterValues[filter.key] || ''"
          @change="updateFilterValue(filter, ($event.target as HTMLSelectElement).value)"
        >
          <option value="">全部</option>
          <option v-for="option in filter.options || []" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>
      <button class="btn primary compact-btn" type="submit">
        <Search :size="15" />查询
      </button>
      <button v-if="hasActiveFilters" class="icon-btn" type="button" title="清空筛选" @click="resetFilters">
        <X :size="16" />
      </button>
      <span class="toolbar-spacer" />
      <label class="page-size-control">
        <span>每页</span>
        <select v-model.number="internalPageSize" @change="setPageSize">
          <option :value="20">20</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
          <option :value="200">200</option>
        </select>
      </label>
      <button class="icon-btn" type="button" title="刷新表格" @click="emit('refresh')">
        <RefreshCw :size="16" :class="{ spin: loading }" />
      </button>
    </form>

    <div v-if="error" class="table-state error-state">
      <strong>加载失败</strong>
      <span>{{ error }}</span>
      <button class="btn" @click="emit('refresh')">重试</button>
    </div>
    <div v-else class="table-viewport" :class="{ loading }">
      <table>
        <thead>
          <tr>
            <th v-if="selectable" class="select-column">
              <input
                type="checkbox"
                :checked="allPageSelected"
                :indeterminate="somePageSelected"
                :disabled="!visibleRows.length"
                :aria-checked="somePageSelected ? 'mixed' : allPageSelected"
                aria-label="全选当前页"
                title="全选当前页"
                @change="toggleCurrentPage"
              />
            </th>
            <th v-for="column in columns" :key="column.key">
              <button
                v-if="column.sortable"
                class="sort-button"
                :title="`按${column.label}排序`"
                @click="setSort(column)"
              >
                {{ column.label }}
                <component :is="sortIcon(column)" :size="13" />
              </button>
              <span v-else>{{ column.label }}</span>
            </th>
            <th v-if="$slots.actions" class="actions-column">操作</th>
          </tr>
        </thead>
        <tbody v-if="visibleRows.length">
          <tr v-for="(row, index) in visibleRows" :key="rowKey(row, index)" @click="emit('rowClick', row)">
            <td v-if="selectable" class="select-column" @click.stop>
              <input
                type="checkbox"
                :checked="selectedRowsById.has(rowKey(row, index))"
                :aria-label="`选择 ${row.email ?? row.id ?? index}`"
                @change="toggleRow(row, index)"
              />
            </td>
            <td v-for="column in columns" :key="column.key" :class="{ mono: column.mono }">
              <StatusBadge v-if="column.badge" :value="row[column.key]" />
              <DateTimeText
                v-else-if="isDateColumn(column)"
                :value="row[column.key]"
                :relative="column.relativeTime"
              />
              <span v-else class="cell-text" :title="String(row[column.key] ?? '')">
                {{ displayValue(column, row[column.key]) }}
              </span>
              <button
                v-if="column.copyable && row[column.key]"
                class="cell-copy"
                title="复制"
                @click.stop="copy(row[column.key])"
              >
                <Copy :size="13" />
              </button>
            </td>
            <td v-if="$slots.actions" class="actions-column" @click.stop>
              <slot name="actions" :row="row" />
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="loading" class="loading-line" />
      <div v-if="!loading && !visibleRows.length" class="table-state">{{ emptyText }}</div>
    </div>

    <footer class="table-footer">
      <span>
        第 {{ rangeStart }}-{{ rangeEnd }} 条，共 {{ effectiveTotal }} 条
        <template v-if="selectable && selectedRows.length">；已选 {{ selectedRows.length }} 条</template>
      </span>
      <div v-if="selectable && effectiveTotal" class="selection-actions">
        <span v-if="selectionError" class="selection-error" :title="selectionError">全选失败</span>
        <span v-if="allRowsSelected" class="all-selected-text">已全选所有页（{{ effectiveTotal }} 条）</span>
        <button
          v-else
          class="text-btn"
          type="button"
          :disabled="!canSelectAllRows || selectingAllRows"
          :title="canSelectAllRows ? '选择当前筛选条件下所有分页数据' : '该表格未提供所有页数据加载入口'"
          @click="selectAllRows"
        >
          {{ selectingAllRows ? "正在全选..." : `全选所有页（${effectiveTotal} 条）` }}
        </button>
        <button v-if="selectedRows.length" class="text-btn" type="button" @click="clearSelection">清空选择</button>
      </div>
      <div class="page-controls">
        <button class="icon-btn" title="首页" :disabled="internalPage <= 1" @click="setPage(1)"><ChevronsLeft :size="16" /></button>
        <button class="icon-btn" title="上一页" :disabled="internalPage <= 1" @click="setPage(internalPage - 1)"><ChevronLeft :size="16" /></button>
        <span>{{ internalPage }} / {{ totalPages }}</span>
        <button class="icon-btn" title="下一页" :disabled="internalPage >= totalPages" @click="setPage(internalPage + 1)"><ChevronRight :size="16" /></button>
        <button class="icon-btn" title="末页" :disabled="internalPage >= totalPages" @click="setPage(totalPages)"><ChevronsRight :size="16" /></button>
      </div>
    </footer>
  </section>
</template>

<style scoped>
.table-shell {
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  min-width: 0;
  overflow: hidden;
}

.table-toolbar {
  align-items: end;
  border-bottom: 1px solid var(--border);
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 58px;
  padding: 10px 12px;
}

.search-control {
  align-items: center;
  background: var(--input-bg);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  display: flex;
  gap: 8px;
  min-height: 36px;
  padding: 0 10px;
  width: min(360px, 100%);
}

.search-control input,
.filter-control select,
.page-size-control select {
  background: transparent;
  border: 0;
  color: var(--text-primary);
  outline: none;
}

.search-control input { min-width: 0; width: 100%; }
.search-control svg { color: var(--text-faint); flex: 0 0 auto; }

.filter-control,
.page-size-control {
  display: grid;
  gap: 3px;
}

.filter-control span,
.page-size-control span {
  color: var(--text-faint);
  font-size: 10px;
  font-weight: 700;
}

.filter-control select,
.page-size-control select {
  background: var(--input-bg);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  min-height: 36px;
  padding: 0 26px 0 9px;
}

.toolbar-spacer { flex: 1 1 auto; }
.compact-btn { min-height: 36px; }
.table-viewport { min-height: 96px; overflow: auto; position: relative; }
.table-viewport.loading { opacity: 0.72; }

table {
  border-collapse: separate;
  border-spacing: 0;
  font-size: 12px;
  min-width: 100%;
  width: max-content;
}

th,
td {
  border-bottom: 1px solid var(--border);
  max-width: 360px;
  padding: 9px 11px;
  text-align: left;
  vertical-align: middle;
}

th {
  background: var(--table-head-bg);
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 800;
  position: sticky;
  top: 0;
  white-space: nowrap;
  z-index: 1;
}

tbody tr { cursor: default; }
tbody tr:hover { background: var(--row-hover); }
tbody tr:last-child td { border-bottom: 0; }
.mono { font-family: "SFMono-Regular", Consolas, monospace; }
.cell-text { display: inline-block; max-width: 330px; overflow-wrap: anywhere; }
.cell-copy { background: transparent; color: var(--text-faint); cursor: pointer; margin-left: 5px; padding: 2px; vertical-align: middle; }
.cell-copy:hover { color: var(--accent); }
.sort-button { align-items: center; background: transparent; color: inherit; cursor: pointer; display: inline-flex; font: inherit; gap: 5px; padding: 0; }
.select-column { text-align: center; width: 38px; }
.actions-column { position: sticky; right: 0; white-space: nowrap; }
th.actions-column { background: var(--table-head-bg); }
td.actions-column { background: var(--panel-bg); }
tr:hover td.actions-column { background: var(--row-hover-solid); }

.table-state {
  align-items: center;
  color: var(--text-muted);
  display: flex;
  flex-direction: column;
  gap: 8px;
  justify-content: center;
  min-height: 120px;
  padding: 20px;
  text-align: center;
}
.error-state { color: var(--danger-text); }
.error-state span { color: var(--text-muted); max-width: 720px; overflow-wrap: anywhere; }
.loading-line { animation: loading 1.2s ease-in-out infinite; background: var(--accent); height: 2px; left: 0; position: absolute; top: 0; width: 34%; }

.table-footer {
  align-items: center;
  border-top: 1px solid var(--border);
  color: var(--text-muted);
  display: flex;
  font-size: 12px;
  gap: 12px;
  justify-content: space-between;
  min-height: 48px;
  padding: 7px 12px;
}
.page-controls { align-items: center; display: flex; gap: 4px; }
.page-controls > span { min-width: 64px; text-align: center; }
.text-btn { background: transparent; color: var(--accent); cursor: pointer; }
.text-btn:disabled { color: var(--text-faint); cursor: not-allowed; }
.selection-actions { align-items: center; display: flex; flex-wrap: wrap; gap: 10px; }
.all-selected-text { color: var(--success-text); font-weight: 700; }
.selection-error { color: var(--danger-text); cursor: help; font-weight: 700; }
.spin { animation: spin 0.9s linear infinite; }

@keyframes loading { from { transform: translateX(-100%); } to { transform: translateX(400%); } }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 767px) {
  .search-control { width: 100%; }
  .filter-control { flex: 1 1 140px; }
  .toolbar-spacer { display: none; }
  .table-footer { align-items: flex-start; flex-direction: column; }
  .page-controls { justify-content: space-between; width: 100%; }
}
</style>
