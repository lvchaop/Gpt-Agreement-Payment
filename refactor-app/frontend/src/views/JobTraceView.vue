<script setup lang="ts">
import { ArrowLeft, RefreshCw } from "@lucide/vue";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import {
  cancelJob, cancelWorkItem, getJobSummary, listEvents, listRuns, listSteps, listWorkItems,
  type JobEvent, type JobRun, type JobStep, type WorkItem,
} from "../api/jobs";
import { loadAllPages, type PagedResult, type PageQuery, type Row } from "../api/types";
import DataTable, { type Column, type TableFilter } from "../components/DataTable.vue";
import DateTimeText from "../components/DateTimeText.vue";
import FormDrawer from "../components/FormDrawer.vue";
import JsonBlock from "../components/JsonBlock.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { useOpsStore } from "../stores/ops";

const route = useRoute();
const router = useRouter();
const store = useOpsStore();
const jobId = computed(() => String(route.params.jobId));
const summary = ref<Row | null>(null);
const runs = ref<JobRun[]>([]);
const steps = ref<JobStep[]>([]);
const workResult = ref<PagedResult<WorkItem>>({ items: [], page: 1, page_size: 50, total: 0, total_pages: 1, sort: "created_at" });
const eventResult = ref<PagedResult<JobEvent>>({ items: [], page: 1, page_size: 100, total: 0, total_pages: 1, sort: "ts" });
const workQuery = ref<PageQuery>({ page: 1, page_size: 50, sort: "created_at" });
const eventQuery = ref<PageQuery>({ page: 1, page_size: 100, sort: "ts" });
const selectedRunId = ref("");
const activeTab = ref<"work" | "events" | "runs" | "input">("work");
const selectedDetail = ref<Row | null>(null);
const detailTitle = ref("");
const loading = ref(false);
const error = ref("");
const cancellingWorkId = ref("");
let pollTimer: number | undefined;

const progress = computed(() => (summary.value?.progress ?? {}) as Record<string, number>);
const isActive = computed(() => ["queued", "running"].includes(String(summary.value?.job_status ?? "")));
const completion = computed(() => {
  const total = Number(progress.value.total || 0);
  const done = Number(progress.value.succeeded || 0) + Number(progress.value.skipped || 0) + Number(progress.value.failed || 0) + Number(progress.value.cancelled || 0);
  return total ? Math.round((done / total) * 100) : 0;
});

const workColumns: Column[] = [
  { key: "id", label: "Work ID", mono: true, summary: 24, copyable: true },
  { key: "work_type", label: "类型" },
  { key: "work_status", label: "状态", badge: true, sortable: true },
  { key: "claimed_by", label: "执行者", summary: 18 },
  { key: "started_at", label: "开始时间", type: "datetime", relativeTime: true, sortable: true },
  { key: "finished_at", label: "结束时间", type: "datetime", sortable: true },
  { key: "error_code", label: "错误码", badge: true },
  { key: "error_message", label: "错误信息", summary: 40 },
];
const workFilters: TableFilter[] = [{ key: "status", label: "Work 状态", options: [
  { label: "排队中", value: "queued" }, { label: "运行中", value: "running" },
  { label: "成功", value: "succeeded" }, { label: "已跳过", value: "skipped" },
  { label: "失败", value: "failed" }, { label: "已取消", value: "cancelled" },
] }];
const eventColumns: Column[] = [
  { key: "ts", label: "时间", type: "datetime", relativeTime: true, sortable: true },
  { key: "level", label: "级别", badge: true, sortable: true },
  { key: "event_type", label: "事件类型", sortable: true },
  { key: "message", label: "消息", summary: 64 },
];
const eventFilters: TableFilter[] = [{ key: "level", label: "级别", options: [
  { label: "ERROR", value: "ERROR" }, { label: "WARNING", value: "WARNING" }, { label: "INFO", value: "INFO" },
] }];
const runColumns: Column[] = [
  { key: "id", label: "运行 ID", mono: true, summary: 24, copyable: true },
  { key: "run_status", label: "状态", badge: true }, { key: "attempt", label: "尝试" },
  { key: "started_at", label: "开始时间", type: "datetime", relativeTime: true },
  { key: "finished_at", label: "结束时间", type: "datetime" }, { key: "error_code", label: "错误码", badge: true },
];
const stepColumns: Column[] = [
  { key: "name", label: "步骤" }, { key: "step_status", label: "状态", badge: true },
  { key: "attempt", label: "尝试" }, { key: "error_code", label: "错误码", badge: true },
];

async function loadWork(query: PageQuery = {}) {
  workQuery.value = { ...workQuery.value, ...query };
  workResult.value = await listWorkItems(jobId.value, workQuery.value);
}

async function loadEvents(query: PageQuery = {}) {
  if (!selectedRunId.value) return;
  eventQuery.value = { ...eventQuery.value, ...query };
  eventResult.value = await listEvents(selectedRunId.value, eventQuery.value);
}

function loadAllWorkRows(query: PageQuery) {
  return loadAllPages(
    (pageQuery) => listWorkItems(jobId.value, pageQuery),
    { ...workQuery.value, ...query },
  );
}

function loadAllEventRows(query: PageQuery) {
  if (!selectedRunId.value) return Promise.resolve([]);
  return loadAllPages(
    (pageQuery) => listEvents(selectedRunId.value, pageQuery),
    { ...eventQuery.value, ...query },
  );
}

async function loadSteps() {
  steps.value = selectedRunId.value ? await listSteps(selectedRunId.value) : [];
}

async function selectRun(runId: string) {
  selectedRunId.value = runId;
  eventQuery.value.page = 1;
  await Promise.all([loadEvents(), loadSteps()]);
}

async function load() {
  loading.value = true; error.value = "";
  try {
    const [nextSummary, nextRuns] = await Promise.all([getJobSummary(jobId.value), listRuns(jobId.value)]);
    summary.value = nextSummary;
    runs.value = nextRuns;
    const nextRun = selectedRunId.value && nextRuns.some((run) => run.id === selectedRunId.value)
      ? selectedRunId.value : nextRuns.at(-1)?.id ?? "";
    await Promise.all([loadWork(), nextRun ? selectRun(nextRun) : Promise.resolve()]);
    store.touchRefresh();
  } catch (err) { error.value = String((err as Error).message ?? err); }
  finally { loading.value = false; }
}

async function cancelCurrentJob() {
  try { await cancelJob(jobId.value); store.toast("排队任务已取消", jobId.value, "success"); await load(); }
  catch (err) { store.toast("取消失败", String((err as Error).message ?? err), "error"); }
}

async function cancelWork(row: Row) {
  const id = String(row.id ?? ""); if (!id) return;
  cancellingWorkId.value = id;
  try { await cancelWorkItem(id); await loadWork(); store.toast("Work 已取消", id, "success"); }
  catch (err) { store.toast("取消 Work 失败", String((err as Error).message ?? err), "error"); }
  finally { cancellingWorkId.value = ""; }
}

function openDetail(title: string, row: Row) { detailTitle.value = title; selectedDetail.value = row; }

onMounted(() => {
  void load();
  pollTimer = window.setInterval(() => { if (!loading.value && isActive.value) void load(); }, 3000);
});
onBeforeUnmount(() => { if (pollTimer) window.clearInterval(pollTimer); });
</script>

<template>
  <PageHeader title="任务详情" :description="jobId">
    <button class="icon-btn labeled" @click="router.push('/jobs')"><ArrowLeft :size="16" />返回</button>
    <button v-if="summary?.job_status === 'queued'" class="btn danger" @click="cancelCurrentJob">取消任务</button>
    <button class="icon-btn labeled" @click="load"><RefreshCw :size="16" :class="{ spin: loading }" />刷新</button>
  </PageHeader>

  <section v-if="summary" class="job-summary">
    <div class="summary-main"><span>任务类型</span><strong>{{ summary.type }}</strong><StatusBadge :value="summary.job_status" /></div>
    <div><span>创建时间</span><DateTimeText :value="summary.created_at" relative /></div>
    <div><span>触发来源</span><strong>{{ summary.created_by || '-' }}</strong></div>
    <div><span>Work 总数</span><strong>{{ progress.total ?? 0 }}</strong></div>
    <div><span>成功 / 跳过 / 失败 / 排队 / 运行</span><strong>{{ progress.succeeded ?? 0 }} / {{ progress.skipped ?? 0 }} / {{ progress.failed ?? 0 }} / {{ progress.queued ?? 0 }} / {{ progress.running ?? 0 }}</strong></div>
    <div class="progress-track"><i :style="{ width: `${completion}%` }" /></div>
  </section>
  <p v-if="error" class="trace-error">{{ error }}</p>

  <nav class="trace-tabs">
    <button :class="{ active: activeTab === 'work' }" @click="activeTab = 'work'">Work（{{ workResult.total }}）</button>
    <button :class="{ active: activeTab === 'events' }" @click="activeTab = 'events'">事件（{{ eventResult.total }}）</button>
    <button :class="{ active: activeTab === 'runs' }" @click="activeTab = 'runs'">运行与步骤（{{ runs.length }}）</button>
    <button :class="{ active: activeTab === 'input' }" @click="activeTab = 'input'">任务输入</button>
  </nav>

  <DataTable
    v-if="activeTab === 'work'" :columns="workColumns" :filters="workFilters" :rows="workResult.items"
    :total="workResult.total" :page="workResult.page" :page-size="workResult.page_size" :sort="workResult.sort" remote
    :all-rows-loader="loadAllWorkRows"
    empty-text="暂无 Work。" @query-change="loadWork" @refresh="loadWork()" @row-click="(row) => openDetail('Work 详情', row)"
  >
    <template #actions="{ row }"><button v-if="row.work_status === 'queued'" class="btn danger" :disabled="cancellingWorkId === row.id" @click="cancelWork(row)">取消</button></template>
  </DataTable>

  <section v-else-if="activeTab === 'events'" class="event-section">
    <label class="run-select"><span>运行批次</span><select v-model="selectedRunId" class="select" @change="selectRun(selectedRunId)"><option v-for="run in runs" :key="run.id" :value="run.id">第 {{ run.attempt }} 次 / {{ run.run_status }} / {{ run.id }}</option></select></label>
    <DataTable :columns="eventColumns" :filters="eventFilters" :rows="eventResult.items" :total="eventResult.total" :page="eventResult.page" :page-size="eventResult.page_size" :sort="eventResult.sort" :all-rows-loader="loadAllEventRows" remote empty-text="暂无事件。" @query-change="loadEvents" @refresh="loadEvents()" @row-click="(row) => openDetail('事件详情', row)" />
  </section>

  <div v-else-if="activeTab === 'runs'" class="trace-split">
    <DataTable :columns="runColumns" :rows="runs" empty-text="暂无运行记录。" @row-click="(row) => row.id && selectRun(String(row.id))" />
    <DataTable :columns="stepColumns" :rows="steps" empty-text="该运行没有步骤。" @row-click="(row) => openDetail('步骤详情', row)" />
  </div>
  <JsonBlock v-else-if="summary" title="任务输入" :value="summary.input_json" />

  <FormDrawer :open="Boolean(selectedDetail)" :title="detailTitle" submit-text="关闭" @close="selectedDetail = null" @submit="selectedDetail = null">
    <JsonBlock title="完整数据（敏感字段已由服务端脱敏）" :value="selectedDetail" />
  </FormDrawer>
</template>

<style scoped>
.job-summary { align-items: center; background: var(--panel-bg); border: 1px solid var(--border); border-radius: var(--radius-md); display: grid; gap: 14px; grid-template-columns: 2fr 1fr 1fr .6fr 1.4fr; margin-bottom: 12px; padding: 12px 14px; position: relative; }
.job-summary > div:not(.progress-track) { display: grid; gap: 4px; }.job-summary span { color: var(--text-faint); font-size: 10px; }.job-summary strong { font-size: 12px; overflow-wrap: anywhere; }.summary-main { align-items: center; display: flex !important; flex-wrap: wrap; gap: 7px !important; }.summary-main span { flex-basis: 100%; }.progress-track { background: var(--panel-bg-3); bottom: 0; height: 3px; left: 0; position: absolute; right: 0; }.progress-track i { background: var(--accent); display: block; height: 100%; }
.trace-tabs { border-bottom: 1px solid var(--border); display: flex; gap: 3px; margin-bottom: 10px; overflow-x: auto; }.trace-tabs button { background: transparent; border-bottom: 2px solid transparent; color: var(--text-muted); cursor: pointer; font-size: 12px; font-weight: 700; padding: 9px 12px; white-space: nowrap; }.trace-tabs button.active { border-bottom-color: var(--accent); color: var(--text-primary); }
.event-section { display: grid; gap: 8px; }.run-select { align-items: center; display: flex; gap: 8px; }.run-select span { color: var(--text-muted); font-size: 11px; }.run-select .select { max-width: 520px; }.trace-split { display: grid; gap: 12px; }.trace-error { color: var(--danger-text); font-size: 12px; }.spin { animation: spin .9s linear infinite; }@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 1000px) { .job-summary { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 600px) { .job-summary { grid-template-columns: 1fr; } }
</style>
