<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";

import DataTable, { type Column } from "../components/DataTable.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { resourcesApi, type Row } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();

const jobs = ref<Row[]>([]);
const jobRuns = ref<Row[]>([]);
const channels = ref<Row[]>([]);
const usageItems = ref<Row[]>([]);
const usageSummary = ref<Row>({});
const consoleItems = ref<Row[]>([]);
const selectedUsageRows = ref<Row[]>([]);
const loading = ref(false);
const consoleLoading = ref(false);
const runsLoading = ref(false);
const usageLoading = ref(false);
const runningScheduleId = ref("");
const error = ref("");
const usageError = ref("");
const consoleError = ref("");
const selectedScheduleType = ref("");
const selectedJobId = ref("");
const selectedRunId = ref("");
const logLevel = ref("");
const logLimit = ref(1000);
const logMaxBytes = ref(524288);
const runLimit = ref(100);
const autoRefresh = ref(true);
const usageChannelId = ref("");
const usageStatus = ref("");
const usageProvider = ref("");
const usageQuery = ref("");
const usageLimit = ref(500);
const probeLimit = ref(100);
const probeConcurrency = ref(5);
const probing = ref(false);
const initializedDefaultJob = ref(false);
let pollTimer: number | undefined;

const jobLabels: Record<string, string> = {
  "automation.workspace_invite_sync": "空间邀请同步",
  "automation.workspace_authorize": "空间授权",
  "automation.codex_heartbeat": "Codex 心跳",
  "automation.downstream_push": "下游推送",
  "automation.downstream_usage_cleanup": "额度清理",
  "automation.remote_member_release": "远端成员释放",
};

const usageColumns: Column[] = [
  { key: "email", label: "账号邮箱", summary: 26 },
  { key: "workspace_name", label: "空间", summary: 22 },
  { key: "downstream_channel_name", label: "渠道" },
  { key: "downstream_provider", label: "类型", badge: true },
  { key: "push_status", label: "推送", badge: true },
  { key: "usage_percent", label: "使用率" },
  { key: "usage_status", label: "额度状态", badge: true },
  { key: "last_usage_check_at", label: "最近查询", summary: 24 },
  { key: "error_code", label: "错误码", badge: true },
];

const runColumns: Column[] = [
  { key: "started_at", label: "开始时间", summary: 24 },
  { key: "run_status", label: "运行状态", badge: true },
  { key: "duration_ms", label: "耗时 ms" },
  { key: "item_count", label: "总数" },
  { key: "succeeded", label: "成功" },
  { key: "failed", label: "失败" },
  { key: "skipped", label: "跳过" },
  { key: "event_count", label: "事件" },
  { key: "error_code", label: "错误码", badge: true },
];

const sortedJobs = computed(() =>
  [...jobs.value].sort((a, b) =>
    String(a.schedule_type || "").localeCompare(String(b.schedule_type || "")),
  ),
);

const selectedJobOptions = computed(() =>
  jobs.value
    .filter((row) => !selectedScheduleType.value || row.schedule_type === selectedScheduleType.value)
    .filter((row) => row.last_job_id)
    .map((row) => ({
      label: `${labelOf(row.schedule_type)} / ${shortText(row.last_job_id, 18)}`,
      jobId: String(row.last_job_id || ""),
      runId: String(row.last_run_id || ""),
    })),
);

const consoleLines = computed(() =>
  consoleItems.value.map((item) => {
    const level = String(item.level || "INFO");
    const line = [
      `[${item.ts || ""}]`,
      level.padEnd(5, " "),
      String(item.event_type || "").padEnd(34, " "),
      String(item.message || ""),
      item.data_summary ? ` ${item.data_summary}` : "",
    ].join(" ");
    return { ...item, level, line };
  }),
);

const selectedRun = computed(() => jobRuns.value.find((row) => row.run_id === selectedRunId.value));

function labelOf(value: unknown) {
  return jobLabels[String(value || "")] || String(value || "");
}

function shortText(value: unknown, size = 16) {
  const text = String(value || "");
  if (text.length <= size) return text || "-";
  const head = Math.max(6, Math.floor(size * 0.58));
  return `${text.slice(0, head)}…${text.slice(-(size - head - 1))}`;
}

function durationText(ms: unknown) {
  const value = Number(ms || 0);
  if (!value) return "-";
  if (value < 1000) return `${value}ms`;
  return `${(value / 1000).toFixed(1)}s`;
}

function bytesText(value: unknown) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)}MB`;
}

function usageTone(value: unknown) {
  const num = Number(value || 0);
  if (num >= 95) return "danger";
  if (num >= 80) return "warning";
  return "success";
}

function selectJob(row: Row) {
  selectedScheduleType.value = String(row.schedule_type || "");
  selectedJobId.value = String(row.last_job_id || "");
  selectedRunId.value = String(row.last_run_id || "");
  void loadRuns().then(loadConsole);
}

async function loadJobs() {
  const result = await resourcesApi.automationMonitorJobs();
  jobs.value = result.items || [];
  if (!initializedDefaultJob.value && !selectedScheduleType.value && jobs.value[0]) {
    initializedDefaultJob.value = true;
    selectJob(jobs.value[0]);
  }
}

async function loadConsole() {
  consoleLoading.value = true;
  consoleError.value = "";
  try {
    const result = await resourcesApi.automationMonitorConsole({
      schedule_type: selectedScheduleType.value,
      job_id: selectedJobId.value,
      run_id: selectedRunId.value,
      level: logLevel.value,
      limit: logLimit.value,
      max_bytes: logMaxBytes.value,
    });
    consoleItems.value = result.items || [];
  } catch (err) {
    consoleError.value = String((err as Error).message ?? err);
  } finally {
    consoleLoading.value = false;
  }
}

async function loadRuns() {
  runsLoading.value = true;
  try {
    const result = await resourcesApi.automationMonitorJobRuns({
      schedule_type: selectedScheduleType.value,
      limit: runLimit.value,
    });
    jobRuns.value = result.items || [];
    if (selectedRunId.value && !jobRuns.value.some((row) => row.run_id === selectedRunId.value)) {
      selectedRunId.value = "";
      selectedJobId.value = "";
    }
  } finally {
    runsLoading.value = false;
  }
}

async function loadUsage() {
  usageLoading.value = true;
  usageError.value = "";
  try {
    const result = await resourcesApi.automationMonitorDownstreamUsage({
      downstream_channel_id: usageChannelId.value,
      usage_status: usageStatus.value,
      provider_type: usageProvider.value,
      q: usageQuery.value,
      limit: usageLimit.value,
    });
    usageItems.value = result.items || [];
    usageSummary.value = result.summary || {};
  } catch (err) {
    usageError.value = String((err as Error).message ?? err);
  } finally {
    usageLoading.value = false;
  }
}

async function loadChannels() {
  channels.value = await resourcesApi.downstreamChannels();
}

async function loadAll() {
  loading.value = true;
  error.value = "";
  try {
    await Promise.all([loadJobs(), loadChannels(), loadUsage()]);
    await loadRuns();
    await loadConsole();
  } catch (err) {
    error.value = String((err as Error).message ?? err);
  } finally {
    loading.value = false;
  }
}

async function runNow(row: Row) {
  const id = String(row.id || "");
  if (!id || runningScheduleId.value) return;
  runningScheduleId.value = id;
  try {
    await resourcesApi.runAutomationScheduleNow(id);
    store.toast("已触发调度", labelOf(row.schedule_type), "success");
    await loadJobs();
    const updated = jobs.value.find((item) => item.id === id);
    if (updated) selectJob(updated);
  } catch (err) {
    store.toast("触发调度失败", String((err as Error).message ?? err), "error");
  } finally {
    runningScheduleId.value = "";
  }
}

async function probeUsage(selectedOnly = false) {
  const ids = selectedOnly
    ? selectedUsageRows.value.map((row) => String(row.id || "")).filter(Boolean)
    : [];
  if (selectedOnly && !ids.length) {
    store.toast("没有选中记录", "请先勾选要查询额度的推送记录。", "warning");
    return;
  }
  probing.value = true;
  try {
    const result = await resourcesApi.automationMonitorDownstreamUsageProbe({
      downstream_push_record_ids: ids,
      downstream_channel_id: selectedOnly ? "" : usageChannelId.value,
      limit: selectedOnly ? ids.length : probeLimit.value,
      concurrency: probeConcurrency.value,
      threshold_percent: 95,
      persist_result: true,
    });
    store.toast(
      "额度查询完成",
      `检查=${result.checked ?? 0} 成功=${result.succeeded ?? 0} 失败=${result.failed ?? 0}`,
      Number(result.failed || 0) > 0 ? "warning" : "success",
    );
    await loadUsage();
  } catch (err) {
    store.toast("额度查询失败", String((err as Error).message ?? err), "error");
  } finally {
    probing.value = false;
  }
}

function onJobSelectChange() {
  const option = selectedJobOptions.value.find((item) => item.jobId === selectedJobId.value);
  selectedRunId.value = option?.runId || "";
  void loadConsole();
}

function onScheduleTypeChange() {
  selectedJobId.value = "";
  selectedRunId.value = "";
  void loadRuns().then(loadConsole);
}

function selectRun(row: Row) {
  selectedJobId.value = String(row.job_id || "");
  selectedRunId.value = String(row.run_id || "");
  void loadConsole();
}

onMounted(() => {
  void loadAll();
  pollTimer = window.setInterval(() => {
    if (!autoRefresh.value || loading.value || consoleLoading.value) return;
    void loadJobs();
    void loadRuns();
    void loadConsole();
  }, 5000);
});

onBeforeUnmount(() => {
  if (pollTimer) window.clearInterval(pollTimer);
});
</script>

<template>
  <PageHeader title="自动化监控" description="五个长期 Job 的运行态、控制台日志，以及已推送凭证的额度使用情况。">
    <button class="btn" :disabled="loading" @click="loadAll">{{ loading ? "刷新中..." : "刷新全部" }}</button>
  </PageHeader>

  <section v-if="error" class="panel error-panel">{{ error }}</section>

  <section class="monitor-section">
    <div class="section-title">
      <div>
        <h2>五个 Job 执行情况</h2>
        <p>点击卡片会把下面控制台切换到该 Job 的最近一次运行。</p>
      </div>
    </div>
    <div class="job-grid">
      <article
        v-for="row in sortedJobs"
	        :key="String(row.id)"
	        class="panel job-card"
	        :class="{ selected: selectedScheduleType === row.schedule_type }"
	        @click="selectJob(row)"
	      >
        <div class="job-head">
          <div>
            <h3>{{ labelOf(row.schedule_type) }}</h3>
            <small>{{ row.schedule_type }}</small>
          </div>
          <StatusBadge :value="row.enabled ? row.schedule_status || 'active' : 'paused'" />
        </div>
        <div class="job-status-row">
          <StatusBadge :value="row.last_job_status || row.last_run_status || 'unknown'" />
          <span>耗时 {{ durationText(row.duration_ms) }}</span>
        </div>
        <dl class="job-metrics">
          <div><dt>成功</dt><dd>{{ row.succeeded ?? 0 }}</dd></div>
          <div><dt>失败</dt><dd>{{ row.failed ?? 0 }}</dd></div>
          <div><dt>跳过</dt><dd>{{ row.skipped ?? 0 }}</dd></div>
        </dl>
        <div class="job-meta">
          <span>Job</span>
          <RouterLink
            v-if="row.last_job_id"
            :to="{ name: 'job-trace', params: { jobId: String(row.last_job_id) } }"
            @click.stop
          >
            {{ shortText(row.last_job_id, 24) }}
          </RouterLink>
          <code v-else>-</code>
        </div>
        <div class="job-meta">
          <span>下次</span>
          <code>{{ row.next_run_at || "-" }}</code>
        </div>
        <button class="btn primary" :disabled="runningScheduleId === row.id" @click.stop="runNow(row)">
          {{ runningScheduleId === row.id ? "执行中..." : "立即运行" }}
        </button>
      </article>
    </div>

    <section class="panel runs-panel">
      <div class="runs-toolbar">
        <div>
          <h3>执行记录</h3>
          <p>点击某一次执行，下面日志只展示该 run 的完整摘要、失败项和事件。</p>
        </div>
        <label class="inline-control">
          <span>记录数</span>
          <input v-model.number="runLimit" class="input small-input" type="number" min="1" max="500" />
        </label>
        <button class="btn" :disabled="runsLoading" @click="loadRuns">
          {{ runsLoading ? "加载中..." : "刷新执行记录" }}
        </button>
      </div>
      <DataTable
        :columns="runColumns"
        :rows="jobRuns"
        :loading="runsLoading"
        empty-text="暂无执行记录。"
        @refresh="loadRuns"
      >
        <template #actions="{ row }">
          <button class="btn tiny" :class="{ primary: row.run_id === selectedRunId }" @click="selectRun(row)">
            查看日志
          </button>
        </template>
      </DataTable>
      <div v-if="selectedRun" class="run-detail">
        <strong>当前 Run：</strong>
        <code>{{ selectedRun.run_id }}</code>
        <span>{{ selectedRun.run_status }}</span>
        <span>失败 {{ selectedRun.failed ?? 0 }}</span>
        <span v-if="selectedRun.error_message">错误：{{ selectedRun.error_message }}</span>
      </div>
    </section>

    <section class="panel console-panel">
      <div class="console-toolbar">
        <label class="filter-field">
          <span>Job 类型</span>
          <select v-model="selectedScheduleType" class="select" @change="onScheduleTypeChange">
            <option value="">全部</option>
            <option v-for="row in sortedJobs" :key="String(row.schedule_type)" :value="String(row.schedule_type)">
              {{ labelOf(row.schedule_type) }}
            </option>
          </select>
        </label>
        <label class="filter-field">
          <span>最近 Job</span>
          <select v-model="selectedJobId" class="select" @change="onJobSelectChange">
            <option value="">全部</option>
            <option v-for="item in selectedJobOptions" :key="item.jobId" :value="item.jobId">
              {{ item.label }}
            </option>
          </select>
        </label>
        <label class="filter-field compact">
          <span>级别</span>
          <select v-model="logLevel" class="select" @change="loadConsole">
            <option value="">ALL</option>
            <option value="INFO">INFO</option>
            <option value="WARN">WARN</option>
            <option value="ERROR">ERROR</option>
            <option value="DEBUG">DEBUG</option>
          </select>
        </label>
        <label class="filter-field compact">
          <span>最大行数</span>
          <input v-model.number="logLimit" class="input" type="number" min="1" max="5000" />
        </label>
        <label class="filter-field compact">
          <span>最大字节</span>
          <input v-model.number="logMaxBytes" class="input" type="number" min="4096" max="2097152" />
        </label>
        <label class="inline-control auto-refresh">
          <input v-model="autoRefresh" type="checkbox" />
          <span>自动刷新</span>
        </label>
        <button class="btn" :disabled="consoleLoading" @click="loadConsole">
          {{ consoleLoading ? "加载中..." : "刷新日志" }}
        </button>
      </div>
      <div class="console-size">
        <span>{{ consoleItems.length }} 行</span>
        <span>最大 {{ bytesText(logMaxBytes) }}</span>
        <span v-if="selectedRunId">Run {{ shortText(selectedRunId, 24) }}</span>
      </div>
      <div v-if="consoleError" class="console-error">{{ consoleError }}</div>
      <pre class="console-output"><code v-for="item in consoleLines" :key="String(item.id)" :class="item.level.toLowerCase()">{{ item.line }}
</code></pre>
    </section>
  </section>

  <section class="monitor-section">
    <div class="section-title">
      <div>
        <h2>推送凭证额度使用情况</h2>
        <p>这里只查询额度并回写查询结果，不执行远端剔除、不删除本地成员。</p>
      </div>
    </div>
    <div class="usage-summary-grid">
      <article class="panel summary-card"><span>已推送凭证</span><strong>{{ usageSummary.total ?? 0 }}</strong></article>
      <article class="panel summary-card"><span>低于 80%</span><strong>{{ usageSummary.below_80 ?? 0 }}</strong></article>
      <article class="panel summary-card warning"><span>80% - 94%</span><strong>{{ usageSummary.between_80_94 ?? 0 }}</strong></article>
      <article class="panel summary-card danger"><span>>= 95%</span><strong>{{ usageSummary.gte_95 ?? 0 }}</strong></article>
      <article class="panel summary-card"><span>查询失败</span><strong>{{ usageSummary.check_failed ?? 0 }}</strong></article>
    </div>

    <section class="panel usage-actions">
      <div class="filter-grid">
        <label class="filter-field">
          <span>渠道</span>
          <select v-model="usageChannelId" class="select">
            <option value="">全部渠道</option>
            <option v-for="channel in channels" :key="String(channel.id)" :value="String(channel.id)">
              {{ channel.provider_type }} / {{ channel.name }}
            </option>
          </select>
        </label>
        <label class="filter-field">
          <span>下游类型</span>
          <select v-model="usageProvider" class="select">
            <option value="">全部</option>
            <option value="cpa">cpa</option>
            <option value="sub2api">sub2api</option>
          </select>
        </label>
        <label class="filter-field">
          <span>额度状态</span>
          <select v-model="usageStatus" class="select">
            <option value="">全部</option>
            <option value="unknown">unknown</option>
            <option value="active">active</option>
            <option value="near_limit">near_limit</option>
            <option value="check_failed">check_failed</option>
            <option value="used">used</option>
          </select>
        </label>
        <label class="filter-field">
          <span>关键词</span>
          <input v-model="usageQuery" class="input" placeholder="邮箱 / 空间 / 凭证 / 错误码" />
        </label>
        <label class="filter-field compact">
          <span>展示数量</span>
          <input v-model.number="usageLimit" class="input" type="number" min="1" max="2000" />
        </label>
        <div class="filter-actions">
          <button class="btn" :disabled="usageLoading" @click="loadUsage">
            {{ usageLoading ? "筛选中..." : "筛选" }}
          </button>
        </div>
      </div>
      <div class="probe-row">
        <label class="inline-control">
          <span>查询数量</span>
          <input v-model.number="probeLimit" class="input small-input" type="number" min="1" max="1000" />
        </label>
        <label class="inline-control">
          <span>并发</span>
          <input v-model.number="probeConcurrency" class="input small-input" type="number" min="1" max="100" />
        </label>
        <button class="btn" :disabled="probing" @click="probeUsage(true)">
          查询选中额度（{{ selectedUsageRows.length }}）
        </button>
        <button class="btn primary" :disabled="probing" @click="probeUsage(false)">
          {{ probing ? "查询中..." : "查询当前筛选额度" }}
        </button>
      </div>
    </section>

    <DataTable
      :columns="usageColumns"
      :rows="usageItems"
      :loading="usageLoading"
      :error="usageError"
      selectable
      empty-text="暂无已推送凭证。"
      @selection-change="(rows) => (selectedUsageRows = rows as Row[])"
      @refresh="loadUsage"
    >
      <template #actions="{ row }">
        <div class="usage-cell" :class="usageTone(row.usage_percent)">
          <span>{{ row.usage_percent ?? 0 }}%</span>
          <i :style="{ width: `${Number(row.usage_percent || 0)}%` }"></i>
        </div>
      </template>
    </DataTable>
  </section>
</template>

<style scoped>
.error-panel {
  border-color: rgba(239, 68, 68, 0.35);
  color: #fecaca;
  margin-bottom: 16px;
  padding: 14px;
}

.monitor-section {
  display: grid;
  gap: 14px;
  margin-bottom: 22px;
}

.section-title {
  align-items: end;
  display: flex;
  justify-content: space-between;
}

.section-title h2,
.section-title p,
.job-head h3 {
  margin: 0;
}

.section-title h2 {
  font-size: 20px;
}

.section-title p {
  color: var(--text-muted);
  font-size: 13px;
  margin-top: 6px;
}

.job-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr));
}

.job-card {
  cursor: pointer;
  display: grid;
  gap: 12px;
  padding: 16px;
}

.job-card.selected {
  border-color: rgba(59, 130, 246, 0.78);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.12), var(--shadow);
}

.job-head,
.job-status-row,
.job-meta {
  align-items: center;
  display: flex;
  gap: 10px;
  justify-content: space-between;
  min-width: 0;
}

.job-head h3 {
  font-size: 15px;
}

.job-head small,
.job-status-row span,
.job-meta span {
  color: var(--text-muted);
  font-size: 12px;
}

.job-metrics {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(3, 1fr);
  margin: 0;
}

.job-metrics div {
  background: rgba(8, 13, 25, 0.42);
  border: 1px solid rgba(38, 50, 73, 0.72);
  border-radius: 10px;
  padding: 9px;
}

.job-metrics dt {
  color: var(--text-muted);
  font-size: 11px;
}

.job-metrics dd {
  font-size: 18px;
  font-weight: 900;
  margin: 3px 0 0;
}

.job-meta a,
.job-meta code {
  color: #93c5fd;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.console-panel {
  overflow: hidden;
}

.runs-panel {
  overflow: hidden;
}

.runs-toolbar {
  align-items: center;
  border-bottom: 1px solid var(--border);
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(0, 1fr) auto auto;
  padding: 14px;
}

.runs-toolbar h3,
.runs-toolbar p {
  margin: 0;
}

.runs-toolbar p {
  color: var(--text-muted);
  font-size: 12px;
  margin-top: 4px;
}

.run-detail {
  align-items: center;
  border-top: 1px solid var(--border);
  color: var(--text-muted);
  display: flex;
  flex-wrap: wrap;
  font-size: 12px;
  gap: 10px;
  padding: 10px 14px;
}

.run-detail code {
  color: #93c5fd;
}

.tiny {
  min-height: 32px;
  padding: 6px 10px;
}

.console-toolbar {
  align-items: end;
  border-bottom: 1px solid var(--border);
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(180px, 1.2fr) minmax(190px, 1.3fr) 120px 120px 140px auto auto;
  padding: 14px;
}

.compact {
  min-width: 0;
}

.auto-refresh {
  padding-bottom: 9px;
}

.console-size {
  color: var(--text-muted);
  display: flex;
  font-size: 12px;
  gap: 16px;
  padding: 10px 14px 0;
}

.console-error {
  color: #fca5a5;
  padding: 10px 14px 0;
}

.console-output {
  background: #050816;
  border: 1px solid rgba(38, 50, 73, 0.72);
  border-radius: 14px;
  color: #cbd5e1;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.6;
  margin: 14px;
  max-height: 420px;
  min-height: 260px;
  overflow: auto;
  padding: 14px;
  white-space: pre-wrap;
}

.console-output .error {
  color: #fca5a5;
}

.console-output .warn {
  color: #fcd34d;
}

.console-output .info {
  color: #bfdbfe;
}

.console-output .debug {
  color: #a5b4fc;
}

.usage-summary-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr));
}

.summary-card {
  padding: 15px;
}

.summary-card span {
  color: var(--text-muted);
  display: block;
  font-size: 12px;
  font-weight: 800;
}

.summary-card strong {
  display: block;
  font-size: 28px;
  margin-top: 8px;
}

.summary-card.warning strong {
  color: #fcd34d;
}

.summary-card.danger strong {
  color: #fca5a5;
}

.usage-actions {
  padding: 14px;
}

.probe-row {
  align-items: center;
  border-top: 1px solid var(--border);
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
  padding-top: 14px;
}

.usage-cell {
  background: rgba(8, 13, 25, 0.72);
  border: 1px solid rgba(38, 50, 73, 0.72);
  border-radius: 999px;
  min-width: 110px;
  overflow: hidden;
  padding: 4px 8px;
  position: relative;
}

.usage-cell span {
  font-size: 12px;
  font-weight: 900;
  position: relative;
  z-index: 1;
}

.usage-cell i {
  bottom: 0;
  left: 0;
  opacity: 0.28;
  position: absolute;
  top: 0;
}

.usage-cell.success i {
  background: var(--success);
}

.usage-cell.warning i {
  background: var(--warning);
}

.usage-cell.danger i {
  background: var(--danger);
}

@media (max-width: 1100px) {
  .console-toolbar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 767px) {
  .console-toolbar {
    grid-template-columns: 1fr;
  }

  .probe-row {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
