<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import JsonBlock from "../components/JsonBlock.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import {
  getJob,
  listEvents,
  listJobs,
  listRuns,
  listWorkItems,
  type Job,
  type JobEvent,
  type JobRun,
  type WorkItem,
} from "../api/jobs";

type Stage = {
  key: string;
  title: string;
  status: string;
  description: string;
  metrics: Array<{ label: string; value: unknown }>;
  detail?: unknown;
  jobId?: string;
};

const route = useRoute();
const router = useRouter();
const jobs = ref<Job[]>([]);
const selectedJobId = ref("");
const selectedJob = ref<Job | null>(null);
const runs = ref<JobRun[]>([]);
const workItems = ref<WorkItem[]>([]);
const events = ref<JobEvent[]>([]);
const loading = ref(false);
const error = ref("");
let pollTimer: number | undefined;

const automationJobs = computed(() =>
  jobs.value.filter((job) => String(job.type || "").startsWith("automation.")),
);

const latestRun = computed(() => runs.value[0] ?? null);
const output = computed(() => (latestRun.value?.output_json || {}) as Record<string, unknown>);
const input = computed(() => (selectedJob.value?.input_json || {}) as Record<string, unknown>);

const isLive = computed(
  () =>
    selectedJob.value?.job_status === "queued" ||
    selectedJob.value?.job_status === "running" ||
    workItems.value.some((item) => item.work_status === "queued" || item.work_status === "running"),
);

const summaryCards = computed(() => [
  { label: "当前阶段", value: output.value.stage || selectedJob.value?.job_status || "-" },
  { label: "等待秒", value: output.value.next_wait_seconds ?? 0 },
  { label: "空间", value: output.value.team_workspace_id || input.value.team_workspace_id || "-" },
  { label: "选中账号", value: output.value.selected_account_count ?? inputListCount("user_account_ids") },
  { label: "冷却跳过", value: output.value.skipped_cooldown_count ?? 0 },
  { label: "本次操作账号", value: output.value.selected_user_account_id || output.value.current_user_account_id || "-" },
  { label: "生成授权", value: output.value.authorized_credential_id || "-" },
  { label: "授权失败", value: output.value.fill_error_count ?? 0 },
]);

const stages = computed<Stage[]>(() => {
  const inviteJob = objectValue(output.value.invite_job);
  const syncAfterInvite = objectValue(output.value.sync_after_invite);
  const finalSync = objectValue(output.value.final_sync);
  const authorizedIds = arrayValue(output.value.authorized_credential_ids);
  const fillErrors = arrayValue(output.value.fill_errors);
  const jobStatus = selectedJob.value?.job_status || "unknown";
  return [
    {
      key: "created",
      title: "1. 创建自动化任务",
      status: jobStatus === "failed" ? "failed" : "succeeded",
      description: "记录本次选择空间、账号池和自动化参数。",
      metrics: [
        { label: "账号数", value: inputListCount("user_account_ids") },
        { label: "邀请并发", value: input.value.invite_concurrency ?? "-" },
        { label: "等待秒", value: input.value.post_invite_wait_seconds ?? "-" },
      ],
      detail: input.value,
    },
    {
      key: "invite",
      title: "2. 批量发送邀请",
      status: statusFromCounts(inviteJob),
      description: "复用现有 membership.invite_member.bulk，同步屏障仍在实际请求前生效。",
      metrics: [
        { label: "Work", value: inviteJob.work_count ?? 0 },
        { label: "成功", value: inviteJob.succeeded ?? 0 },
        { label: "失败", value: inviteJob.failed ?? 0 },
        { label: "并发", value: inviteJob.concurrency ?? "-" },
      ],
      detail: inviteJob,
      jobId: String(inviteJob.job_id || ""),
    },
    {
      key: "sync_after_invite",
      title: "3. 邀请后远端同步",
      status: syncAfterInvite.remote_member_count === undefined ? "pending" : "succeeded",
      description: "读取远端成员和待处理邀请，剔除本地不存在于远端的数据。",
      metrics: [
        { label: "远端成员", value: syncAfterInvite.remote_member_count ?? 0 },
        { label: "远端邀请", value: syncAfterInvite.remote_invite_count ?? 0 },
        { label: "本地剔除", value: syncAfterInvite.removed_local_count ?? 0 },
      ],
      detail: syncAfterInvite,
    },
    {
      key: "codex_fill",
      title: "4. 空间锁定并生成 1 个 Codex 授权",
      status: fillErrors.length > 0 ? "partial_success" : authorizedIds.length > 0 ? "succeeded" : "pending",
      description: "同一个空间一次只随机选择一个账号操作；授权成功后标记 pending_push。",
      metrics: [
        { label: "操作账号", value: output.value.selected_user_account_id || output.value.current_user_account_id || "-" },
        { label: "授权 ID", value: output.value.authorized_credential_id || "-" },
        { label: "失败", value: fillErrors.length },
      ],
      detail: {
        selected_user_account_id: output.value.selected_user_account_id || output.value.current_user_account_id || "",
        authorized_credential_id: output.value.authorized_credential_id || "",
        authorized_credential_ids: authorizedIds,
        fill_errors: fillErrors,
      },
    },
    {
      key: "final_sync",
      title: "5. 最终远端同步",
      status: finalSync.remote_member_count === undefined ? "pending" : "succeeded",
      description: "授权后再次读取远端状态，更新空间使用人数。",
      metrics: [
        { label: "远端成员", value: finalSync.remote_member_count ?? 0 },
        { label: "远端邀请", value: finalSync.remote_invite_count ?? 0 },
        { label: "本地剔除", value: finalSync.removed_local_count ?? 0 },
      ],
      detail: finalSync,
    },
  ];
});

const recentErrors = computed(() =>
  events.value.filter((event) => event.level === "ERROR").slice(-8).reverse(),
);

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function inputListCount(key: string) {
  return arrayValue(input.value[key]).length;
}

function statusFromCounts(value: Record<string, unknown>) {
  const workCount = Number(value.work_count ?? 0);
  const failed = Number(value.failed ?? 0);
  const succeeded = Number(value.succeeded ?? 0);
  if (!workCount) return "pending";
  if (failed > 0 && succeeded > 0) return "partial_success";
  if (failed > 0) return "failed";
  return "succeeded";
}

async function loadJobs() {
  jobs.value = await listJobs();
  if (!selectedJobId.value) {
    selectedJobId.value =
      String(route.query.jobId || "") || String(automationJobs.value[0]?.id || "");
  }
}

async function loadSelectedJob() {
  if (!selectedJobId.value) return;
  loading.value = true;
  error.value = "";
  try {
    selectedJob.value = await getJob(selectedJobId.value);
    [runs.value, workItems.value] = await Promise.all([
      listRuns(selectedJobId.value),
      listWorkItems(selectedJobId.value),
    ]);
    const runId = runs.value[0]?.id || "";
    events.value = runId ? await listEvents(runId) : [];
  } catch (err) {
    error.value = String((err as Error).message ?? err);
  } finally {
    loading.value = false;
  }
}

async function loadAll() {
  await loadJobs();
  await loadSelectedJob();
}

watch(selectedJobId, async (value) => {
  if (!value) return;
  await router.replace({ name: "automation-flow", query: { jobId: value } });
  await loadSelectedJob();
});

onMounted(() => {
  void loadAll();
  pollTimer = window.setInterval(() => {
    if (!loading.value && isLive.value) void loadSelectedJob();
  }, 2500);
});

onBeforeUnmount(() => {
  if (pollTimer) window.clearInterval(pollTimer);
});
</script>

<template>
  <PageHeader title="自动化流水" description="把一次空间自动化的邀请、同步、授权、待推送状态串起来看。">
    <select v-model="selectedJobId" class="select job-select">
      <option value="">选择自动化任务</option>
      <option v-for="jobItem in automationJobs" :key="jobItem.id" :value="jobItem.id">
        {{ jobItem.created_at }} / {{ jobItem.type }} / {{ jobItem.id }}
      </option>
    </select>
    <button class="btn primary" :disabled="loading" @click="loadAll">
      {{ loading ? "刷新中..." : "刷新" }}
    </button>
  </PageHeader>

  <section v-if="selectedJob" class="overview panel">
    <div class="job-title">
      <span>当前任务</span>
      <strong>{{ selectedJob.id }}</strong>
      <StatusBadge :value="selectedJob.job_status" />
    </div>
    <div v-for="card in summaryCards" :key="card.label" class="metric-card">
      <span>{{ card.label }}</span>
      <strong>{{ card.value }}</strong>
    </div>
  </section>

  <section v-if="error" class="panel error-panel">
    {{ error }}
  </section>

  <section v-if="!selectedJob && !loading" class="panel empty-panel">
    <h2>还没有可展示的自动化流水</h2>
    <p>先到空间成员页面选中同一空间的成员，点击“启动空间自动化”，完成后会自动跳到这里。</p>
    <RouterLink class="btn primary" :to="{ name: 'memberships' }">去空间成员启动</RouterLink>
  </section>

  <section v-if="selectedJob" class="flow-grid">
    <article v-for="stage in stages" :key="stage.key" class="stage-card panel">
      <div class="stage-head">
        <div>
          <h2>{{ stage.title }}</h2>
          <p>{{ stage.description }}</p>
        </div>
        <StatusBadge :value="stage.status" />
      </div>
      <div class="stage-metrics">
        <div v-for="metric in stage.metrics" :key="metric.label">
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}</strong>
        </div>
      </div>
      <div v-if="stage.jobId" class="stage-link">
        <RouterLink :to="{ name: 'job-trace', params: { jobId: stage.jobId } }">
          查看邀请子任务 {{ stage.jobId }}
        </RouterLink>
      </div>
      <JsonBlock :title="`${stage.title} 详情`" :value="stage.detail || {}" collapsed />
    </article>
  </section>

  <section v-if="selectedJob" class="lower-grid">
    <article class="panel">
      <div class="section-head">
        <h2>Work 状态</h2>
        <span>{{ workItems.length }} 条</span>
      </div>
      <div class="work-status-strip">
        <div v-for="status in ['queued', 'running', 'succeeded', 'failed', 'cancelled']" :key="status">
          <StatusBadge :value="status" />
          <strong>{{ workItems.filter((item) => item.work_status === status).length }}</strong>
        </div>
      </div>
    </article>

    <article class="panel">
      <div class="section-head">
        <h2>错误事件</h2>
        <span>{{ recentErrors.length }} 条</span>
      </div>
      <div v-if="recentErrors.length" class="error-list">
        <div v-for="event in recentErrors" :key="event.id" class="error-row">
          <strong>{{ event.event_type }}</strong>
          <span>{{ event.message }}</span>
          <small>{{ event.ts }}</small>
        </div>
      </div>
      <p v-else class="empty-text">暂无 ERROR 事件。</p>
    </article>
  </section>

  <JsonBlock v-if="selectedJob" title="自动化任务完整输出" :value="output" collapsed />
</template>

<style scoped>
.job-select {
  min-width: min(680px, 100%);
}

.overview {
  align-items: stretch;
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(320px, 2fr) repeat(7, minmax(120px, 1fr));
  margin-bottom: 18px;
  padding: 14px;
}

.job-title,
.metric-card {
  background: rgba(15, 23, 42, 0.42);
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 16px;
  min-width: 0;
  padding: 14px;
}

.job-title {
  display: grid;
  gap: 8px;
}

.job-title span,
.metric-card span {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 900;
}

.job-title strong,
.metric-card strong {
  overflow-wrap: anywhere;
}

.metric-card strong {
  display: block;
  font-size: 24px;
  letter-spacing: -0.03em;
  margin-top: 8px;
}

.flow-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(5, minmax(240px, 1fr));
  margin-bottom: 18px;
}

.stage-card {
  min-width: 0;
  overflow: hidden;
  padding: 0;
}

.stage-head {
  border-bottom: 1px solid var(--border);
  display: grid;
  gap: 12px;
  padding: 14px;
}

.stage-head h2,
.section-head h2 {
  font-size: 14px;
  margin: 0;
}

.stage-head p {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.45;
  margin: 6px 0 0;
}

.stage-metrics {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  padding: 14px;
}

.stage-metrics div {
  background: rgba(30, 41, 59, 0.45);
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 12px;
  padding: 10px;
}

.stage-metrics span {
  color: var(--text-muted);
  display: block;
  font-size: 11px;
  font-weight: 900;
  margin-bottom: 5px;
}

.stage-link {
  border-top: 1px solid var(--border);
  padding: 12px 14px;
}

.stage-link a {
  color: #93c5fd;
  font-size: 12px;
  font-weight: 900;
  overflow-wrap: anywhere;
}

.lower-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: 1fr 1fr;
  margin-bottom: 18px;
}

.lower-grid .panel,
.error-panel,
.empty-panel {
  padding: 14px;
}

.empty-panel {
  display: grid;
  gap: 12px;
  justify-items: start;
}

.empty-panel h2 {
  font-size: 18px;
  margin: 0;
}

.empty-panel p {
  color: var(--text-muted);
  margin: 0;
}

.section-head {
  align-items: center;
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-head span,
.empty-text {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 800;
}

.work-status-strip {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.work-status-strip div {
  background: rgba(15, 23, 42, 0.38);
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 14px;
  display: grid;
  gap: 9px;
  justify-items: start;
  padding: 12px;
}

.error-list {
  display: grid;
  gap: 9px;
}

.error-row {
  background: rgba(127, 29, 29, 0.18);
  border: 1px solid rgba(248, 113, 113, 0.2);
  border-radius: 12px;
  display: grid;
  gap: 5px;
  padding: 10px 12px;
}

.error-row span,
.error-row small {
  color: var(--text-muted);
  overflow-wrap: anywhere;
}

@media (max-width: 1280px) {
  .overview,
  .flow-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 767px) {
  .overview,
  .flow-grid,
  .lower-grid,
  .work-status-strip {
    grid-template-columns: 1fr;
  }
}
</style>
