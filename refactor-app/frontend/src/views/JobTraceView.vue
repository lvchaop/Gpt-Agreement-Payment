<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import DataTable, { type Column } from "../components/DataTable.vue";
import JsonBlock from "../components/JsonBlock.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import {
  cancelJob,
  cancelWorkItem,
  getJob,
  listEvents,
  listRuns,
  listSteps,
  listWorkItems,
  type Job,
  type JobEvent,
  type JobRun,
  type JobStep,
  type WorkItem,
} from "../api/jobs";
import { useOpsStore } from "../stores/ops";

const route = useRoute();
const store = useOpsStore();
const jobId = computed(() => String(route.params.jobId));
const job = ref<Job | null>(null);
const runs = ref<JobRun[]>([]);
const workItems = ref<WorkItem[]>([]);
const steps = ref<JobStep[]>([]);
const events = ref<JobEvent[]>([]);
const loading = ref(false);
const cancelling = ref(false);
const cancellingWorkItemId = ref("");
const error = ref("");
const selectedRun = ref("");
const selectedStep = ref<JobStep | null>(null);
const selectedEvent = ref<JobEvent | null>(null);
let pollTimer: number | undefined;
const queuedWorkCount = computed(
  () => workItems.value.filter((item) => item.work_status === "queued").length,
);
const hasRunningWork = computed(() =>
  workItems.value.some((item) => item.work_status === "queued" || item.work_status === "running"),
);
const shouldPoll = computed(
  () => job.value?.job_status === "queued" || job.value?.job_status === "running" || hasRunningWork.value,
);

const runColumns: Column[] = [
  { key: "id", label: "运行 ID", mono: true },
  { key: "run_status", label: "运行状态", badge: true },
  { key: "attempt", label: "尝试次数" },
  { key: "started_at", label: "开始时间" },
  { key: "finished_at", label: "结束时间" },
  { key: "error_code", label: "错误码", badge: true },
];

const workColumns: Column[] = [
  { key: "id", label: "Work ID", mono: true },
  { key: "work_type", label: "类型" },
  { key: "work_status", label: "状态", badge: true },
  { key: "claimed_by", label: "执行者" },
  { key: "started_at", label: "开始时间" },
  { key: "finished_at", label: "结束时间" },
  { key: "error_code", label: "错误码", badge: true },
];

const stepColumns: Column[] = [
  { key: "name", label: "步骤" },
  { key: "step_status", label: "步骤状态", badge: true },
  { key: "attempt", label: "尝试次数" },
  { key: "error_code", label: "错误码", badge: true },
];

const eventColumns: Column[] = [
  { key: "level", label: "级别", badge: true },
  { key: "event_type", label: "事件类型" },
  { key: "message", label: "消息" },
  { key: "ts", label: "时间" },
];

async function load() {
  loading.value = true;
  error.value = "";
  try {
    job.value = await getJob(jobId.value);
    [runs.value, workItems.value] = await Promise.all([
      listRuns(jobId.value),
      listWorkItems(jobId.value),
    ]);
    selectedRun.value = runs.value[0]?.id ?? "";
    if (selectedRun.value) {
      await loadRun(selectedRun.value);
    }
  } catch (err) {
    error.value = String((err as Error).message ?? err);
  } finally {
    loading.value = false;
  }
}

async function cancelQueuedWorkItem(row: Record<string, unknown>) {
  const workItemId = String(row.id ?? "");
  if (row.work_status !== "queued" || !workItemId || cancellingWorkItemId.value) return;
  cancellingWorkItemId.value = workItemId;
  error.value = "";
  try {
    await cancelWorkItem(workItemId);
    store.toast("Work 已取消", workItemId, "success");
    workItems.value = await listWorkItems(jobId.value);
  } catch (err) {
    error.value = String((err as Error).message ?? err);
    store.toast("取消 Work 失败", error.value, "error");
  } finally {
    cancellingWorkItemId.value = "";
  }
}

async function loadRun(runId: string) {
  selectedRun.value = runId;
  [steps.value, events.value] = await Promise.all([listSteps(runId), listEvents(runId)]);
  selectedStep.value = steps.value.find((step) => step.step_status === "failed") ?? steps.value[0] ?? null;
  selectedEvent.value = events.value.find((event) => event.level === "ERROR") ?? events.value[0] ?? null;
}

async function cancelCurrentJob() {
  if (!job.value || cancelling.value) return;
  cancelling.value = true;
  error.value = "";
  try {
    job.value = await cancelJob(job.value.id);
    workItems.value = await listWorkItems(jobId.value);
    store.toast("任务/排队 Work 已取消", job.value.id, "success");
  } catch (err) {
    error.value = String((err as Error).message ?? err);
    store.toast("取消失败", error.value, "error");
  } finally {
    cancelling.value = false;
  }
}

onMounted(() => {
  void load();
  pollTimer = window.setInterval(() => {
    if (!loading.value && shouldPoll.value) void load();
  }, 2000);
});

onBeforeUnmount(() => {
  if (pollTimer) window.clearInterval(pollTimer);
});
</script>

<template>
  <PageHeader title="任务追踪" :description="jobId">
    <button
      v-if="job?.job_status === 'queued' || queuedWorkCount > 0"
      class="btn danger"
      :disabled="cancelling"
      @click="cancelCurrentJob"
    >
      {{ cancelling ? "取消中..." : queuedWorkCount > 0 ? "取消排队 Work" : "取消任务" }}
    </button>
    <button class="btn primary" @click="load">刷新</button>
  </PageHeader>

  <section v-if="job" class="panel summary">
    <div>
      <span>任务类型</span>
      <strong>{{ job.type }}</strong>
    </div>
    <div>
      <span>任务状态</span>
      <StatusBadge :value="job.job_status" />
    </div>
    <div>
      <span>创建时间</span>
      <strong>{{ job.created_at }}</strong>
    </div>
  </section>

  <div class="stack trace">
    <DataTable :columns="workColumns" :rows="workItems" empty-text="暂无 Work。" >
      <template #actions="{ row }">
        <button
          v-if="row.work_status === 'queued'"
          class="btn danger compact-action"
          :disabled="cancellingWorkItemId === row.id"
          @click="cancelQueuedWorkItem(row)"
        >
          {{ cancellingWorkItemId === row.id ? "取消中" : "取消" }}
        </button>
      </template>
    </DataTable>
    <DataTable :columns="runColumns" :rows="runs" :loading="loading" :error="error" empty-text="暂无运行记录。" @row-click="(row) => row.id && loadRun(String(row.id))" />
    <DataTable
      :columns="stepColumns"
      :rows="steps"
      empty-text="暂无步骤记录。"
      @row-click="(row) => (selectedStep = row as JobStep)"
    />
    <JsonBlock
      v-if="selectedStep"
      title="选中步骤详情"
      :value="{
        name: selectedStep.name,
        status: selectedStep.step_status,
        input_json: selectedStep.input_json,
        output_json: selectedStep.output_json,
        error_code: selectedStep.error_code,
        error_message: selectedStep.error_message,
      }"
      collapsed
    />
    <DataTable
      :columns="eventColumns"
      :rows="events"
      empty-text="暂无事件记录。"
      @row-click="(row) => (selectedEvent = row as JobEvent)"
    />
    <JsonBlock
      v-if="selectedEvent"
      title="选中事件详情"
      :value="{
        level: selectedEvent.level,
        event_type: selectedEvent.event_type,
        message: selectedEvent.message,
        data_json: selectedEvent.data_json,
      }"
      collapsed
    />
    <JsonBlock v-if="job" title="任务输入 JSON" :value="job.input_json" collapsed />
  </div>
</template>

<style scoped>
.summary {
  display: grid;
  gap: 12px;
  grid-template-columns: 2fr 1fr 2fr;
  margin-bottom: 18px;
  padding: 16px;
}

.summary span {
  color: var(--text-muted);
  display: block;
  font-size: 12px;
  font-weight: 800;
  margin-bottom: 6px;
}

.summary strong {
  overflow-wrap: anywhere;
}

.trace {
  gap: 18px;
}

.compact-action {
  min-height: 30px;
  padding: 0 10px;
}

@media (max-width: 767px) {
  .summary {
    grid-template-columns: 1fr;
  }
}
</style>
