<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";

import { cancelJob, listJobs } from "../api/jobs";
import type { PagedResult, PageQuery, Row } from "../api/types";
import ConfirmModal from "../components/ConfirmModal.vue";
import ResourcePage from "../components/ResourcePage.vue";
import type { Column, TableFilter } from "../components/DataTable.vue";
import { useOpsStore } from "../stores/ops";

const router = useRouter();
const store = useOpsStore();
const pageRef = ref<InstanceType<typeof ResourcePage> | null>(null);
const pendingCancel = ref<Row | null>(null);
const cancelling = ref(false);

const columns: Column[] = [
  { key: "id", label: "任务 ID", mono: true, summary: 24, copyable: true },
  { key: "type", label: "任务类型", sortable: true },
  { key: "job_status", label: "状态", badge: true, sortable: true },
  { key: "work_progress", label: "Work 进度" },
  { key: "work_skipped", label: "跳过 Work" },
  { key: "work_failed", label: "失败 Work" },
  { key: "priority", label: "优先级", sortable: true },
  { key: "created_by", label: "触发来源" },
  { key: "created_at", label: "创建时间", type: "datetime", relativeTime: true, sortable: true },
  { key: "updated_at", label: "更新时间", type: "datetime", relativeTime: true, sortable: true },
];

const filters: TableFilter[] = [{
  key: "status", label: "任务状态", options: [
    { label: "排队中", value: "queued" }, { label: "运行中", value: "running" },
    { label: "成功", value: "succeeded" }, { label: "失败", value: "failed" },
    { label: "已取消", value: "cancelled" },
  ],
}];

async function loader(query: PageQuery): Promise<PagedResult<Row>> {
  const result = await listJobs(query);
  return {
    ...result,
    items: result.items.map((job) => {
      const progress = (job.progress ?? {}) as Record<string, number>;
      const done = Number(progress.succeeded || 0) + Number(progress.skipped || 0) + Number(progress.failed || 0) + Number(progress.cancelled || 0);
      return {
        ...job,
        work_progress: `${done} / ${Number(progress.total || 0)}`,
        work_skipped: Number(progress.skipped || 0),
        work_failed: Number(progress.failed || 0),
      };
    }),
  };
}

async function confirmCancel() {
  const id = String(pendingCancel.value?.id ?? "");
  if (!id) return;
  cancelling.value = true;
  try {
    await cancelJob(id);
    store.toast("任务已取消", id, "success");
    pendingCancel.value = null;
    await pageRef.value?.load();
  } catch (err) {
    store.toast("取消失败", String((err as Error).message ?? err), "error");
  } finally { cancelling.value = false; }
}
</script>

<template>
  <ResourcePage
    ref="pageRef"
    title="任务日志"
    description="统一查看 Job、Work、步骤与事件；Work 数量表示同一时刻允许执行的 Work。"
    :columns="columns"
    :loader="loader"
    :filters="filters"
    default-sort="-created_at"
    empty-text="暂无任务。"
    @row-click="(row) => row.id && router.push(`/jobs/${row.id}`)"
  >
    <template #rowActions="{ row }">
      <button v-if="row.job_status === 'queued'" class="btn danger" @click="pendingCancel = row">取消</button>
    </template>
  </ResourcePage>
  <ConfirmModal
    :open="Boolean(pendingCancel)"
    title="取消排队任务"
    message="任务尚未执行。确认后会同时取消该任务下仍在排队的 Work。"
    :summary="{ '任务 ID': pendingCancel?.id, '任务类型': pendingCancel?.type }"
    confirm-text="确认取消"
    danger
    :busy="cancelling"
    @close="pendingCancel = null"
    @confirm="confirmCancel"
  />
</template>
