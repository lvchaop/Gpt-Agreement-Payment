<script setup lang="ts">
import { computed, ref } from "vue";

import ResourcePage from "../components/ResourcePage.vue";
import type { Row } from "../api/resources";
import { resourcesApi } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();
const pageRef = ref<InstanceType<typeof ResourcePage> | null>(null);
const selectedRows = ref<Row[]>([]);
const settling = ref(false);
const selectedPushedCount = computed(
  () => selectedRows.value.filter((row) => String(row.push_status || "") === "pushed").length,
);

const filters = [
  {
    key: "credential_type",
    label: "凭证类型",
    options: [
      { label: "个人账号", value: "personal_account" },
      { label: "Team 5h/周", value: "team_5h_weekly" },
      { label: "Team 月", value: "team_monthly" },
    ],
  },
  {
    key: "push_status",
    label: "推送状态",
    options: [
      { label: "none", value: "none" },
      { label: "pending", value: "pending" },
      { label: "pushing", value: "pushing" },
      { label: "pushed", value: "pushed" },
      { label: "failed", value: "failed" },
      { label: "skipped", value: "skipped" },
      { label: "used", value: "used" },
    ],
  },
  {
    key: "recycle_status",
    label: "回收状态",
    options: [
      { label: "none", value: "none" },
      { label: "pending", value: "pending" },
      { label: "running", value: "running" },
      { label: "done", value: "done" },
      { label: "failed", value: "failed" },
      { label: "blocked", value: "blocked" },
    ],
  },
];

const columns = [
  { key: "space_credential_id", label: "空间凭证 ID", mono: true, summary: 28 },
  { key: "email", label: "账号邮箱", summary: 30 },
  { key: "external_space_id", label: "外部空间 ID", mono: true, summary: 28 },
  { key: "space_name", label: "空间名称", summary: 24 },
  { key: "credential_type", label: "凭证类型", badge: true },
  { key: "downstream_channel_name", label: "下游渠道", summary: 24 },
  { key: "downstream_provider", label: "下游类型", badge: true },
  { key: "push_status", label: "推送状态", badge: true },
  { key: "recycle_status", label: "回收状态", badge: true },
  { key: "usage_summary", label: "使用额度", summary: 42 },
  { key: "last_usage_checked_at", label: "额度更新时间", summary: 30 },
  { key: "pushed_count", label: "成功" },
  { key: "failed_push_count", label: "失败" },
  { key: "used_count", label: "使用" },
  { key: "latest_attempt_status", label: "最近尝试", badge: true },
  { key: "latest_attempt_error_code", label: "最近错误码", badge: true },
  { key: "latest_attempt_error_message", label: "最近错误", summary: 44 },
  { key: "downstream_external_id", label: "下游外部 ID", mono: true, summary: 28 },
  { key: "updated_at", label: "更新时间", summary: 30 },
];

function updateSelection(rows: Record<string, unknown>[]) {
  selectedRows.value = rows as Row[];
}

async function reload() {
  await pageRef.value?.load();
}

async function manualSettleSelected() {
  const ids = selectedRows.value
    .filter((row) => String(row.push_status || "") === "pushed")
    .map((row) => String(row.space_credential_id || row.id || ""))
    .filter(Boolean);
  if (!ids.length) {
    store.toast("未选择推送凭证", "请先勾选 push_status=pushed 的推送记录。", "warning");
    return;
  }
  settling.value = true;
  try {
    const result = await resourcesApi.manualSettleSpacePushRecords({
      space_credential_ids: ids,
      created_by: "ops-ui",
    });
    store.toast(
      "手动结算完成",
      `已改推送状态：used=${result.used ?? 0} skipped=${result.skipped ?? 0} ignored=${result.ignored ?? 0}`,
      Number(result.ignored || 0) > 0 || Number(result.failed || 0) > 0 ? "warning" : "success",
    );
    await reload();
  } catch (err) {
    store.toast("手动结算失败", String((err as Error).message ?? err), "error");
  } finally {
    settling.value = false;
  }
}
</script>

<template>
  <ResourcePage
    ref="pageRef"
    title="推送记录"
    description="读取现有 space_push_bindings / space_push_attempts / space_credential_usage_states，不新增表。"
    :columns="columns"
    :loader="resourcesApi.spacePushRecords"
    :filters="filters"
    empty-text="暂无推送记录。"
    selectable
    @selection-change="updateSelection"
  >
    <template #actions>
      <div class="action-group">
        <button class="btn primary" :disabled="settling || selectedPushedCount === 0" @click="manualSettleSelected">
          {{ settling ? "结算中..." : `手动结算已选推送凭证（${selectedPushedCount}）` }}
        </button>
        <span class="action-hint">只处理推送状态 pushed；结算后推送状态会改为 used 或 skipped。</span>
      </div>
    </template>
    <template #before>
      <section class="panel hint-card">
        <strong>数据来源</strong>
        <span>当前状态：space_push_bindings；最近尝试：space_push_attempts；使用额度：space_credential_usage_states。</span>
      </section>
    </template>
  </ResourcePage>
</template>

<style scoped>
.hint-card {
  align-items: center;
  color: var(--text-muted);
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
  padding: 12px 14px;
}

.hint-card strong {
  color: var(--text-primary);
}
</style>
