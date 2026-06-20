<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import DataTable, { type Column } from "../components/DataTable.vue";
import MetricCard from "../components/MetricCard.vue";
import PageHeader from "../components/PageHeader.vue";
import { listJobs, type Job } from "../api/jobs";
import { resourcesApi, type Row } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const router = useRouter();
const store = useOpsStore();
const loading = ref(false);
const error = ref("");
const jobs = ref<Job[]>([]);
const workspaces = ref<Row[]>([]);
const memberships = ref<Row[]>([]);
const batches = ref<Row[]>([]);
const credentials = ref<Row[]>([]);
const proxies = ref<Row[]>([]);
const mailLeases = ref<Row[]>([]);

const failedJobs = computed(() => jobs.value.filter((job) => job.job_status === "failed").slice(0, 8));
const recentBatches = computed(() => batches.value.slice(0, 8));
const tokenErrors = computed(
  () =>
    credentials.value.filter((row) =>
      ["invalid", "error", "expired"].includes(String(row.credential_status ?? "")),
    ).length,
);

const jobColumns: Column[] = [
  { key: "id", label: "任务 ID", mono: true },
  { key: "type", label: "任务类型" },
  { key: "job_status", label: "状态", badge: true },
  { key: "updated_at", label: "更新时间" },
];

const batchColumns: Column[] = [
  { key: "id", label: "批次 ID", mono: true },
  { key: "team_workspace_id", label: "团队空间", mono: true },
  { key: "batch_status", label: "批次状态", badge: true },
  { key: "activation_status", label: "生效状态", badge: true },
  { key: "success_count", label: "成功数" },
  { key: "failed_count", label: "失败数" },
];

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const result = await Promise.all([
      listJobs(),
      resourcesApi.workspaces(),
      resourcesApi.memberships(),
      resourcesApi.batches(),
      resourcesApi.credentials(),
      resourcesApi.proxies(),
      resourcesApi.mailLeases(),
    ]);
    [jobs.value, workspaces.value, memberships.value, batches.value, credentials.value, proxies.value, mailLeases.value] =
      result;
    store.touchRefresh();
  } catch (err) {
    error.value = String((err as Error).message ?? err);
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <PageHeader title="总览" description="看系统是否卡住、失败、缺代理、缺 token。">
    <button class="btn primary" @click="load">刷新</button>
  </PageHeader>

  <div class="grid-4">
    <MetricCard label="排队任务" :value="jobs.filter((j) => j.job_status === 'queued').length" tone="info" />
    <MetricCard label="运行任务" :value="jobs.filter((j) => j.job_status === 'running').length" tone="purple" />
    <MetricCard label="失败任务" :value="failedJobs.length" tone="danger" helper="下方展示最近失败" />
    <MetricCard label="有效团队空间" :value="workspaces.filter((w) => w.workspace_status === 'active').length" tone="success" />
    <MetricCard label="有效成员关系" :value="memberships.filter((m) => m.membership_status === 'active').length" tone="success" />
    <MetricCard label="Token 异常" :value="tokenErrors" tone="warning" />
    <MetricCard label="可用代理" :value="proxies.filter((p) => p.proxy_status === 'available').length" tone="info" />
    <MetricCard label="邮箱租约" :value="mailLeases.length" tone="neutral" />
  </div>

  <div class="grid-2 dashboard-tables">
    <section>
      <PageHeader title="最近失败任务" />
      <DataTable
        :columns="jobColumns"
        :rows="failedJobs"
        :loading="loading"
        :error="error"
        empty-text="暂无失败任务。"
        @refresh="load"
        @row-click="(row) => row.id && router.push(`/jobs/${row.id}`)"
      />
    </section>
    <section>
      <PageHeader title="最近批次" />
      <DataTable
        :columns="batchColumns"
        :rows="recentBatches"
        :loading="loading"
        :error="error"
        empty-text="暂无批次。"
        @refresh="load"
        @row-click="(row) => row.id && router.push(`/join-batches/${row.id}`)"
      />
    </section>
  </div>
</template>

<style scoped>
.dashboard-tables {
  margin-top: 24px;
}
</style>
