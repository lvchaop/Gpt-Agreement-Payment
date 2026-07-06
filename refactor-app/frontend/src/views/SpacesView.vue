<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import DataTable from "../components/DataTable.vue";
import ResourcePage from "../components/ResourcePage.vue";
import { resourcesApi } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();
const router = useRouter();
const adminSessionJson = ref("");
const adminCookieHeader = ref("");
const accountsCheckHeadersText = ref("");
const showImportPanel = ref(false);
const showCredentialPanel = ref(false);
const adminSessions = ref<Record<string, unknown>[]>([]);
const adminSessionsLoading = ref(false);
const adminSessionsError = ref("");
const deletingAdminSessionId = ref("");
const credentialUserAccountIds = ref("");
const credentialExternalSpaceId = ref("");
const credentialSessionAccessToken = ref("");
const credentialCookieHeader = ref("");
const credentialSpaceName = ref("");
const credentialOwnerUserAccountId = ref("");
const credentialSourceAdminSessionId = ref("");
const credentialNamePrefix = ref("codex");
const credentialConcurrency = ref(5);

const columns = [
  { key: "id", label: "空间 ID", mono: true, summary: 26 },
  { key: "name", label: "名称" },
  { key: "external_space_id", label: "外部空间 ID", mono: true, summary: 26 },
  { key: "space_type", label: "空间类型", badge: true },
  { key: "credential_type", label: "凭证类型", badge: true },
  { key: "auth_mode", label: "授权模式", badge: true },
  { key: "provider", label: "来源" },
  { key: "plan_type", label: "套餐" },
  { key: "seat_limit", label: "席位上限" },
  { key: "space_status", label: "状态", badge: true },
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
    `管理员=${result.admin_email || "-"} 空间=${result.space_count}`,
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

async function deleteAdminSession(row: Record<string, unknown>, reload: () => Promise<void>) {
  const id = String(row.id || "");
  const email = String(row.admin_email || "");
  if (!id) return;
  const confirmed = window.confirm(
    [
      "确认删除这个空间管理员及其本地关联数据？",
      `管理员邮箱：${email || "-"}`,
      `Session ID：${id}`,
      "会删除该管理员 Session 的本地关联数据。",
      "不会删除账号、代理、邮箱租约、任务运行日志，也不会调用远端接口。",
    ].join("\n"),
  );
  if (!confirmed) return;
  deletingAdminSessionId.value = id;
  try {
    const result = await resourcesApi.deleteTeamAdminSession(id);
    store.toast(
      "空间管理员已删除",
      `账号检查=${result.deleted_account_checks ?? 0} 代理绑定=${result.deleted_admin_proxy_bindings ?? 0}`,
      "success",
    );
    await loadAdminSessions();
    await reload();
  } finally {
    deletingAdminSessionId.value = "";
  }
}

function parseIds(value: string) {
  return value
    .split(/[\n,，\\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

async function createBusinessCredentials(reload: () => Promise<void>) {
  const userAccountIds = parseIds(credentialUserAccountIds.value);
  if (!userAccountIds.length) {
    store.toast("缺少账号", "请填写 user_account_id，多个用换行或逗号分隔。", "warning");
    return;
  }
  if (!credentialExternalSpaceId.value.trim()) {
    store.toast("缺少空间 ID", "请填写 Business Space 的 chatgpt-account-id。", "warning");
    return;
  }
  if (!credentialSessionAccessToken.value.trim()) {
    store.toast("缺少 Session Access Token", "请填写管理员登录后的 session access_token。", "warning");
    return;
  }
  const result = await resourcesApi.createBusinessAccessTokenCredentials({
    user_account_ids: userAccountIds,
    external_space_id: credentialExternalSpaceId.value.trim(),
    session_access_token: credentialSessionAccessToken.value.trim(),
    cookie_header: credentialCookieHeader.value,
    space_name: credentialSpaceName.value,
    owner_user_account_id: credentialOwnerUserAccountId.value,
    source_admin_session_id: credentialSourceAdminSessionId.value,
    credential_name_prefix: credentialNamePrefix.value || "codex",
    created_by: "ops-ui-space",
    concurrency: credentialConcurrency.value,
  });
  store.toast(
    "Business Access Token 创建完成",
    `work=${result.work_count} 成功=${result.succeeded} 失败=${result.failed}`,
    result.failed > 0 ? "warning" : "success",
  );
  await reload();
  await router.push({ name: "job-trace", params: { jobId: result.job_id } });
}

onMounted(loadAdminSessions);
</script>

<template>
  <ResourcePage
    title="空间"
    description="系统只有一套 Space 逻辑：个人空间和 Business 空间统一展示。"
    :columns="columns"
    :loader="resourcesApi.spaces"
    empty-text="暂无空间。"
  >
    <template #actions>
      <button class="btn primary" @click="showCredentialPanel = !showCredentialPanel">
        {{ showCredentialPanel ? "收起创建凭证" : "创建 Business AT 凭证" }}
      </button>
      <button class="btn" @click="showImportPanel = !showImportPanel">
        {{ showImportPanel ? "收起导入" : "新增管理员导入" }}
      </button>
    </template>
    <template #before="{ reload }">
      <form
        v-if="showCredentialPanel"
        class="panel filter-panel admin-session-form"
        @submit.prevent="createBusinessCredentials(reload)"
      >
        <div class="panel-heading">
          <div>
            <h2>创建 Business Access Token 凭证</h2>
            <p>触发新流程：用管理员 session access_token 调 WHAM auth-credentials，按 usage 推导 credential_type，再写入 Space 凭证。</p>
          </div>
          <button class="btn" type="button" @click="showCredentialPanel = false">关闭</button>
        </div>
        <label class="field wide">
          <span>user_account_id 列表</span>
          <textarea v-model="credentialUserAccountIds" class="input textarea small-textarea" required placeholder="每行一个 user_account_id，或用逗号分隔"></textarea>
        </label>
        <label class="field wide">
          <span>Business Space chatgpt-account-id</span>
          <input v-model="credentialExternalSpaceId" class="input" required placeholder="例如 acct_xxx / UUID" />
        </label>
        <label class="field wide">
          <span>管理员 session access_token</span>
          <textarea v-model="credentialSessionAccessToken" class="input textarea small-textarea" required placeholder="登录后拿到的 session access_token"></textarea>
        </label>
        <label class="field wide">
          <span>管理员 Cookie Header（可选）</span>
          <input v-model="credentialCookieHeader" class="input" placeholder="__Secure-next-auth.session-token=..." />
        </label>
        <label class="field">
          <span>空间名称（可选）</span>
          <input v-model="credentialSpaceName" class="input" placeholder="Business 空间展示名" />
        </label>
        <label class="field">
          <span>Owner user_account_id（可选）</span>
          <input v-model="credentialOwnerUserAccountId" class="input" placeholder="空间 owner 账号 ID" />
        </label>
        <label class="field">
          <span>source_admin_session_id（可选）</span>
          <input v-model="credentialSourceAdminSessionId" class="input" placeholder="已导入管理员 Session ID" />
        </label>
        <label class="field">
          <span>凭证名前缀</span>
          <input v-model="credentialNamePrefix" class="input" placeholder="codex" />
        </label>
        <label class="field">
          <span>并发</span>
          <input v-model.number="credentialConcurrency" class="input small-input" type="number" min="1" max="500" />
        </label>
        <button class="btn primary">创建凭证 Job</button>
      </form>

      <form v-if="showImportPanel" class="panel filter-panel admin-session-form" @submit.prevent="importAdminSession(reload)">
        <div class="panel-heading">
          <div>
            <h2>新增管理员导入</h2>
            <p>粘贴 ChatGPT 管理员 api/auth/session JSON 和 Cookie Header，只导入 admin session 与 Business 候选信息；不提前写 Space。</p>
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
