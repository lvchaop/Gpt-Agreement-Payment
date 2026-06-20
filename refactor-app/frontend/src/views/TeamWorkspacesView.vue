<script setup lang="ts">
import { onMounted, ref } from "vue";

import DataTable from "../components/DataTable.vue";
import ResourcePage from "../components/ResourcePage.vue";
import { resourcesApi } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();
const adminSessionJson = ref("");
const adminCookieHeader = ref("");
const showImportPanel = ref(false);
const adminSessions = ref<Record<string, unknown>[]>([]);
const adminSessionsLoading = ref(false);
const adminSessionsError = ref("");

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
    fetch_accounts_check: true,
  });
  store.toast(
    "管理员 Session 已导入",
    `管理员=${result.admin_email || "-"} 空间=${result.workspace_count}`,
    "success",
  );
  adminSessionJson.value = "";
  adminCookieHeader.value = "";
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
        />
      </section>
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

@media (max-width: 767px) {
  .panel-heading {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
