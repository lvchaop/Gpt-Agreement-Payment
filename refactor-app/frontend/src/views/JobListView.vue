<script setup lang="ts">
import { ExternalLink, Play, RefreshCw, Settings2 } from "@lucide/vue";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { resourcesApi, type Row } from "../api/resources";
import DataTable, { type Column } from "../components/DataTable.vue";
import EntitySelect from "../components/EntitySelect.vue";
import FormDrawer from "../components/FormDrawer.vue";
import PageHeader from "../components/PageHeader.vue";
import { useOpsStore } from "../stores/ops";

type ConfigValue = string | number;
type ConfigField = {
  key: string;
  label: string;
  type: "number" | "text" | "channel" | "space";
  min?: number;
  max?: number;
  required?: boolean;
  spaceType?: "business" | "personal";
};

const router = useRouter();
const store = useOpsStore();
const rows = ref<Row[]>([]);
const loading = ref(false);
const error = ref("");
const changingScheduleId = ref("");
const scheduleTarget = ref<Row | null>(null);
const runTarget = ref<Row | null>(null);
const savingSchedule = ref(false);
const runningNow = ref(false);
const scheduleEnabled = ref(false);
const scheduleInterval = ref(60);
const scheduleConfig = ref<Record<string, ConfigValue>>({});
const runConfig = ref<Record<string, ConfigValue>>({});
let pollTimer: number | undefined;

const definitions: Record<string, { label: string; defaults: Record<string, ConfigValue>; fields: ConfigField[] }> = {
  "automation.space_membership_invite_sync": {
    label: "空间邀请",
    defaults: {
      space_id: "",
      space_limit: 1,
      invite_limit_per_space: 1000,
      work_count: 1000,
      barrier_timeout_s: 30,
    },
    fields: [
      { key: "space_id", label: "Business 空间", type: "space" },
      { key: "barrier_timeout_s", label: "屏障等待秒数", type: "number", min: 1 },
    ],
  },
  "automation.space_membership_invite_dynamic": {
    label: "按席位批量邀请",
    defaults: { space_id: "" },
    fields: [
      { key: "space_id", label: "Business 空间", type: "space" },
    ],
  },
  "automation.space_membership_growth_round": {
    label: "倍增邀请并剔除",
    defaults: { space_id: "", work_count: 16, session_wait_timeout_s: 900 },
    fields: [
      { key: "space_id", label: "Business 空间（必选）", type: "space" },
      { key: "work_count", label: "同时执行 Session Work 数", type: "number", min: 1, max: 16 },
      { key: "session_wait_timeout_s", label: "等待 Session 完成秒数", type: "number", min: 1 },
    ],
  },
  "automation.space_authorize": {
    label: "空间授权",
    defaults: { space_id: "", work_count: 1, credential_name_prefix: "codex" },
    fields: [
      { key: "space_id", label: "Business 空间（必选）", type: "space", required: true },
      { key: "work_count", label: "同时执行 Work 数", type: "number", min: 1, max: 350 },
      { key: "credential_name_prefix", label: "凭证名称前缀", type: "text" },
    ],
  },
  "automation.space_downstream_push": {
    label: "下游推送",
    defaults: { work_count: 5, downstream_channel_id: "" },
    fields: [
      { key: "work_count", label: "同时执行 Work 数", type: "number", min: 1, max: 350 },
      { key: "downstream_channel_id", label: "下游渠道", type: "channel" },
    ],
  },
  "automation.space_recycle_sweep": {
    label: "回收结算",
    defaults: { limit: 100, work_count: 5 },
    fields: [
      { key: "limit", label: "每轮处理上限", type: "number", min: 1 },
      { key: "work_count", label: "同时执行 Work 数", type: "number", min: 1, max: 350 },
    ],
  },
  "automation.space_seat_expand": {
    label: "扩席位",
    defaults: { space_id: "", work_count: 1 },
    fields: [
      { key: "space_id", label: "Business 空间", type: "space" },
      { key: "work_count", label: "同时执行 Work 数", type: "number", min: 1, max: 350 },
    ],
  },
  "automation.space_auto_replenish": {
    label: "自动补号",
    defaults: { space_id: "", work_count: 20 },
    fields: [
      { key: "space_id", label: "Business 空间（留空处理全部已开启空间）", type: "space" },
      { key: "work_count", label: "同时执行 Space Work 数", type: "number", min: 1, max: 350 },
    ],
  },
  "automation.personal_payment_method_bind": {
    label: "个人空间绑卡",
    defaults: { space_id: "", limit: 10, work_count: 1 },
    fields: [
      { key: "space_id", label: "个人空间（留空处理全部待绑定空间）", type: "space", spaceType: "personal" },
      { key: "limit", label: "每轮处理上限", type: "number", min: 1, max: 100 },
      { key: "work_count", label: "同时执行 Work 数", type: "number", min: 1, max: 10 },
    ],
  },
};

const columns: Column[] = [
  { key: "display_name", label: "Job" },
  { key: "schedule_state", label: "调度", badge: true },
  { key: "interval_text", label: "间隔" },
  { key: "config_summary", label: "调度参数", summary: 54 },
  { key: "latest_job_status", label: "最近状态", badge: true },
  { key: "work_summary", label: "成功 / 失败 / 跳过" },
  { key: "next_run_at", label: "下次执行", type: "datetime", relativeTime: true },
  { key: "last_error_message", label: "最近错误", summary: 42 },
];

const scheduleFields = computed(() => fieldsFor(scheduleTarget.value));
const runFields = computed(() => fieldsFor(runTarget.value));

function definitionFor(row: Row | null) {
  return definitions[String(row?.schedule_type || "")];
}

function fieldsFor(row: Row | null) {
  return definitionFor(row)?.fields || [];
}

function effectiveConfig(row: Row) {
  const definition = definitionFor(row);
  const saved = row.config_json && typeof row.config_json === "object"
    ? row.config_json as Record<string, ConfigValue>
    : {};
  return { ...(definition?.defaults || {}), ...saved };
}

function configSummary(value: unknown) {
  if (!value || typeof value !== "object") return "-";
  return Object.entries(value as Record<string, unknown>)
    .map(([key, item]) => `${key}=${String(item || "-")}`)
    .join(" · ");
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const result = await resourcesApi.residentJobs();
    rows.value = result.items.map((row) => ({
      ...row,
      display_name: definitionFor(row)?.label || row.schedule_type,
      schedule_state: row.enabled ? "enabled" : "disabled",
      interval_text: `${row.interval_seconds ?? 0} 秒`,
      config_summary: configSummary(effectiveConfig(row)),
      work_summary: `${row.succeeded ?? 0} / ${row.failed ?? 0} / ${row.skipped ?? 0}`,
    }));
    store.touchRefresh();
  } catch (err) {
    error.value = String((err as Error).message ?? err);
  } finally {
    loading.value = false;
  }
}

async function toggleSchedule(row: Row, event: Event) {
  const id = String(row.id || "");
  if (!id) return;
  const enabled = (event.target as HTMLInputElement).checked;
  changingScheduleId.value = id;
  try {
    await resourcesApi.patchResidentJobSchedule(id, { enabled });
    store.toast(enabled ? "调度已开启" : "调度已关闭", String(row.display_name), "success");
    await load();
  } catch (err) {
    store.toast("调度更新失败", String((err as Error).message ?? err), "error");
    await load();
  } finally {
    changingScheduleId.value = "";
  }
}

function openSchedule(row: Row) {
  scheduleTarget.value = row;
  scheduleEnabled.value = Boolean(row.enabled);
  scheduleInterval.value = Number(row.interval_seconds || 60);
  scheduleConfig.value = effectiveConfig(row);
}

async function saveSchedule() {
  const id = String(scheduleTarget.value?.id || "");
  if (!id) return;
  if (!validateRequiredConfig(scheduleTarget.value, scheduleConfig.value)) return;
  savingSchedule.value = true;
  try {
    await resourcesApi.patchResidentJobSchedule(id, {
      enabled: scheduleEnabled.value,
      interval_seconds: scheduleInterval.value,
      config_json: scheduleConfig.value,
    });
    store.toast("调度配置已保存", String(scheduleTarget.value?.display_name || ""), "success");
    scheduleTarget.value = null;
    await load();
  } catch (err) {
    store.toast("保存失败", String((err as Error).message ?? err), "error");
  } finally {
    savingSchedule.value = false;
  }
}

function openRun(row: Row) {
  runTarget.value = row;
  runConfig.value = effectiveConfig(row);
}

function executionJobIds(result: Row) {
  const ids = new Set<string>();
  if (result.job_id) ids.add(String(result.job_id));
  if (Array.isArray(result.items)) {
    result.items.forEach((item) => {
      if (item && typeof item === "object" && (item as Row).job_id) {
        ids.add(String((item as Row).job_id));
      }
    });
  }
  return [...ids];
}

async function runOnce() {
  const target = runTarget.value;
  const id = String(target?.id || "");
  if (!id) return;
  if (!validateRequiredConfig(target, runConfig.value)) return;
  runningNow.value = true;
  try {
    const result = await resourcesApi.runResidentJobNow(id, {
      config_overrides: runConfig.value,
      created_by: "ops:job-list",
    });
    const jobIds = executionJobIds(result);
    store.toast("已执行一次", `${String(target?.display_name || "Job")} · ${jobIds.length} 个执行 Job`, "success");
    runTarget.value = null;
    await load();
    if (jobIds.length === 1) await router.push(`/jobs/${jobIds[0]}`);
  } catch (err) {
    store.toast("执行失败", String((err as Error).message ?? err), "error");
  } finally {
    runningNow.value = false;
  }
}

async function loadChannels(query: string) {
  return (await resourcesApi.channelOptions(query)).items;
}

async function loadSpaces(query: string, spaceType: "business" | "personal") {
  return (await resourcesApi.spaceOptions(query, spaceType)).items.filter(
    (item) => String(item.status || "") === "active",
  );
}

function entityLoader(field: ConfigField) {
  if (field.type === "space") {
    return (query: string) => loadSpaces(query, field.spaceType || "business");
  }
  return loadChannels;
}

function entityPlaceholder(field: ConfigField) {
  if (field.required) return "请选择 active Business 空间";
  return field.type === "space"
    ? "留空表示全部 active Business 空间"
    : "留空表示全部启用渠道";
}

function validateRequiredConfig(row: Row | null, config: Record<string, ConfigValue>) {
  const missing = fieldsFor(row).find(
    (field) => field.required && !String(config[field.key] || "").trim(),
  );
  if (!missing) return true;
  store.toast("参数不完整", `请选择${missing.label.replace("（必选）", "")}`, "warning");
  return false;
}

onMounted(() => {
  void load();
  pollTimer = window.setInterval(() => {
    if (!loading.value && !scheduleTarget.value && !runTarget.value) void load();
  }, 5000);
});

onBeforeUnmount(() => {
  if (pollTimer) window.clearInterval(pollTimer);
});
</script>

<template>
  <PageHeader title="Job 列表" description="空间邀请、授权、推送、回收、扩席位、自动补号与个人空间绑卡。">
    <button class="icon-btn labeled" @click="load">
      <RefreshCw :size="16" :class="{ spin: loading }" />刷新
    </button>
  </PageHeader>
  <DataTable
    :columns="columns"
    :rows="rows"
    :loading="loading"
    :error="error"
    empty-text="暂无 Job 数据。"
    @refresh="load"
  >
    <template #actions="{ row }">
      <label class="schedule-toggle" :title="row.enabled ? '关闭调度' : '开启调度'">
        <input
          type="checkbox"
          :checked="Boolean(row.enabled)"
          :disabled="changingScheduleId === row.id"
          @change="toggleSchedule(row, $event)"
        />
        <span>{{ row.enabled ? "开" : "关" }}</span>
      </label>
      <button class="icon-btn" title="编辑调度" @click="openSchedule(row)">
        <Settings2 :size="15" />
      </button>
      <button class="icon-btn" title="手动执行一次" @click="openRun(row)">
        <Play :size="15" />
      </button>
      <button
        class="icon-btn"
        title="查看最近日志"
        :disabled="!row.latest_job_id"
        @click="router.push(`/jobs/${row.latest_job_id}`)"
      >
        <ExternalLink :size="15" />
      </button>
    </template>
  </DataTable>

  <FormDrawer
    :open="Boolean(scheduleTarget)"
    title="编辑调度"
    :description="String(scheduleTarget?.display_name || '')"
    submit-text="保存调度"
    :busy="savingSchedule"
    @close="scheduleTarget = null"
    @submit="saveSchedule"
  >
    <section class="drawer-section">
      <label class="check"><input v-model="scheduleEnabled" type="checkbox" /><span>开启定时调度</span></label>
      <label class="field"><span>执行间隔（秒）</span><input v-model.number="scheduleInterval" class="input" type="number" min="5" /></label>
    </section>
    <section class="drawer-section">
      <h3>调度参数</h3>
      <div class="drawer-grid">
        <template v-for="field in scheduleFields" :key="field.key">
          <label v-if="field.type === 'number'" class="field">
            <span>{{ field.label }}</span>
            <input v-model.number="scheduleConfig[field.key]" class="input" type="number" :min="field.min" :max="field.max" />
          </label>
          <label v-else-if="field.type === 'text'" class="field">
            <span>{{ field.label }}</span>
            <input v-model="scheduleConfig[field.key]" class="input" />
          </label>
          <div v-else class="field wide">
            <span>{{ field.label }}</span>
            <EntitySelect
              :model-value="String(scheduleConfig[field.key] || '')"
              :loader="entityLoader(field)"
              :placeholder="entityPlaceholder(field)"
              @update:model-value="scheduleConfig[field.key] = String($event)"
            />
          </div>
        </template>
      </div>
    </section>
  </FormDrawer>

  <FormDrawer
    :open="Boolean(runTarget)"
    title="手动执行一次"
    :description="String(runTarget?.display_name || '')"
    submit-text="执行一次"
    :busy="runningNow"
    @close="runTarget = null"
    @submit="runOnce"
  >
    <section class="drawer-section">
      <h3>本次执行参数</h3>
      <div class="drawer-grid">
        <template v-for="field in runFields" :key="field.key">
          <label v-if="field.type === 'number'" class="field">
            <span>{{ field.label }}</span>
            <input v-model.number="runConfig[field.key]" class="input" type="number" :min="field.min" :max="field.max" />
          </label>
          <label v-else-if="field.type === 'text'" class="field">
            <span>{{ field.label }}</span>
            <input v-model="runConfig[field.key]" class="input" />
          </label>
          <div v-else class="field wide">
            <span>{{ field.label }}</span>
            <EntitySelect
              :model-value="String(runConfig[field.key] || '')"
              :loader="entityLoader(field)"
              :placeholder="entityPlaceholder(field)"
              @update:model-value="runConfig[field.key] = String($event)"
            />
          </div>
        </template>
      </div>
    </section>
  </FormDrawer>
</template>

<style scoped>
.spin { animation: spin 0.9s linear infinite; }
.schedule-toggle { align-items: center; color: var(--text-muted); display: inline-flex; font-size: 11px; gap: 5px; }
.schedule-toggle input { accent-color: var(--accent); }
.drawer-section { display: grid; gap: 12px; }
.drawer-section + .drawer-section { border-top: 1px solid var(--border); padding-top: 14px; }
.drawer-section h3 { font-size: 13px; margin: 0; }
.drawer-grid { display: grid; gap: 10px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.drawer-grid .wide { grid-column: 1 / -1; }
.check { align-items: center; color: var(--text-muted); display: flex; font-size: 12px; gap: 7px; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 620px) { .drawer-grid { grid-template-columns: 1fr; } }
</style>
