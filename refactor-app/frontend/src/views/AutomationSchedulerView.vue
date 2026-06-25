<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";

import JsonBlock from "../components/JsonBlock.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { resourcesApi, type Row } from "../api/resources";

const schedules = ref<Row[]>([]);
const loading = ref(false);
const savingId = ref("");
const error = ref("");
let pollTimer: number | undefined;

const labels: Record<string, { title: string; desc: string }> = {
  "automation.workspace_invite_sync": {
    title: "空间邀请同步",
    desc: "扫描可用空间，发送 350 邀请，2 分钟后同步远端成员和待处理邀请，并剔除本地不存在成员。",
  },
  "automation.workspace_authorize": {
    title: "空间授权",
    desc: "扫描席位未满的空间，拿 workspace 锁，随机授权 1 个账号，生成 pending_push 凭证。",
  },
  "automation.downstream_push": {
    title: "下游推送",
    desc: "扫描所有下游渠道，未达到推送上限时推送 pending_push 凭证。",
  },
  "automation.downstream_usage_cleanup": {
    title: "用量清理",
    desc: "扫描已推送记录，达到阈值后本地结算并创建远端释放任务。",
  },
  "automation.remote_member_release": {
    title: "远端成员释放",
    desc: "扫描待释放远端成员任务，删除并复查远端成员，直到确认不存在。",
  },
};

const sortedSchedules = computed(() =>
  [...schedules.value].sort((a, b) =>
    String(a.schedule_type || "").localeCompare(String(b.schedule_type || "")),
  ),
);

function labelOf(type: unknown) {
  return labels[String(type)]?.title || String(type || "");
}

function descOf(type: unknown) {
  return labels[String(type)]?.desc || "";
}

function configSummary(value: unknown) {
  const obj = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  return Object.entries(obj)
    .slice(0, 4)
    .map(([key, item]) => `${key}=${String(item)}`)
    .join(" / ");
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    schedules.value = await resourcesApi.automationSchedules();
  } catch (err) {
    error.value = String((err as Error).message ?? err);
  } finally {
    loading.value = false;
  }
}

async function toggleSchedule(row: Row) {
  const id = String(row.id || "");
  if (!id) return;
  savingId.value = id;
  try {
    await resourcesApi.patchAutomationSchedule(id, { enabled: !Boolean(row.enabled) });
    await load();
  } catch (err) {
    error.value = String((err as Error).message ?? err);
  } finally {
    savingId.value = "";
  }
}

async function runNow(row: Row) {
  const id = String(row.id || "");
  if (!id) return;
  savingId.value = `run:${id}`;
  try {
    await resourcesApi.runAutomationScheduleNow(id);
    await load();
  } catch (err) {
    error.value = String((err as Error).message ?? err);
  } finally {
    savingId.value = "";
  }
}

onMounted(() => {
  void load();
  pollTimer = window.setInterval(() => void load(), 5000);
});

onBeforeUnmount(() => {
  if (pollTimer) window.clearInterval(pollTimer);
});
</script>

<template>
  <PageHeader title="自动化调度" description="配置长期 Job 的定时触发、参数和最近运行状态。">
    <button class="btn" :disabled="loading" @click="load">
      {{ loading ? "刷新中..." : "刷新" }}
    </button>
  </PageHeader>

  <section v-if="error" class="panel error-panel">{{ error }}</section>

  <section class="schedule-grid">
    <article v-for="row in sortedSchedules" :key="String(row.id)" class="panel schedule-card">
      <div class="card-head">
        <div>
          <h2>{{ labelOf(row.schedule_type) }}</h2>
          <p>{{ descOf(row.schedule_type) }}</p>
        </div>
        <StatusBadge :value="row.enabled ? row.schedule_status || 'active' : 'paused'" />
      </div>

      <div class="metric-row">
        <div>
          <span>间隔</span>
          <strong>{{ row.interval_seconds }}s</strong>
        </div>
        <div>
          <span>上次运行</span>
          <strong>{{ row.last_run_at || "-" }}</strong>
        </div>
        <div>
          <span>下次运行</span>
          <strong>{{ row.next_run_at || "-" }}</strong>
        </div>
      </div>

      <div class="summary-line">
        <span>配置</span>
        <code>{{ configSummary(row.config_json) || "{}" }}</code>
      </div>

      <div class="summary-line">
        <span>最近 Job</span>
        <RouterLink
          v-if="row.last_job_id"
          :to="{ name: 'job-trace', params: { jobId: String(row.last_job_id) } }"
        >
          {{ row.last_job_id }}
        </RouterLink>
        <code v-else>-</code>
      </div>

      <div v-if="row.last_error_message" class="error-box">
        {{ row.last_error_code }} / {{ row.last_error_message }}
      </div>

      <details>
        <summary>查看完整配置</summary>
        <JsonBlock :value="row.config_json" />
      </details>

      <div class="actions card-actions">
        <button class="btn" :disabled="savingId === String(row.id)" @click="toggleSchedule(row)">
          {{ row.enabled ? "暂停" : "启用" }}
        </button>
        <button class="btn primary" :disabled="savingId === `run:${row.id}`" @click="runNow(row)">
          {{ savingId === `run:${row.id}` ? "运行中..." : "立即运行一次" }}
        </button>
      </div>
    </article>
  </section>
</template>

<style scoped>
.error-panel {
  border-color: rgba(239, 68, 68, 0.35);
  color: #fecaca;
  margin-bottom: 16px;
  padding: 14px;
}

h2,
p {
  margin: 0;
}

h2 {
  font-size: 17px;
}

p {
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.5;
  margin-top: 6px;
}

.schedule-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 520px), 1fr));
}

.schedule-card {
  display: grid;
  gap: 14px;
  padding: 18px;
}

.card-head {
  align-items: flex-start;
  display: flex;
  gap: 16px;
  justify-content: space-between;
}

.metric-row {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.metric-row div {
  background: rgba(8, 13, 25, 0.42);
  border: 1px solid rgba(38, 50, 73, 0.72);
  border-radius: 12px;
  min-width: 0;
  padding: 10px;
}

.metric-row span,
.summary-line span {
  color: var(--text-muted);
  display: block;
  font-size: 12px;
  font-weight: 800;
  margin-bottom: 5px;
}

.metric-row strong,
.summary-line code,
.summary-line a {
  color: var(--text-primary);
  display: block;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-line {
  min-width: 0;
}

.summary-line a {
  color: #93c5fd;
}

.error-box {
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 12px;
  color: #fecaca;
  font-size: 12px;
  padding: 10px;
}

details {
  color: var(--text-muted);
  font-size: 13px;
}

summary {
  cursor: pointer;
  font-weight: 800;
  margin-bottom: 10px;
}

.card-actions {
  justify-content: flex-end;
}

@media (max-width: 760px) {
  .create-grid,
  .metric-row {
    grid-template-columns: 1fr;
  }

  .card-head {
    display: grid;
  }
}
</style>
