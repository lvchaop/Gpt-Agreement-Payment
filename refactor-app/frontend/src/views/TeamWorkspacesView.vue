<script setup lang="ts">
import { onMounted, ref } from "vue";

import DataTable from "../components/DataTable.vue";
import ResourcePage from "../components/ResourcePage.vue";
import { resourcesApi } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();
const adminSessionJson = ref("");
const adminCookieHeader = ref("");
const accountsCheckHeadersText = ref("");
const showImportPanel = ref(false);
const adminSessions = ref<Record<string, unknown>[]>([]);
const adminSessionsLoading = ref(false);
const adminSessionsError = ref("");
const removingWorkspaceId = ref("");
const revokingInviteWorkspaceId = ref("");
const deletingAdminSessionId = ref("");

const columns = [
  { key: "id", label: "空间 ID", mono: true, summary: 26 },
  { key: "name", label: "名称" },
  { key: "external_workspace_id", label: "外部空间 ID", mono: true, summary: 26 },
  { key: "admin_email", label: "管理员邮箱", mono: true, summary: 32 },
  { key: "provider", label: "来源" },
  { key: "plan_type", label: "套餐" },
  { key: "seat_limit", label: "席位上限" },
  { key: "workspace_status", label: "状态", badge: true },
  { key: "source_admin_session_id", label: "管理员 Session", mono: true, summary: 26 },
];

const adminSessionColumns = [
  { key: "id", label: "Session ID", mono: true, summary: 26 },
  { key: "admin_email", label: "管理员邮箱", mono: true, summary: 34 },
  { key: "expires_at", label: "Cookie/Session 过期时间", mono: true, summary: 30 },
  { key: "imported_at", label: "导入/更新时间", mono: true, summary: 30 },
];

async function importAdminSession(reload: () => Promise<void>) {
  let raw: Record<string, unknown>;
  try {
    raw = JSON.parse(adminSessionJson.value);
  } catch {
    store.toast("JSON 格式错误", "请粘贴完整 api/auth/session JSON。", "error");
    return;
  }
  const result = await resourcesApi.importTeamAdminSession({
    raw_session_json: raw,
    cookie_header: adminCookieHeader.value,
    accounts_check_headers_text: accountsCheckHeadersText.value,
    fetch_accounts_check: true,
  });
  store.toast(
    "管理员 Session 已导入",
    `管理员=${result.admin_email || "-"} 空间=${result.workspace_count}`,
    "success",
  );
  adminSessionJson.value = "";
  adminCookieHeader.value = "";
  accountsCheckHeadersText.value = "";
  showImportPanel.value = false;
  await loadAdminSessions();
  await reload();
}

async function loadAdminSessions() {
  adminSessionsLoading.value = true;
  adminSessionsError.value = "";
  try {
    adminSessions.value = await resourcesApi.teamAdminSessions();
  } catch (err) {
    adminSessionsError.value = String((err as Error).message ?? err);
  } finally {
    adminSessionsLoading.value = false;
  }
}

async function removeWorkspaceMembers(row: Record<string, unknown>, reload: () => Promise<void>) {
  const id = String(row.id || "");
  const name = String(row.name || "");
  const externalId = String(row.external_workspace_id || "");
  if (!id) return;
  const confirmed = window.confirm(
    [
      "确认剔除这个固定空间里的远端成员？",
      `空间名称：${name || "-"}`,
      `外部空间 ID：${externalId || "-"}`,
      "会跳过 account-owner / 当前管理员。",
    ].join("\n"),
  );
  if (!confirmed) return;
  removingWorkspaceId.value = id;
  try {
    const result = await resourcesApi.removeWorkspaceMembers(id, {
      confirm_remove: true,
      concurrency: 20,
      page_size: 100,
    });
    store.toast(
      "远端成员剔除完成",
      `远端总数=${result.total_members ?? 0} 目标=${result.target_count ?? 0} 成功=${result.removed_count ?? 0} 失败=${result.failed_count ?? 0} 跳过=${result.skipped_count ?? 0}`,
      Number(result.failed_count ?? 0) > 0 ? "warning" : "success",
    );
    await reload();
  } finally {
    removingWorkspaceId.value = "";
  }
}

async function revokeWorkspaceInvite(row: Record<string, unknown>, reload: () => Promise<void>) {
  const id = String(row.id || "");
  const name = String(row.name || "");
  if (!id) return;
  const confirmed = window.confirm(
    [
      "确认撤销当前团队空间的全部远端邀请？",
      `空间：${name || "-"}`,
      "只调用远端撤销邀请，不修改本地成员状态。",
    ].join("\n"),
  );
  if (!confirmed) return;
  revokingInviteWorkspaceId.value = id;
  try {
    const result = await resourcesApi.revokeWorkspaceInvite(id, {
      concurrency: 20,
      page_size: 100,
    });
    store.toast(
      "邀请撤销完成",
      `邀请=${result.invite_count ?? 0} 成功=${result.revoked_count ?? 0} 失败=${result.failed_count ?? 0}`,
      Number(result.failed_count ?? 0) > 0 ? "warning" : "success",
    );
    await reload();
  } finally {
    revokingInviteWorkspaceId.value = "";
  }
}

async function deleteAdminSession(row: Record<string, unknown>, reload: () => Promise<void>) {
  const id = String(row.id || "");
  const email = String(row.admin_email || "");
  if (!id) return;
  const confirmed = window.confirm(
    [
      "确认删除这个空间管理员及其本地关联数据？",
      `管理员邮箱：${email || "-"}`,
      `Session ID：${id}`,
      "会同时删除本地团队空间、空间成员关系、Codex 授权、批次、批次明细、下游推送记录。",
      "不会删除账号、代理、邮箱租约、任务运行日志，也不会调用远端接口。",
    ].join("\n"),
  );
  if (!confirmed) return;
  deletingAdminSessionId.value = id;
  try {
    const result = await resourcesApi.deleteTeamAdminSession(id);
    store.toast(
      "空间管理员已删除",
      `空间=${result.deleted_workspaces ?? 0} 成员=${result.deleted_memberships ?? 0} 授权=${result.deleted_credentials ?? 0} 批次=${result.deleted_batches ?? 0}`,
      "success",
    );
    await loadAdminSessions();
    await reload();
  } finally {
    deletingAdminSessionId.value = "";
  }
}

onMounted(loadAdminSessions);
</script>

<template>
  <ResourcePage
    title="团队空间"
    description="只维护已知 ChatGPT/OpenAI Team Workspace，不从 token 自动发现。"
    :columns="columns"
    :loader="resourcesApi.workspaces"
    empty-text="暂无团队空间。"
  >
    <template #actions>
      <button class="btn" @click="showImportPanel = !showImportPanel">
        {{ showImportPanel ? "收起导入" : "新增管理员导入" }}
      </button>
    </template>
    <template #before="{ reload }">
      <form v-if="showImportPanel" class="panel filter-panel admin-session-form" @submit.prevent="importAdminSession(reload)">
        <div class="panel-heading">
          <div>
            <h2>新增管理员导入</h2>
            <p>粘贴 ChatGPT 管理员 api/auth/session JSON 和 Cookie Header，系统解析可邀请 Team Workspace。</p>
          </div>
          <button class="btn" type="button" @click="showImportPanel = false">关闭</button>
        </div>
        <label class="field wide">
          <span>管理员 api/auth/session JSON</span>
          <textarea v-model="adminSessionJson" class="input textarea" required placeholder="{&quot;user&quot;:{...},&quot;account&quot;:{...},&quot;accessToken&quot;:&quot;...&quot;}"></textarea>
        </label>
        <label class="field wide">
          <span>管理员 Cookie Header（可选，accounts/check 不够时填写）</span>
          <input v-model="adminCookieHeader" class="input" placeholder="__Secure-next-auth.session-token=..." />
        </label>
        <label class="field wide">
          <span>accounts/check 浏览器请求头（可选，粘贴 DevTools Request Headers）</span>
          <textarea
            v-model="accountsCheckHeadersText"
            class="input textarea small-textarea"
            placeholder="Request URL: https://chatgpt.com/backend-api/accounts/check/v4-2023-04-27&#10;accept-language:&#10;zh-CN,zh;q=0.9&#10;cookie:&#10;...&#10;sec-ch-ua:&#10;...&#10;user-agent:&#10;..."
          ></textarea>
        </label>
        <button class="btn primary">导入管理员 Session 并解析空间</button>
      </form>

      <section class="panel admin-table-panel">
        <div class="panel-heading">
          <div>
            <h2>空间管理员</h2>
            <p>展示已导入的管理员 Session。表格字段可点击复制完整值。</p>
          </div>
          <button class="btn" @click="loadAdminSessions">刷新管理员</button>
        </div>
        <DataTable
          :columns="adminSessionColumns"
          :rows="adminSessions"
          :loading="adminSessionsLoading"
          :error="adminSessionsError"
          empty-text="暂无空间管理员。"
          @refresh="loadAdminSessions"
        >
          <template #actions="{ row }">
            <button
              class="btn danger small"
              :disabled="deletingAdminSessionId === String(row.id || '')"
              @click="deleteAdminSession(row, reload)"
            >
              {{ deletingAdminSessionId === String(row.id || "") ? "删除中..." : "删除管理员" }}
            </button>
          </template>
        </DataTable>
      </section>
    </template>
    <template #rowActions="{ row, reload }">
      <div class="row-actions">
        <button
          class="btn small"
          :disabled="revokingInviteWorkspaceId === String(row.id || '')"
          @click="revokeWorkspaceInvite(row, reload)"
        >
          {{ revokingInviteWorkspaceId === String(row.id || "") ? "撤销中..." : "撤销邀请" }}
        </button>
        <button
          class="btn danger small"
          :disabled="removingWorkspaceId === String(row.id || '')"
          @click="removeWorkspaceMembers(row, reload)"
        >
          {{ removingWorkspaceId === String(row.id || "") ? "剔除中..." : "剔除成员" }}
        </button>
      </div>
    </template>
  </ResourcePage>
</template>

<style scoped>
.admin-session-form {
  display: grid;
  gap: 12px;
}

.admin-table-panel {
  margin-bottom: 18px;
  padding: 0;
}

.panel-heading {
  align-items: center;
  border-bottom: 1px solid var(--border);
  display: flex;
  gap: 16px;
  justify-content: space-between;
  padding: 16px;
}

.panel-heading h2 {
  font-size: 16px;
  margin: 0 0 6px;
}

.panel-heading p {
  color: var(--text-muted);
  font-size: 13px;
  margin: 0;
}

.wide {
  min-width: 0;
}

.textarea {
  min-height: 150px;
  resize: vertical;
}

.row-actions {
  display: flex;
  gap: 8px;
}

.small {
  padding: 8px 10px;
  white-space: nowrap;
}

@media (max-width: 767px) {
  .panel-heading {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
