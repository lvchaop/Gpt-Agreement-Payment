<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";

import ResourcePage from "../components/ResourcePage.vue";
import type { Row } from "../api/resources";
import { resourcesApi } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const router = useRouter();
const store = useOpsStore();
const selectedRows = ref<Row[]>([]);
const selectedCount = ref(0);
const heartbeatConcurrency = ref(50);
const reauthConcurrency = ref(50);
const batchName = ref("");

const columns = [
  { key: "id", label: "授权 ID", mono: true, summary: 28 },
  { key: "user_email", label: "账号邮箱", summary: 30 },
  { key: "user_account_id", label: "账号 ID", mono: true, summary: 28 },
  { key: "workspace_name", label: "空间名称", summary: 26 },
  { key: "external_workspace_id", label: "外部空间 ID", mono: true, summary: 28 },
  { key: "codex_client_id", label: "客户端", mono: true, summary: 28 },
  { key: "credential_status", label: "授权状态", badge: true },
  { key: "expires_at", label: "过期时间", summary: 30 },
  { key: "last_heartbeat_status", label: "心跳状态", badge: true },
  { key: "last_heartbeat_at", label: "最近心跳时间" },
  { key: "bound_batch_id", label: "占用批次", mono: true, summary: 26 },
];

function updateSelection(rows: Record<string, unknown>[]) {
  selectedRows.value = rows as Row[];
  selectedCount.value = rows.length;
}

async function heartbeatSelected() {
  const ids = selectedRows.value.map((row) => String(row.id || "")).filter(Boolean);
  if (!ids.length) {
    store.toast("未选择授权", "请先勾选要心跳检测的授权。", "warning");
    return;
  }
  const result = await resourcesApi.heartbeatCredentials({
    codex_credential_ids: ids,
    created_by: "ops-ui",
    concurrency: heartbeatConcurrency.value,
  });
  store.toast(
    "心跳检测完成",
    `work=${result.work_count} 并发=${result.concurrency} 成功=${result.succeeded} 失败=${result.failed}`,
    result.failed > 0 ? "warning" : "success",
  );
  await router.push(`/jobs/${result.job_id}`);
}

async function reauthorizeSelected() {
  const userAccountIds = [
    ...new Set(selectedRows.value.map((row) => String(row.user_account_id || "")).filter(Boolean)),
  ];
  if (!userAccountIds.length) {
    store.toast("未选择授权", "请先勾选要重新授权的记录。", "warning");
    return;
  }
  const workspaceIds = new Set(selectedRows.value.map((row) => String(row.team_workspace_id || "")));
  if (workspaceIds.size !== 1) {
    store.toast("空间不一致", "重新授权要求选中的授权属于同一个团队空间。", "warning");
    return;
  }
  const clientIds = new Set(selectedRows.value.map((row) => String(row.codex_client_id || "")));
  if (clientIds.size !== 1) {
    store.toast("客户端不一致", "重新授权要求选中的授权使用同一个 codex_client_id。", "warning");
    return;
  }
  const result = await resourcesApi.buildCredentials({
    user_account_ids: userAccountIds,
    team_workspace_id: [...workspaceIds][0],
    codex_client_id: [...clientIds][0],
    created_by: "ops-ui-reauthorize",
    concurrency: reauthConcurrency.value,
    force_reauthorize: true,
  });
  store.toast(
    "重新授权完成",
    `work=${result.work_count} 并发=${result.concurrency} 成功=${result.succeeded} 失败=${result.failed}`,
    result.failed > 0 ? "warning" : "success",
  );
  await router.push(`/jobs/${result.job_id}`);
}

async function createBatchFromSelected() {
  const ids = selectedRows.value.map((row) => String(row.id || "")).filter(Boolean);
  if (!ids.length) {
    store.toast("未选择授权", "请先勾选要加入批次的授权。", "warning");
    return;
  }
  const workspaceIds = new Set(selectedRows.value.map((row) => String(row.team_workspace_id || "")));
  if (workspaceIds.size !== 1) {
    store.toast("空间不一致", "同一个批次只能选择同一个团队空间下的授权。", "warning");
    return;
  }
  const occupied = selectedRows.value.filter((row) => String(row.bound_batch_id || ""));
  if (occupied.length > 0) {
    store.toast("授权已被批次占用", `已有 ${occupied.length} 条授权存在 active batch item。`, "warning");
    return;
  }
  const result = await resourcesApi.createBatchFromCredentials({
    team_workspace_id: [...workspaceIds][0],
    codex_credential_ids: ids,
    batch_name: batchName.value,
    created_by: "ops-ui",
  });
  store.toast("批次已创建", result.batch_id, "success");
  await router.push(`/join-batches/${result.batch_id}`);
}
</script>

<template>
  <ResourcePage
    title="Codex 授权"
    description="每个账号在某个 Team Workspace 下的 Codex OAuth credential。token 明文不默认展示。"
    :columns="columns"
    :loader="resourcesApi.credentials"
    empty-text="暂无 Codex 授权。"
    selectable
    @selection-change="updateSelection"
  >
    <template #actionCards>
      <section class="panel credential-action-card">
        <div class="credential-action-heading">
          <div>
            <h2>授权维护</h2>
            <p>对已生成的 Codex OAuth credential 做心跳检测或重新授权。</p>
          </div>
          <span class="selected-hint">已选 {{ selectedCount }} 条授权</span>
        </div>
        <div class="credential-action-body">
          <label class="field">
            <span>心跳并发</span>
            <input v-model.number="heartbeatConcurrency" class="input small-input" type="number" min="1" max="500" />
          </label>
          <button class="btn" :disabled="selectedCount === 0" @click="heartbeatSelected">
            心跳检测选中（{{ selectedCount }}）
          </button>
          <label class="field">
            <span>授权并发</span>
            <input v-model.number="reauthConcurrency" class="input small-input" type="number" min="1" max="500" />
          </label>
          <button class="btn" :disabled="selectedCount === 0" @click="reauthorizeSelected">
            重新授权选中（{{ selectedCount }}）
          </button>
        </div>
      </section>

      <section class="panel credential-action-card">
        <div class="credential-action-heading">
          <div>
            <h2>批次创建</h2>
            <p>把同一空间下未被占用的授权记录加入一个新批次。</p>
          </div>
        </div>
        <div class="credential-action-body batch-action-body">
          <label class="field batch-name">
            <span>批次名称</span>
            <input v-model="batchName" class="input" placeholder="可选" />
          </label>
          <button class="btn primary" :disabled="selectedCount === 0" @click="createBatchFromSelected">
            用选中授权创建批次
          </button>
        </div>
      </section>
    </template>
  </ResourcePage>
</template>

<style scoped>
.credential-action-card {
  margin-bottom: 14px;
  overflow: hidden;
  padding: 0;
}

.credential-action-heading {
  align-items: center;
  border-bottom: 1px solid var(--border);
  display: flex;
  gap: 12px;
  justify-content: space-between;
  padding: 14px 16px;
}

.credential-action-heading h2 {
  font-size: 14px;
  letter-spacing: -0.01em;
  margin: 0;
}

.credential-action-heading p,
.selected-hint {
  color: var(--text-muted);
}

.credential-action-heading p {
  font-size: 12px;
  line-height: 1.45;
  margin: 5px 0 0;
}

.selected-hint {
  font-size: 13px;
  font-weight: 800;
}

.credential-action-body {
  align-items: end;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 14px 16px 16px;
  width: 100%;
}

.batch-action-body {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) auto;
}

.batch-name {
  min-width: 0;
}

@media (max-width: 767px) {
  .credential-action-heading,
  .credential-action-body {
    align-items: stretch;
    flex-direction: column;
  }

  .batch-action-body {
    grid-template-columns: 1fr;
  }
}
</style>
