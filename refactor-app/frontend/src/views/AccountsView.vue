<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import ResourcePage from "../components/ResourcePage.vue";
import type { Row } from "../api/resources";
import { resourcesApi } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();
const router = useRouter();

const columns = [
  { key: "id", label: "账号 ID", mono: true },
  { key: "email", label: "邮箱" },
  { key: "phone_number", label: "手机号" },
  { key: "openai_user_id", label: "OpenAI 用户 ID", mono: true },
  { key: "personal_chatgpt_account_id", label: "个人 Account ID", mono: true, summary: 28 },
  { key: "account_status", label: "账号状态", badge: true },
  { key: "session_status", label: "Session 状态", badge: true },
  { key: "refresh_token_status", label: "RT 状态", badge: true },
  { key: "created_at", label: "创建时间" },
];

const filters = [
  {
    key: "account_status",
    label: "账号状态",
    options: [
      { label: "active", value: "active" },
      { label: "invalid", value: "invalid" },
    ],
  },
  {
    key: "session_status",
    label: "Session 状态",
    options: [
      { label: "unknown", value: "unknown" },
      { label: "active", value: "active" },
      { label: "expired", value: "expired" },
      { label: "invalid", value: "invalid" },
      { label: "refreshing", value: "refreshing" },
      { label: "dead", value: "dead" },
      { label: "error", value: "error" },
    ],
  },
  {
    key: "refresh_token_status",
    label: "RT 状态",
    options: [
      { label: "missing", value: "missing" },
      { label: "active", value: "active" },
      { label: "refreshing", value: "refreshing" },
      { label: "expired", value: "expired" },
      { label: "invalid", value: "invalid" },
      { label: "dead", value: "dead" },
      { label: "error", value: "error" },
    ],
  },
];

const selectedCount = ref(0);
const selectedRows = ref<Row[]>([]);
const backfillConcurrency = ref(10);
const inviteConcurrency = ref(50);
const authConcurrency = ref(50);
const workspaces = ref<Row[]>([]);
const selectedWorkspaceId = ref("");
const selectedAuthWorkspaceId = ref("");
const codexClientId = ref("app_EMoamEEZ73f0CkXaXp7hrann");

onMounted(async () => {
  workspaces.value = await resourcesApi.workspaces();
  if (!selectedWorkspaceId.value && workspaces.value.length) {
    selectedWorkspaceId.value = String(workspaces.value[0].id || "");
  }
  if (!selectedAuthWorkspaceId.value && workspaces.value.length) {
    selectedAuthWorkspaceId.value = String(workspaces.value[0].id || "");
  }
});

function updateSelection(rows: Record<string, unknown>[]) {
  selectedRows.value = rows as Row[];
  selectedCount.value = rows.length;
}

async function runSelectedAccountJob(kind: "session" | "rt" | "session_rt") {
  const ids = selectedRows.value.map((row) => String(row.id || "")).filter(Boolean);
  if (!ids.length) {
    store.toast("未选择账号", "请先勾选账号。", "warning");
    return;
  }
  const payload = {
    user_account_ids: ids,
    created_by: "ops-ui",
    concurrency: backfillConcurrency.value,
  };
  const result = kind === "session"
    ? await resourcesApi.backfillSession(payload)
    : kind === "rt"
      ? await resourcesApi.backfillRt(payload)
      : await resourcesApi.backfillSessionRt(payload);
  const titleByKind = {
    session: "补 Session 执行完成",
    rt: "补 RT 执行完成",
    session_rt: "补 Session + RT 执行完成",
  };
  store.toast(
    titleByKind[kind],
    `work=${result.work_count} 并发=${result.concurrency} 成功=${result.succeeded} 失败=${result.failed}`,
    result.failed > 0 ? "warning" : "success",
  );
  await router.push({ name: "job-trace", params: { jobId: result.job_id } });
}

async function inviteSelectedUsers() {
  const ids = selectedRows.value.map((row) => String(row.id || "")).filter(Boolean);
  if (!ids.length) {
    store.toast("未选择账号", "请先勾选账号。", "warning");
    return;
  }
  if (!selectedWorkspaceId.value) {
    store.toast("未选择空间", "请先选择要邀请进入的空间。", "warning");
    return;
  }
  const result = await resourcesApi.membershipInvite({
    team_workspace_id: selectedWorkspaceId.value,
    user_account_ids: ids,
    created_by: "ops-ui",
    concurrency: inviteConcurrency.value,
  });
  store.toast(
    "邀请任务执行完成",
    `work=${result.work_count ?? ids.length} 成功=${result.succeeded ?? 0} 失败=${result.failed ?? 0}`,
    Number(result.failed ?? 0) > 0 ? "warning" : "success",
  );
  await router.push({ name: "job-trace", params: { jobId: result.job_id } });
}

async function buildSelectedCredentials() {
  const ids = selectedRows.value.map((row) => String(row.id || "")).filter(Boolean);
  if (!ids.length) {
    store.toast("未选择账号", "请先勾选账号。", "warning");
    return;
  }
  if (!selectedAuthWorkspaceId.value) {
    store.toast("未选择空间", "请先选择要授权的空间。", "warning");
    return;
  }
  const result = await resourcesApi.buildCredentials({
    user_account_ids: ids,
    team_workspace_id: selectedAuthWorkspaceId.value,
    codex_client_id: codexClientId.value,
    created_by: "ops-ui",
    concurrency: authConcurrency.value,
  });
  store.toast(
    "Codex 授权执行完成",
    `work=${result.work_count} 并发=${result.concurrency} 成功=${result.succeeded} 失败=${result.failed}`,
    result.failed > 0 ? "warning" : "success",
  );
  await router.push({ name: "job-trace", params: { jobId: result.job_id } });
}

async function deleteAccount(row: Row, reload: () => Promise<void>) {
  const id = String(row.id || "");
  if (!id) return;
  const email = String(row.email || "");
  const confirmed = window.confirm(`确认删除账号？\n\n${email || id}\n\n会同时删除该账号的代理绑定。`);
  if (!confirmed) return;
  const result = await resourcesApi.deleteAccount(id);
  store.toast(
    "账号已删除",
    `账号=${result.user_account_id} 代理绑定=${result.deleted_proxy_bindings}`,
    "success",
  );
  await reload();
}
</script>

<template>
  <ResourcePage
    title="账号"
    description="账号级只区分 active / invalid；Session 与账号级 RT 状态在本页展示，Workspace/Codex token 在对应页面展示。"
    :columns="columns"
    :loader="resourcesApi.accounts"
    :filters="filters"
    selectable
    empty-text="暂无账号。"
    @selection-change="updateSelection"
  >
    <template #actionCards>
      <section class="panel account-action-card">
        <div class="account-action-heading">
          <div>
            <h2>账号认证</h2>
            <p>对选中账号补 Session、个人 RT 或同时补齐。</p>
          </div>
          <span class="selected-hint">已选 {{ selectedCount }} 个账号</span>
        </div>
        <div class="account-action-body">
          <label class="inline-control">
            <span>并发 Work</span>
            <input v-model.number="backfillConcurrency" class="input small-input" type="number" min="1" max="500" />
          </label>
          <button class="btn" :disabled="selectedCount === 0" @click="runSelectedAccountJob('session')">
            补 Session
          </button>
          <button class="btn" :disabled="selectedCount === 0" @click="runSelectedAccountJob('rt')">
            补 RT
          </button>
          <button class="btn" :disabled="selectedCount === 0" @click="runSelectedAccountJob('session_rt')">
            补 Session + RT
          </button>
        </div>
      </section>

      <section class="panel account-action-card">
        <div class="account-action-heading">
          <div>
            <h2>Codex 授权</h2>
            <p>使用选中账号对指定 Team Workspace 生成 Codex OAuth credential。</p>
          </div>
        </div>
        <div class="account-action-body">
          <label class="inline-control">
            <span>授权空间</span>
            <select v-model="selectedAuthWorkspaceId" class="select workspace-select">
              <option v-for="workspace in workspaces" :key="String(workspace.id)" :value="String(workspace.id)">
                {{ workspace.name || workspace.external_workspace_id }} / {{ workspace.external_workspace_id }}
              </option>
            </select>
          </label>
          <label class="inline-control">
            <span>Codex Client</span>
            <input v-model="codexClientId" class="input workspace-select" />
          </label>
          <label class="inline-control">
            <span>授权并发</span>
            <input v-model.number="authConcurrency" class="input small-input" type="number" min="1" max="500" />
          </label>
          <button class="btn primary" :disabled="selectedCount === 0 || !selectedAuthWorkspaceId" @click="buildSelectedCredentials">
            生成 Codex 授权
          </button>
        </div>
      </section>

      <section class="panel account-action-card">
        <div class="account-action-heading">
          <div>
            <h2>空间邀请</h2>
            <p>向指定 Team Workspace 发送邀请，接受邀请在“空间成员”页处理。</p>
          </div>
        </div>
        <div class="account-action-body">
          <label class="inline-control">
            <span>邀请空间</span>
            <select v-model="selectedWorkspaceId" class="select workspace-select">
              <option v-for="workspace in workspaces" :key="String(workspace.id)" :value="String(workspace.id)">
                {{ workspace.name || workspace.external_workspace_id }} / {{ workspace.external_workspace_id }}
              </option>
            </select>
          </label>
          <label class="inline-control">
            <span>邀请并发</span>
            <input v-model.number="inviteConcurrency" class="input small-input" type="number" min="1" max="500" />
          </label>
          <button class="btn primary" :disabled="selectedCount === 0 || !selectedWorkspaceId" @click="inviteSelectedUsers">
            发送邀请
          </button>
        </div>
      </section>
    </template>
    <template #rowActions="{ row, reload }">
      <button class="btn danger" @click="deleteAccount(row, reload)">删除</button>
    </template>
  </ResourcePage>
</template>

<style scoped>
.account-action-card {
  margin-bottom: 14px;
  overflow: hidden;
  padding: 0;
}

.account-action-heading {
  align-items: center;
  border-bottom: 1px solid var(--border);
  display: flex;
  gap: 12px;
  justify-content: space-between;
  padding: 14px 16px;
}

.account-action-heading h2 {
  font-size: 14px;
  letter-spacing: -0.01em;
  margin: 0;
}

.account-action-heading p {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.45;
  margin: 5px 0 0;
}

.account-action-body {
  align-items: end;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 14px 16px 16px;
}

.selected-hint {
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 800;
}

@media (max-width: 767px) {
  .account-action-heading,
  .account-action-body {
    align-items: stretch;
    flex-direction: column;
  }
}

</style>
