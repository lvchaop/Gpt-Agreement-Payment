<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { Expand, KeyRound, Plus, Power, PowerOff, RefreshCw, Trash2 } from "@lucide/vue";

import DataTable from "../components/DataTable.vue";
import type { Column, TableFilter } from "../components/DataTable.vue";
import ConfirmModal from "../components/ConfirmModal.vue";
import FormDrawer from "../components/FormDrawer.vue";
import EntitySelect from "../components/EntitySelect.vue";
import ResourcePage from "../components/ResourcePage.vue";
import { resourcesApi, type Row } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();
const router = useRouter();
const pageRef = ref<InstanceType<typeof ResourcePage> | null>(null);
const adminSessionJson = ref("");
const adminCookieHeader = ref("");
const accountsCheckHeadersText = ref("");
const showImportPanel = ref(false);
const showCredentialPanel = ref(false);
const adminSessions = ref<Record<string, unknown>[]>([]);
const adminSessionsLoading = ref(false);
const adminSessionsError = ref("");
const deletingAdminSessionId = ref("");
const credentialUserAccountIds = ref<string[]>([]);
const credentialExternalSpaceId = ref("");
const credentialSessionAccessToken = ref("");
const credentialCookieHeader = ref("");
const credentialSpaceName = ref("");
const credentialOwnerUserAccountId = ref("");
const credentialSourceAdminSessionId = ref("");
const credentialNamePrefix = ref("codex");
const syncingSpaceId = ref("");
const deleteAdminTarget = ref<Row | null>(null);
const syncTarget = ref<Row | null>(null);
const seatExpansionTarget = ref<Row | null>(null);
const statusTarget = ref<Row | null>(null);
const expandingSpaceId = ref("");
const updatingSpaceStatusId = ref("");
const importing = ref(false);
const creatingCredential = ref(false);
const accountLoader = async (query: string) => (await resourcesApi.accountOptions(query)).items;
const businessSpaceLoader = async (query: string) => {
  const result = await resourcesApi.spaces({ q: query, space_type: "business", page_size: 30, sort: "name" });
  return result.items.map((item) => ({
    value: String(item.external_space_id || ""),
    label: String(item.name || item.external_space_id || item.id),
    description: String(item.external_space_id || ""),
    status: String(item.space_status || ""),
  })).filter((item) => item.value);
};

const columns: Column[] = [
  { key: "id", label: "空间 ID", mono: true, summary: 26 },
  { key: "name", label: "名称" },
  { key: "external_space_id", label: "外部空间 ID", mono: true, summary: 26 },
  { key: "space_type", label: "空间类型", badge: true },
  { key: "plan_type", label: "订阅类型", badge: true, sortable: true },
  { key: "last_session_refresh_at", label: "最近 Session 时间", type: "datetime", relativeTime: true, sortable: true },
  { key: "credential_type", label: "凭证类型", badge: true },
  { key: "auth_mode", label: "授权模式", badge: true },
  { key: "provider", label: "来源" },
  { key: "seat_limit", label: "席位上限" },
  { key: "space_status", label: "状态", badge: true },
  { key: "source_admin_session_id", label: "管理员 Session", mono: true, summary: 26 },
];

const filters: TableFilter[] = [
  {
    key: "space_type",
    label: "空间类型",
    options: [
      { label: "personal", value: "personal" },
      { label: "business", value: "business" },
    ],
  },
  {
    key: "credential_type",
    label: "凭证类型",
    options: [
      { label: "personal_account", value: "personal_account" },
      { label: "team_5h_weekly", value: "team_5h_weekly" },
      { label: "team_monthly", value: "team_monthly" },
    ],
  },
  {
    key: "plan_type",
    label: "订阅类型",
    options: [
      { label: "Free", value: "free" },
      { label: "Plus", value: "plus" },
      { label: "Pro", value: "pro" },
    ],
  },
  {
    key: "session_recency",
    label: "最近 Session 时间",
    options: [
      { label: "6 小时内", value: "within_6h" },
      { label: "12 小时内", value: "within_12h" },
      { label: "1 天内", value: "within_1d" },
      { label: "2 天内", value: "within_2d" },
      { label: "3 天内", value: "within_3d" },
      { label: "7 天内", value: "within_7d" },
      { label: "从未获取", value: "never" },
    ],
  },
  {
    key: "auth_mode",
    label: "授权模式",
    options: [
      { label: "codex_oauth", value: "codex_oauth" },
      { label: "backend_access_token", value: "backend_access_token" },
    ],
  },
  {
    key: "space_status",
    label: "状态",
    options: [
      { label: "unknown", value: "unknown" },
      { label: "active", value: "active" },
      { label: "disabled", value: "disabled" },
      { label: "expired", value: "expired" },
      { label: "error", value: "error" },
    ],
  },
  {
    key: "provider",
    label: "来源",
    options: [
      { label: "openai_chatgpt", value: "openai_chatgpt" },
    ],
  },
];

const adminSessionColumns = [
  { key: "id", label: "Session ID", mono: true, summary: 26 },
  { key: "admin_email", label: "管理员邮箱", mono: true, summary: 34 },
  { key: "expires_at", label: "Cookie/Session 过期时间", mono: true, summary: 30 },
  { key: "imported_at", label: "导入/更新时间", mono: true, summary: 30 },
];

async function importAdminSession() {
  let raw: Record<string, unknown>;
  try {
    raw = JSON.parse(adminSessionJson.value);
  } catch {
    store.toast("JSON 格式错误", "请粘贴完整 api/auth/session JSON。", "error");
    return;
  }
  importing.value = true;
  try {
    const result = await resourcesApi.importTeamAdminSession({
      raw_session_json: raw,
      cookie_header: adminCookieHeader.value,
      accounts_check_headers_text: accountsCheckHeadersText.value,
      fetch_accounts_check: true,
    });
    store.toast("管理员 Session 已导入", `管理员=${result.admin_email || "-"} 空间=${result.space_count}`, "success");
    adminSessionJson.value = "";
    adminCookieHeader.value = "";
    accountsCheckHeadersText.value = "";
    showImportPanel.value = false;
    await loadAdminSessions();
    await pageRef.value?.load();
  } catch (err) {
    store.toast("导入失败", String((err as Error).message ?? err), "error");
  } finally { importing.value = false; }
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

async function deleteAdminSession() {
  const id = String(deleteAdminTarget.value?.id || "");
  if (!id) return;
  deletingAdminSessionId.value = id;
  try {
    const result = await resourcesApi.deleteTeamAdminSession(id);
    store.toast(
      "空间管理员已删除",
      `账号检查=${result.deleted_account_checks ?? 0} 代理绑定=${result.deleted_admin_proxy_bindings ?? 0}`,
      "success",
    );
    deleteAdminTarget.value = null;
    await loadAdminSessions();
    await pageRef.value?.load();
  } finally {
    deletingAdminSessionId.value = "";
  }
}

async function createBusinessCredentials() {
  const userAccountIds = credentialUserAccountIds.value;
  if (!userAccountIds.length) {
    store.toast("缺少账号", "请填写 user_account_id，多个用换行或逗号分隔。", "warning");
    return;
  }
  if (!credentialExternalSpaceId.value.trim()) {
    store.toast("缺少空间 ID", "请填写 Business Space 的 chatgpt-account-id。", "warning");
    return;
  }
  if (!credentialCookieHeader.value.trim()) {
    store.toast("缺少 Cookie Header", "创建 Business AT 需要成员账号当前登录 Cookie。", "warning");
    return;
  }
  creatingCredential.value = true;
  try {
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
    });
    store.toast("Business Access Token 创建完成", `work=${result.work_count} 成功=${result.succeeded} 失败=${result.failed}`, result.failed > 0 ? "warning" : "success");
    showCredentialPanel.value = false;
    await pageRef.value?.load();
    await router.push({ name: "job-trace", params: { jobId: result.job_id } });
  } catch (err) {
    store.toast("创建凭证失败", String((err as Error).message ?? err), "error");
  } finally { creatingCredential.value = false; }
}

async function syncRemoteMemberships() {
  const id = String(syncTarget.value?.id || "");
  if (!id) return;
  syncingSpaceId.value = id;
  try {
    const result = await resourcesApi.syncRemoteSpaceMemberships(id, { page_size: 100 });
    store.toast(
      "远端成员同步完成",
      `active=${result.synced_active_count ?? 0} invited=${result.synced_invited_count ?? 0} 剔除=${result.deleted_stale_count ?? 0}`,
      "success",
    );
    syncTarget.value = null;
    await pageRef.value?.load();
  } catch (err) {
    store.toast("同步失败", String((err as Error).message ?? err), "error");
  } finally {
    syncingSpaceId.value = "";
  }
}

async function expandSeats() {
  const id = String(seatExpansionTarget.value?.id || "");
  if (!id) return;
  expandingSpaceId.value = id;
  try {
    const result = await resourcesApi.expandSpaceSeats(id, {
      work_count: 1,
      created_by: "ops:space-seat-expand",
    });
    store.toast("扩席位 Job 已创建", `目标席位=999，Work=${result.queued ?? 0}`, "success");
    seatExpansionTarget.value = null;
    await pageRef.value?.load();
    if (result.job_id) await router.push({ name: "job-trace", params: { jobId: result.job_id } });
  } catch (err) {
    store.toast("扩席位 Job 创建失败", String((err as Error).message ?? err), "error");
  } finally {
    expandingSpaceId.value = "";
  }
}

async function updateSpaceStatus() {
  const id = String(statusTarget.value?.id || "");
  if (!id) return;
  const currentStatus = String(statusTarget.value?.space_status || "");
  const nextStatus = currentStatus === "disabled" ? "active" : "disabled";
  updatingSpaceStatusId.value = id;
  try {
    await resourcesApi.patchSpace(id, { space_status: nextStatus });
    store.toast(
      nextStatus === "disabled" ? "空间已禁用" : "空间已启用",
      String(statusTarget.value?.name || statusTarget.value?.external_space_id || id),
      "success",
    );
    statusTarget.value = null;
    await pageRef.value?.load();
  } catch (err) {
    store.toast("状态更新失败", String((err as Error).message ?? err), "error");
  } finally {
    updatingSpaceStatusId.value = "";
  }
}

onMounted(loadAdminSessions);
</script>

<template>
  <ResourcePage
    ref="pageRef"
    title="空间"
    description="系统只有一套 Space 逻辑：个人空间和 Business 空间统一展示。"
    :columns="columns"
    :loader="resourcesApi.spaces"
    :filters="filters"
    empty-text="暂无空间。"
  >
    <template #actions>
      <button class="btn primary" @click="showCredentialPanel = true"><KeyRound :size="16" />创建 Business AT</button>
      <button class="btn" @click="showImportPanel = true"><Plus :size="16" />导入空间管理员</button>
    </template>
    <template #before>
      <section class="admin-table-panel">
        <div class="panel-heading">
          <div>
            <h2>空间管理员</h2>
            <p>已导入的管理员 Session 与有效期。</p>
          </div>
          <button class="icon-btn labeled" @click="loadAdminSessions"><RefreshCw :size="15" />刷新</button>
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
              @click="deleteAdminTarget = row"
            >
              <Trash2 :size="14" />删除
            </button>
          </template>
        </DataTable>
      </section>
    </template>
    <template #rowActions="{ row }">
      <div class="row-actions">
        <button
          v-if="String(row.space_type || '') === 'business'"
          class="btn small"
          :disabled="String(row.space_status || '') !== 'active' || syncingSpaceId === String(row.id || '')"
          @click.stop="syncTarget = row"
        >
          {{ syncingSpaceId === String(row.id || "") ? "同步中..." : "同步远端成员" }}
        </button>
        <button
          v-if="String(row.space_type || '') === 'business'"
          class="btn small"
          :disabled="String(row.space_status || '') !== 'active' || expandingSpaceId === String(row.id || '')"
          title="创建扩席位 Job，固定扩到 999 席位"
          @click.stop="seatExpansionTarget = row"
        >
          <Expand :size="14" />扩到 999 席位
        </button>
        <button
          v-if="['active', 'disabled'].includes(String(row.space_status || ''))"
          class="btn small"
          :class="{ danger: String(row.space_status || '') === 'active' }"
          :disabled="updatingSpaceStatusId === String(row.id || '')"
          @click.stop="statusTarget = row"
        >
          <PowerOff v-if="String(row.space_status || '') === 'active'" :size="14" />
          <Power v-else :size="14" />
          {{ String(row.space_status || '') === 'active' ? '禁用' : '启用' }}
        </button>
      </div>
    </template>
  </ResourcePage>

  <FormDrawer :open="showCredentialPanel" title="创建 Business Access Token" description="为已加入 Business 空间的成员创建空间凭证。" submit-text="创建凭证 Job" :busy="creatingCredential" width="wide" @close="showCredentialPanel = false" @submit="createBusinessCredentials">
    <label class="field"><span>成员账号</span><EntitySelect v-model="credentialUserAccountIds" :loader="accountLoader" multiple placeholder="按邮箱搜索并添加账号" /></label>
    <label class="field"><span>Business 空间</span><EntitySelect v-model="credentialExternalSpaceId" :loader="businessSpaceLoader" placeholder="按空间名称或外部 ID 搜索" /></label>
    <label class="field"><span>成员 Cookie Header</span><textarea v-model="credentialCookieHeader" class="textarea compact-textarea" required /></label>
    <details><summary>兼容字段</summary><div class="drawer-grid">
      <label class="field wide"><span>成员 session access_token</span><textarea v-model="credentialSessionAccessToken" class="textarea compact-textarea" /></label>
      <label class="field"><span>空间名称</span><input v-model="credentialSpaceName" class="input" /></label>
      <label class="field"><span>Owner 账号</span><EntitySelect v-model="credentialOwnerUserAccountId" :loader="accountLoader" placeholder="按邮箱搜索" /></label>
      <label class="field"><span>空间管理员</span><select v-model="credentialSourceAdminSessionId" class="select"><option value="">不指定</option><option v-for="admin in adminSessions" :key="String(admin.id)" :value="String(admin.id)">{{ admin.admin_email }}</option></select></label>
      <label class="field"><span>凭证名前缀</span><input v-model="credentialNamePrefix" class="input" /></label>
    </div></details>
  </FormDrawer>

  <FormDrawer :open="showImportPanel" title="导入空间管理员" description="导入管理员 Session 并解析 Business 空间；此时不创建成员。" submit-text="导入并解析" :busy="importing" width="wide" @close="showImportPanel = false" @submit="importAdminSession">
    <label class="field"><span>api/auth/session JSON</span><textarea v-model="adminSessionJson" class="textarea large-textarea" required /></label>
    <label class="field"><span>Cookie Header（可选）</span><textarea v-model="adminCookieHeader" class="textarea compact-textarea" /></label>
    <label class="field"><span>accounts/check 请求头（可选）</span><textarea v-model="accountsCheckHeadersText" class="textarea large-textarea" /></label>
  </FormDrawer>

  <ConfirmModal :open="Boolean(deleteAdminTarget)" title="删除空间管理员及关联空间" message="会删除该管理员、本地空间、空间成员和空间凭证；保留任务与推送记录，不调用远端删除。" :summary="{ '管理员邮箱': deleteAdminTarget?.admin_email, 'Session ID': deleteAdminTarget?.id }" confirm-text="确认删除" danger :busy="Boolean(deletingAdminSessionId)" @close="deleteAdminTarget = null" @confirm="deleteAdminSession" />
  <ConfirmModal :open="Boolean(syncTarget)" title="同步远端成员" message="读取远端 users 和 invites 后覆盖本地成员关系；本地存在但远端不存在的该空间成员关系会被物理删除，不会发送邀请。" :summary="{ '空间': syncTarget?.name, '外部空间 ID': syncTarget?.external_space_id }" confirm-text="开始同步" :busy="Boolean(syncingSpaceId)" @close="syncTarget = null" @confirm="syncRemoteMemberships" />
  <ConfirmModal :open="Boolean(seatExpansionTarget)" title="扩到 999 席位" message="使用该空间管理员登录态和静态住宅代理，分阶段提交席位更新并读取远端结果确认。" :summary="{ '空间': seatExpansionTarget?.name, '外部空间 ID': seatExpansionTarget?.external_space_id, '当前席位': seatExpansionTarget?.seats_entitled }" confirm-text="创建扩席位 Job" :busy="Boolean(expandingSpaceId)" @close="seatExpansionTarget = null" @confirm="expandSeats" />
  <ConfirmModal
    :open="Boolean(statusTarget)"
    :title="String(statusTarget?.space_status || '') === 'disabled' ? '启用空间' : '禁用空间'"
    :message="String(statusTarget?.space_status || '') === 'disabled' ? '启用后该空间会重新进入邀请、授权、推送、回收和扩席位流程。' : '禁用后保留空间、成员、凭证和历史记录，但不再进入邀请、授权、推送、回收、扩席位和新的号池下载流程。'"
    :summary="{ '空间': statusTarget?.name, '外部空间 ID': statusTarget?.external_space_id, '凭证类型': statusTarget?.credential_type }"
    :confirm-text="String(statusTarget?.space_status || '') === 'disabled' ? '确认启用' : '确认禁用'"
    :danger="String(statusTarget?.space_status || '') === 'active'"
    :busy="Boolean(updatingSpaceStatusId)"
    @close="statusTarget = null"
    @confirm="updateSpaceStatus"
  />
</template>

<style scoped>
.admin-session-form {
  display: grid;
  gap: 12px;
}

.admin-table-panel { display: grid; gap: 8px; margin-bottom: 12px; }

.panel-heading {
  align-items: center;
  display: flex;
  gap: 16px;
  justify-content: space-between;
  padding: 0 2px;
}

.panel-heading h2 {
  font-size: 13px;
  margin: 0 0 3px;
}

.panel-heading p {
  color: var(--text-muted);
  font-size: 11px;
  margin: 0;
}

.wide {
  min-width: 0;
}

.large-textarea { min-height: 220px; }.compact-textarea { min-height: 82px; }
.drawer-grid { display: grid; gap: 10px; grid-template-columns: repeat(2, minmax(0, 1fr)); margin-top: 10px; }.drawer-grid .wide { grid-column: 1 / -1; }
details { border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px; }summary { color: var(--text-muted); cursor: pointer; font-size: 12px; font-weight: 700; }

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
