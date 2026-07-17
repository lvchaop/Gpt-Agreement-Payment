<script setup lang="ts">
import { Download, RefreshCw } from "@lucide/vue";
import { computed, onMounted, ref, watch } from "vue";

import FormDrawer from "../components/FormDrawer.vue";
import ResourcePage from "../components/ResourcePage.vue";
import type { Column, TableFilter } from "../components/DataTable.vue";
import type { Row } from "../api/resources";
import { resourcesApi } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();
const pageRef = ref<InstanceType<typeof ResourcePage> | null>(null);
const selectedRows = ref<Row[]>([]);
const settling = ref(false);
const downloading = ref(false);
const exportDrawerOpen = ref(false);
const exportCredentialType = ref("");
const exportSpaceId = ref("");
const exportLimit = ref(0);
const spaceOptions = ref<{ label: string; value: string }[]>([]);
const selectedPushedCount = computed(
  () => selectedRows.value.filter((row) => String(row.push_status || "") === "pushed").length,
);
const selectedManualExportRows = computed(() =>
  selectedRows.value.filter((row) => String(row.distribution_mode || "") === "manual_export"),
);
const selectedExportBatchIds = computed(() => [
  ...new Set(
    selectedManualExportRows.value
      .map((row) => String(row.export_batch_id || row.downstream_external_id || ""))
      .filter(Boolean),
  ),
]);

const filters: TableFilter[] = [
  {
    key: "distribution_mode",
    label: "分配方式",
    options: [
      { label: "渠道推送", value: "channel_push" },
      { label: "文件导出", value: "manual_export" },
    ],
  },
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

const columns: Column[] = [
  { key: "space_credential_id", label: "空间凭证 ID", mono: true, summary: 28 },
  { key: "email", label: "账号邮箱", summary: 30 },
  { key: "external_space_id", label: "外部空间 ID", mono: true, summary: 28 },
  { key: "space_name", label: "空间名称", summary: 24 },
  { key: "credential_type", label: "凭证类型", badge: true },
  { key: "distribution_mode", label: "分配方式", badge: true },
  { key: "downstream_channel_name", label: "下游渠道", summary: 24 },
  { key: "downstream_provider", label: "下游类型", badge: true },
  { key: "push_status", label: "推送状态", badge: true },
  { key: "recycle_status", label: "回收状态", badge: true },
  { key: "usage_summary", label: "使用额度", summary: 42 },
  { key: "last_usage_checked_at", label: "额度更新时间", type: "datetime", relativeTime: true },
  { key: "pushed_count", label: "成功" },
  { key: "failed_push_count", label: "失败" },
  { key: "used_count", label: "使用" },
  { key: "latest_attempt_status", label: "最近尝试", badge: true },
  { key: "latest_attempt_error_code", label: "最近错误码", badge: true },
  { key: "latest_attempt_error_message", label: "最近错误", summary: 44 },
  { key: "downstream_external_id", label: "外部 ID / 导出批次", mono: true, summary: 28 },
  { key: "updated_at", label: "更新时间", type: "datetime", relativeTime: true, sortable: true },
];

function updateSelection(rows: Record<string, unknown>[]) {
  selectedRows.value = rows as Row[];
}

async function reload() {
  await pageRef.value?.load();
}

async function loadSpaceOptions() {
  try {
    const result = await resourcesApi.spaceOptions("", "", exportCredentialType.value);
    spaceOptions.value = result.items.map((item) => ({
      label: item.label,
      value: item.value,
    }));
  } catch {
    spaceOptions.value = [];
  }
}

watch(exportCredentialType, async () => {
  exportSpaceId.value = "";
  await loadSpaceOptions();
});

onMounted(async () => {
  await loadSpaceOptions();
});

function saveDownload(result: { blob: Blob; filename: string }) {
  const url = URL.createObjectURL(result.blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = result.filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

async function exportUnpushed() {
  downloading.value = true;
  try {
    const result = await resourcesApi.exportUnpushedSpaceCredentials({
      credential_type: exportCredentialType.value,
      space_id: exportSpaceId.value,
      limit: Math.max(0, Number(exportLimit.value || 0)),
    });
    saveDownload(result);
    exportDrawerOpen.value = false;
    store.toast(
      "号池凭证已下载并出池",
      `导出 ${result.exportedCount} 条，批次 ${result.exportBatchId}`,
      "success",
    );
    await reload();
  } catch (err) {
    store.toast("下载失败", String((err as Error).message ?? err), "error");
  } finally {
    downloading.value = false;
  }
}

async function redownloadSelected() {
  const ids = selectedManualExportRows.value
    .map((row) => String(row.space_credential_id || row.id || ""))
    .filter(Boolean);
  if (!ids.length) {
    store.toast("未选择文件导出记录", "请先勾选分配方式为 manual_export 的记录。", "warning");
    return;
  }
  await runRedownload({ space_credential_ids: ids });
}

async function redownloadBatch() {
  if (selectedExportBatchIds.value.length !== 1) {
    store.toast("请选择一个导出批次", "选中的文件导出记录必须属于同一个批次。", "warning");
    return;
  }
  await runRedownload({ export_batch_id: selectedExportBatchIds.value[0] });
}

async function runRedownload(body: Record<string, unknown>) {
  downloading.value = true;
  try {
    const result = await resourcesApi.redownloadSpaceCredentials(body);
    saveDownload(result);
    store.toast("凭证文件已重新下载", `下载 ${result.exportedCount} 条，状态未改变。`, "success");
  } catch (err) {
    store.toast("重新下载失败", String((err as Error).message ?? err), "error");
  } finally {
    downloading.value = false;
  }
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
        <button class="btn primary" :disabled="downloading" @click="exportDrawerOpen = true">
          <Download :size="16" />下载号池凭证
        </button>
        <button class="btn" :disabled="downloading || selectedManualExportRows.length === 0" @click="redownloadSelected">
          <RefreshCw :size="16" />重新下载选中（{{ selectedManualExportRows.length }}）
        </button>
        <button class="btn" :disabled="downloading || selectedExportBatchIds.length !== 1" @click="redownloadBatch">
          <Download :size="16" />重新下载整批
        </button>
        <button class="btn primary" :disabled="settling || selectedPushedCount === 0" @click="manualSettleSelected">
          {{ settling ? "结算中..." : `手动结算已选推送凭证（${selectedPushedCount}）` }}
        </button>
        <span class="action-hint">只处理推送状态 pushed；结算后推送状态会改为 used 或 skipped。</span>
      </div>
    </template>
  </ResourcePage>

  <FormDrawer
    :open="exportDrawerOpen"
    title="下载未推送凭证"
    description="文件生成成功后，这批凭证立即标记为已分配，不再进入下游推送；可在推送记录中重复下载。"
    :busy="downloading"
    submit-text="下载并出池"
    @close="exportDrawerOpen = false"
    @submit="exportUnpushed"
  >
    <label class="field">
      <span>凭证类型</span>
      <select v-model="exportCredentialType" class="input">
        <option value="">全部类型</option>
        <option value="personal_account">个人账号</option>
        <option value="team_5h_weekly">Team 5h/周</option>
        <option value="team_monthly">Team 月</option>
      </select>
    </label>
    <label class="field">
      <span>Space</span>
      <select v-model="exportSpaceId" class="input">
        <option value="">全部 Space</option>
        <option v-for="option in spaceOptions" :key="option.value" :value="option.value">
          {{ option.label }}
        </option>
      </select>
    </label>
    <label class="field">
      <span>下载数量</span>
      <input v-model.number="exportLimit" class="input" type="number" min="0" step="1" />
      <small>填写 0 下载全部符合条件的号池凭证。</small>
    </label>
  </FormDrawer>
</template>
