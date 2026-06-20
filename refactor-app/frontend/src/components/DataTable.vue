<script setup lang="ts">
import { computed, ref, watch } from "vue";

import StatusBadge from "./StatusBadge.vue";

export type Column = {
  key: string;
  label: string;
  badge?: boolean;
  mono?: boolean;
  summary?: boolean | number;
};

export type FilterOption = {
  label: string;
  value: string;
};

export type TableFilter = {
  key: string;
  label: string;
  options: FilterOption[];
};

const props = defineProps<{
  columns: Column[];
  rows: Record<string, unknown>[];
  loading?: boolean;
  error?: string;
  emptyText?: string;
  filters?: TableFilter[];
  selectable?: boolean;
}>();

const emit = defineEmits<{
  rowClick: [row: Record<string, unknown>];
  refresh: [];
  selectionChange: [rows: Record<string, unknown>[]];
}>();

const search = ref("");
const page = ref(1);
const pageSize = ref(50);
const selectedIds = ref<Set<string>>(new Set());
const filterValues = ref<Record<string, string>>({});

function rowKey(row: Record<string, unknown>, index = 0) {
  return String(row.id ?? `${row.email ?? "row"}-${index}`);
}

const filteredRows = computed(() => {
  const needle = search.value.trim().toLowerCase();
  return props.rows.filter((row) => {
    const matchesSearch = !needle || JSON.stringify(row).toLowerCase().includes(needle);
    const matchesFilters = Object.entries(filterValues.value).every(([key, value]) => {
      if (!value) return true;
      return String(row[key] ?? "") === value;
    });
    return matchesSearch && matchesFilters;
  });
});

const totalPages = computed(() => Math.max(1, Math.ceil(filteredRows.value.length / pageSize.value)));

const pagedRows = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  return filteredRows.value.slice(start, start + pageSize.value);
});

const rangeStart = computed(() => (filteredRows.value.length === 0 ? 0 : (page.value - 1) * pageSize.value + 1));
const rangeEnd = computed(() => Math.min(page.value * pageSize.value, filteredRows.value.length));
const selectedRows = computed(() =>
  props.rows.filter((row, index) => selectedIds.value.has(rowKey(row, index)))
);
const pageRowKeys = computed(() => pagedRows.value.map((row, index) => rowKey(row, index)));
const isCurrentPageAllSelected = computed(
  () => pageRowKeys.value.length > 0 && pageRowKeys.value.every((key) => selectedIds.value.has(key))
);

watch([search, pageSize, () => props.rows], () => {
  page.value = 1;
});

watch(filterValues, () => {
  page.value = 1;
}, { deep: true });

watch(totalPages, (next) => {
  if (page.value > next) page.value = next;
});

watch(selectedRows, (rows) => {
  emit("selectionChange", rows);
});

async function copy(value: unknown) {
  await navigator.clipboard.writeText(String(value ?? ""));
}

function toggleRow(row: Record<string, unknown>, index: number) {
  const next = new Set(selectedIds.value);
  const key = rowKey(row, index);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  selectedIds.value = next;
}

function toggleCurrentPage() {
  const next = new Set(selectedIds.value);
  if (isCurrentPageAllSelected.value) {
    pageRowKeys.value.forEach((key) => next.delete(key));
  } else {
    pageRowKeys.value.forEach((key) => next.add(key));
  }
  selectedIds.value = next;
}

function clearSelection() {
  selectedIds.value = new Set();
}

function displayValue(column: Column, value: unknown) {
  const text = String(value ?? "");
  if (!column.summary) return text;
  const limit = typeof column.summary === "number" ? column.summary : 28;
  if (text.length <= limit) return text;
  const headLength = Math.max(6, Math.floor((limit - 1) * 0.58));
  const tailLength = Math.max(4, limit - headLength - 1);
  return `${text.slice(0, headLength)}…${text.slice(-tailLength)}`;
}
</script>

<template>
  <section class="table-shell panel">
    <div class="table-tools">
      <div class="table-tool-block search-block">
        <div class="tool-block-heading">
          <strong>搜索条件</strong>
          <span>只筛选当前表格数据</span>
        </div>
        <label class="filter-field table-search">
          <span>关键词</span>
          <input v-model="search" class="input" placeholder="搜索当前表格..." />
        </label>
        <div v-if="(filters ?? []).length > 0" class="filter-row">
          <label v-for="filter in filters ?? []" :key="filter.key" class="filter-field compact-filter">
            <span>{{ filter.label }}</span>
            <select v-model="filterValues[filter.key]" class="select compact">
              <option value="">全部</option>
              <option v-for="option in filter.options" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </label>
        </div>
      </div>
      <div class="table-tool-block table-utility-block">
        <div class="tool-block-heading">
          <strong>表格工具</strong>
          <span>分页和刷新</span>
        </div>
        <div class="table-actions">
          <label class="filter-field compact-filter">
            <span>每页</span>
            <select v-model.number="pageSize" class="select compact">
              <option :value="20">20</option>
              <option :value="50">50</option>
              <option :value="100">100</option>
              <option :value="200">200</option>
            </select>
          </label>
          <button class="btn" @click="emit('refresh')">刷新表格</button>
        </div>
      </div>
    </div>

    <div v-if="loading" class="state">加载中...</div>
    <div v-else-if="error" class="state error">{{ error }}</div>
    <div v-else-if="filteredRows.length === 0" class="state">{{ emptyText ?? "暂无数据。" }}</div>
    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th v-if="selectable" class="select-col">
              <input
                type="checkbox"
                :checked="isCurrentPageAllSelected"
                aria-label="选择当前页"
                @change="toggleCurrentPage"
              />
            </th>
            <th v-for="column in columns" :key="column.key">{{ column.label }}</th>
            <th v-if="$slots.actions">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in pagedRows" :key="String(row.id ?? index)" @click="emit('rowClick', row)">
            <td v-if="selectable" class="select-col" @click.stop>
              <input
                type="checkbox"
                :checked="selectedIds.has(rowKey(row, index))"
                :aria-label="`选择 ${row.email ?? row.id ?? index}`"
                @change="toggleRow(row, index)"
              />
            </td>
            <td v-for="column in columns" :key="column.key" :class="{ mono: column.mono }">
              <StatusBadge v-if="column.badge" :value="row[column.key]" />
              <button v-else class="cell-copy" :title="String(row[column.key] ?? '')" @click.stop="copy(row[column.key])">
                {{ displayValue(column, row[column.key]) }}
              </button>
            </td>
            <td v-if="$slots.actions" class="actions-cell" @click.stop>
              <slot name="actions" :row="row" />
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="!loading && !error && filteredRows.length > 0" class="pagination">
      <div class="page-summary">
        第 {{ rangeStart }}-{{ rangeEnd }} 条，共 {{ filteredRows.length }} 条
        <template v-if="filteredRows.length !== rows.length">（原始 {{ rows.length }} 条）</template>
        <template v-if="selectable">；已选 {{ selectedRows.length }} 条</template>
      </div>
      <div class="page-buttons">
        <button v-if="selectable" class="btn" :disabled="selectedRows.length === 0" @click="clearSelection">
          清空选择
        </button>
        <button class="btn" :disabled="page <= 1" @click="page = 1">首页</button>
        <button class="btn" :disabled="page <= 1" @click="page -= 1">上一页</button>
        <span class="page-current">{{ page }} / {{ totalPages }}</span>
        <button class="btn" :disabled="page >= totalPages" @click="page += 1">下一页</button>
        <button class="btn" :disabled="page >= totalPages" @click="page = totalPages">末页</button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.table-shell {
  overflow: hidden;
  min-width: 0;
}

.table-tools {
  border-bottom: 1px solid var(--border);
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(0, 1fr) auto;
  padding: 12px;
}

.table-tool-block {
  background: rgba(8, 13, 25, 0.42);
  border: 1px solid rgba(38, 50, 73, 0.72);
  border-radius: 14px;
  display: grid;
  gap: 10px;
  min-width: 0;
  padding: 12px;
}

.tool-block-heading {
  align-items: baseline;
  display: flex;
  gap: 8px;
  justify-content: space-between;
}

.tool-block-heading strong {
  color: var(--text-primary);
  font-size: 13px;
  letter-spacing: -0.01em;
}

.tool-block-heading span {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 700;
}

.table-search {
  width: min(100%, 520px);
}

.filter-row {
  align-items: end;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.table-actions,
.page-buttons,
.pagination {
  align-items: center;
  display: flex;
  gap: 8px;
}

.compact-filter {
  align-items: center;
  display: grid;
  gap: 5px;
  grid-auto-flow: column;
  grid-template-columns: max-content auto;
}

.compact {
  min-height: 34px;
  min-width: 84px;
  padding: 0 10px;
}

.table-wrap {
  overflow: auto;
}

table {
  border-collapse: collapse;
  min-width: min(980px, calc(100vw - 48px));
  width: 100%;
}

th {
  background: rgba(15, 23, 42, 0.88);
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 900;
  letter-spacing: 0.06em;
  padding: 11px 12px;
  position: sticky;
  text-align: left;
  text-transform: uppercase;
  top: 0;
  z-index: 1;
}

.select-col {
  max-width: 44px;
  min-width: 44px;
  text-align: center;
  width: 44px;
}

.select-col input {
  accent-color: var(--accent);
  cursor: pointer;
}

td {
  border-top: 1px solid rgba(38, 50, 73, 0.76);
  color: var(--text-primary);
  font-size: 13px;
  max-width: 280px;
  padding: 10px 12px;
  vertical-align: middle;
}

tr {
  cursor: pointer;
}

tbody tr:hover {
  background: rgba(59, 130, 246, 0.07);
}

.cell-copy {
  background: transparent;
  color: inherit;
  cursor: copy;
  display: block;
  max-width: 100%;
  overflow: hidden;
  padding: 0;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mono .cell-copy {
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
}

.actions-cell {
  white-space: nowrap;
}

.state {
  color: var(--text-muted);
  padding: 28px;
}

.error {
  color: #fca5a5;
}

.pagination {
  border-top: 1px solid var(--border);
  justify-content: space-between;
  padding: 12px;
}

.page-summary,
.page-current {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 800;
}

@media (max-width: 767px) {
  .table-tools {
    grid-template-columns: 1fr;
  }

  .table-actions,
  .pagination {
    align-items: stretch;
    flex-direction: column;
  }

  .page-buttons {
    flex-wrap: wrap;
  }

  .table-search {
    width: 100%;
  }

  .compact-filter {
    align-items: stretch;
    grid-auto-flow: row;
    grid-template-columns: 1fr;
  }

  table {
    min-width: 720px;
  }

  th,
  td {
    padding: 9px 10px;
  }
}
</style>
