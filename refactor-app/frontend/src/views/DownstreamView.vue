<script setup lang="ts">
import { ref } from "vue";

import ResourcePage from "../components/ResourcePage.vue";
import { resourcesApi } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();
const thresholdPercent = ref(95);
const selectedRows = ref<Record<string, unknown>[]>([]);
const repushing = ref(false);

const columns = [
  { key: "id", label: "推送记录 ID", mono: true },
  { key: "codex_credential_id", label: "授权 ID", mono: true, summary: 28 },
  { key: "downstream_channel_name", label: "渠道" },
  { key: "downstream_provider", label: "下游平台", badge: true },
  { key: "push_status", label: "推送状态", badge: true },
  { key: "push_attempt_count", label: "推送尝试" },
  { key: "downstream_external_id", label: "下游外部 ID", mono: true },
  { key: "downstream_chatgpt_account_id", label: "下游空间", mono: true },
  { key: "token_chatgpt_account_id", label: "Token 空间", mono: true },
  { key: "usage_percent", label: "使用率" },
  { key: "usage_status", label: "使用状态", badge: true },
  { key: "error_code", label: "错误码", badge: true },
  { key: "error_message", label: "错误信息" },
];

function onSelectionChange(rows: Record<string, unknown>[]) {
  selectedRows.value = rows;
}

async function sweepUsage(reload: () => Promise<void>) {
  const result = await resourcesApi.downstreamUsageSweep({
    threshold_percent: thresholdPercent.value,
    created_by: "ops-ui",
  });
  store.toast(
    "使用率扫描完成",
    `检查=${result.checked_count ?? 0} 近阈值=${result.near_limit_count ?? 0} 来源=${result.usage_source ?? ""}`,
    "success",
  );
  await reload();
}

async function repushSelected(reload: () => Promise<void>) {
  const ids = selectedRows.value
    .filter((row) => String(row.push_status || "") === "pushed")
    .map((row) => String(row.id || ""))
    .filter(Boolean);
  if (!ids.length) {
    store.toast("没有可重推记录", "请先勾选推送状态为 pushed 的记录。", "warning");
    return;
  }
  repushing.value = true;
  try {
    const result = await resourcesApi.repushDownstreamRecords({
      downstream_push_record_ids: ids,
      created_by: "ops-ui",
    });
    store.toast(
      "重推完成",
      `请求=${result.requested ?? ids.length} 成功=${result.succeeded ?? 0} 失败=${result.failed ?? 0} 跳过=${result.skipped ?? 0}`,
      Number(result.failed ?? 0) > 0 ? "warning" : "success",
    );
    await reload();
  } catch (err) {
    store.toast("重推失败", String((err as Error).message ?? err), "error");
  } finally {
    repushing.value = false;
  }
}
</script>

<template>
  <ResourcePage
    title="下游推送"
    description="CPA / Sub2API 推送结果。当前按 Codex 授权唯一记录，一条授权只能占用一个下游渠道。"
    :columns="columns"
    :loader="resourcesApi.downstream"
    selectable
    empty-text="暂无下游推送记录。"
    @selection-change="onSelectionChange"
  >
    <template #actionCards="{ reload }">
      <section class="panel action-card">
        <div class="action-heading">
          <div>
            <h2>成功记录重推</h2>
            <p>只重推 push_status=pushed 的记录；不扣余额、不新增占用、不新建推送记录。</p>
          </div>
        </div>
        <div class="action-row">
          <button class="btn primary" :disabled="repushing" @click="repushSelected(reload)">
            {{ repushing ? "重推中..." : `重推选中成功记录（${selectedRows.length}）` }}
          </button>
        </div>
      </section>
      <section class="panel action-card">
        <div class="action-heading">
          <div>
            <h2>使用率扫描</h2>
            <p>当前 usage 来源是 placeholder，占位返回 0%；后续接真实下游额度接口。</p>
          </div>
        </div>
        <div class="action-row">
          <label class="inline-control">
            <span>剔除阈值百分比</span>
            <input v-model.number="thresholdPercent" class="input small-input" type="number" min="1" max="100" />
          </label>
          <button class="btn" @click="sweepUsage(reload)">扫描已推送凭证</button>
        </div>
      </section>
    </template>
  </ResourcePage>
</template>

<style scoped>
.action-card {
  margin-bottom: 14px;
  overflow: hidden;
  padding: 0;
}

.action-heading {
  border-bottom: 1px solid var(--border);
  padding: 14px 16px;
}

.action-heading h2 {
  font-size: 14px;
  margin: 0;
}

.action-heading p {
  color: var(--text-muted);
  font-size: 12px;
  margin: 5px 0 0;
}

.action-row {
  align-items: end;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 14px 16px 16px;
}
</style>
