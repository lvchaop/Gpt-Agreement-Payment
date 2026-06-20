<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import DataTable, { type Column } from "../components/DataTable.vue";
import PageHeader from "../components/PageHeader.vue";
import { cancelJob, listJobs, type Job } from "../api/jobs";
import { useOpsStore } from "../stores/ops";

const router = useRouter();
const store = useOpsStore();
const rows = ref<Job[]>([]);
const loading = ref(false);
const error = ref("");
const cancellingJobId = ref("");
let pollTimer: number | undefined;

const hasActiveJobs = computed(() =>
  rows.value.some((row) => row.job_status === "queued" || row.job_status === "running"),
);

const columns: Column[] = [
  { key: "id", label: "任务 ID", mono: true },
  { key: "type", label: "任务类型" },
  { key: "job_status", label: "状态", badge: true },
  { key: "priority", label: "优先级" },
  { key: "created_by", label: "创建人" },
  { key: "created_at", label: "创建时间" },
  { key: "updated_at", label: "更新时间" },
];

async function load() {
  loading.value = true;
  error.value = "";
  try {
    rows.value = await listJobs();
    store.touchRefresh();
  } catch (err) {
    error.value = String((err as Error).message ?? err);
  } finally {
    loading.value = false;
  }
}

async function cancelQueuedJob(row: Record<string, unknown>) {
  const jobId = String(row.id ?? "");
  if (row.job_status !== "queued" || !jobId || cancellingJobId.value) return;
  cancellingJobId.value = jobId;
  error.value = "";
  try {
    await cancelJob(jobId);
    store.toast("任务已取消", jobId, "success");
    await load();
  } catch (err) {
    error.value = String((err as Error).message ?? err);
    store.toast("取消失败", error.value, "error");
  } finally {
    cancellingJobId.value = "";
  }
}

onMounted(() => {
  void load();
  pollTimer = window.setInterval(() => {
    if (!loading.value && hasActiveJobs.value) void load();
  }, 2000);
});

onBeforeUnmount(() => {
  if (pollTimer) window.clearInterval(pollTimer);
});
</script>

<template>
  <PageHeader title="任务" description="所有长任务都从这里追踪运行、步骤和事件。">
    <button class="btn primary" @click="load">刷新</button>
  </PageHeader>
  <DataTable
    :columns="columns"
    :rows="rows"
    :loading="loading"
    :error="error"
    empty-text="暂无任务。"
    @refresh="load"
    @row-click="(row) => row.id && router.push(`/jobs/${row.id}`)"
  >
    <template #actions="{ row }">
      <button
        v-if="row.job_status === 'queued'"
        class="btn danger compact-action"
        :disabled="cancellingJobId === row.id"
        @click="cancelQueuedJob(row)"
      >
        {{ cancellingJobId === row.id ? "取消中" : "取消" }}
      </button>
    </template>
  </DataTable>
</template>

<style scoped>
.compact-action {
  min-height: 30px;
  padding: 0 10px;
}
</style>
