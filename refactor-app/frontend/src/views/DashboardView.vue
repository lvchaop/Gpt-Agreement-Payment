<script setup lang="ts">
import { AlertTriangle, RefreshCw } from "@lucide/vue";
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { resourcesApi, type Row } from "../api/resources";
import DataTable, { type Column } from "../components/DataTable.vue";
import DateTimeText from "../components/DateTimeText.vue";
import MetricCard from "../components/MetricCard.vue";
import PageHeader from "../components/PageHeader.vue";
import { useOpsStore } from "../stores/ops";

const router = useRouter();
const store = useOpsStore();
const loading = ref(false);
const error = ref("");
const metrics = ref<Record<string, number>>({});
const failedJobs = ref<Row[]>([]);
const generatedAt = ref("");

const jobColumns: Column[] = [
  { key: "id", label: "任务 ID", mono: true, summary: 24, copyable: true },
  { key: "type", label: "任务类型" },
  { key: "job_status", label: "状态", badge: true },
  { key: "created_by", label: "触发来源" },
  { key: "updated_at", label: "更新时间", type: "datetime", relativeTime: true },
];

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const result = await resourcesApi.overview();
    metrics.value = result.metrics;
    failedJobs.value = result.recent_failed_jobs;
    generatedAt.value = result.generated_at;
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
  <PageHeader title="运营总览" description="当前任务积压、账号可用性、交付容量和异常入口。">
    <DateTimeText v-if="generatedAt" :value="generatedAt" relative />
    <button class="icon-btn labeled" @click="load"><RefreshCw :size="16" :class="{ spin: loading }" />刷新</button>
  </PageHeader>

  <section v-if="error" class="overview-error">
    <AlertTriangle :size="17" /><span>{{ error }}</span><button class="btn" @click="load">重试</button>
  </section>

  <div class="grid-4 metrics-grid">
    <MetricCard label="运行中的 Job" :value="metrics.running_jobs ?? 0" tone="info" />
    <MetricCard label="排队中的 Job" :value="metrics.queued_jobs ?? 0" tone="warning" />
    <MetricCard label="排队中的 Work" :value="metrics.queued_work ?? 0" tone="warning" />
    <MetricCard label="24 小时失败 Job" :value="metrics.failed_jobs_24h ?? 0" tone="danger" />
    <MetricCard label="Session 异常账号" :value="metrics.session_issues ?? 0" tone="danger" />
    <MetricCard label="待授权成员" :value="metrics.unauthorized_memberships ?? 0" tone="warning" />
    <MetricCard label="待结算/失败推送" :value="metrics.push_attention ?? 0" tone="warning" />
    <MetricCard label="可用静态代理" :value="metrics.available_static_proxies ?? 0" tone="success" />
    <MetricCard label="下游推送余额" :value="metrics.downstream_push_balance ?? 0" tone="info" />
    <MetricCard label="下游最大坑位" :value="metrics.downstream_slot_limit ?? 0" tone="neutral" />
  </div>

  <section class="dashboard-section">
    <div class="section-heading"><div><h2>最近失败任务</h2><p>点击任务查看 Work、运行步骤和事件日志。</p></div><button class="btn" @click="router.push('/jobs')">查看全部</button></div>
    <DataTable
      :columns="jobColumns"
      :rows="failedJobs"
      :loading="loading"
      empty-text="最近没有失败任务。"
      @refresh="load"
      @row-click="(row) => row.id && router.push(`/jobs/${row.id}`)"
    />
  </section>
</template>

<style scoped>
.metrics-grid { margin-bottom: 18px; }
.dashboard-section { display: grid; gap: 9px; }
.section-heading { align-items: flex-end; display: flex; gap: 12px; justify-content: space-between; }
.section-heading h2 { font-size: 14px; margin: 0; }
.section-heading p { color: var(--text-muted); font-size: 11px; margin: 3px 0 0; }
.overview-error { align-items: center; background: rgba(215, 91, 91, 0.1); border: 1px solid rgba(215, 91, 91, 0.45); border-radius: var(--radius-md); color: var(--danger-text); display: flex; gap: 8px; margin-bottom: 12px; padding: 10px 12px; }
.overview-error span { flex: 1; font-size: 12px; }.spin { animation: spin 0.9s linear infinite; }@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 600px) { .metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
