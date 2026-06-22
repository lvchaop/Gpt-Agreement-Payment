<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import ResourcePage from "../components/ResourcePage.vue";
import type { Row } from "../api/resources";
import { resourcesApi } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();
const router = useRouter();
const pageRef = ref<InstanceType<typeof ResourcePage> | null>(null);
const selectedRows = ref<Row[]>([]);
const selectedCount = ref(0);
const adminEmail = ref("");
const externalWorkspaceId = ref("");
const userEmail = ref("");
const workspace = ref("");
const membershipStatus = ref("");
const hasCodexCredential = ref("");
const sessionOtpStatus = ref("");
const acceptConcurrency = ref(50);
const codexClientId = ref("app_EMoamEEZ73f0CkXaXp7hrann");
const authConcurrency = ref(50);
const sessionOtpConcurrency = ref(50);
const sessionConcurrency = ref(10);
const workspaces = ref<Row[]>([]);
const syncWorkspaceId = ref("");
const syncPageSize = ref(100);
const sessionOtpBatchCount = computed(() => {
  const size = Math.max(1, Number(sessionOtpConcurrency.value || 1));
  return selectedCount.value > 0 ? Math.ceil(selectedCount.value / size) : 0;
});
const authBatchCount = computed(() => {
  const size = Math.max(1, Number(authConcurrency.value || 1));
  return selectedCount.value > 0 ? Math.ceil(selectedCount.value / size) : 0;
});

const columns = [
  { key: "id", label: "成员关系 ID", mono: true, summary: 28 },
  { key: "user_email", label: "账号邮箱", summary: 30 },
  { key: "admin_email", label: "管理员邮箱", summary: 30 },
  { key: "external_workspace_id", label: "外部空间 ID", mono: true, summary: 28 },
  { key: "workspace_name", label: "空间名称" },
  { key: "workspace_plan_type", label: "空间订阅类型", summary: 24 },
  { key: "membership_status", label: "成员状态", badge: true },
  { key: "has_codex_credential", label: "是否授权", badge: true },
  { key: "codex_credential_count", label: "授权数" },
  { key: "last_codex_credential_at", label: "最近授权时间", summary: 30 },
  { key: "session_otp_status", label: "验证码状态", badge: true },
  { key: "session_otp_code_len", label: "验证码长度" },
  { key: "failure_code", label: "失败码", summary: 24 },
  { key: "failure_message", label: "失败信息", summary: 36 },
];

async function loadMemberships() {
  return resourcesApi.memberships({
    admin_email: adminEmail.value,
    external_workspace_id: externalWorkspaceId.value,
    user_email: userEmail.value,
    workspace: workspace.value,
    membership_status: membershipStatus.value,
    has_codex_credential: hasCodexCredential.value,
    session_otp_status: sessionOtpStatus.value,
  });
}

function updateSelection(rows: Record<string, unknown>[]) {
  selectedRows.value = rows as Row[];
  selectedCount.value = rows.length;
}

async function reload() {
  await pageRef.value?.load();
}

async function loadWorkspaces() {
  workspaces.value = await resourcesApi.workspaces();
  if (!syncWorkspaceId.value && workspaces.value.length) {
    syncWorkspaceId.value = String(workspaces.value[0].id || "");
  }
}

async function syncRemoteState() {
  if (!syncWorkspaceId.value) {
    store.toast("缺少空间", "请先选择要同步的 Team Workspace。", "warning");
    return;
  }
  const result = await resourcesApi.syncMembershipRemoteState({
    team_workspace_id: syncWorkspaceId.value,
    page_size: syncPageSize.value,
  });
  store.toast(
    "远端同步完成",
    `远端成员=${result.remote_member_count ?? 0} 远端邀请=${result.remote_invite_count ?? 0} 剔除本地=${result.removed_local_count ?? 0}`,
    "success",
  );
  await reload();
}

async function acceptMemberships(rows: Row[]) {
  const ids = rows.map((row) => String(row.id || "")).filter(Boolean);
  if (!ids.length) {
    store.toast("未选择成员", "请先勾选要接受邀请的成员关系。", "warning");
    return;
  }
  const result = await resourcesApi.membershipAcceptInvite({
    membership_ids: ids,
    created_by: "ops-ui",
    concurrency: acceptConcurrency.value,
  });
  store.toast(
    "接受邀请执行完成",
    `work=${result.work_count} 并发=${result.concurrency} 成功=${result.succeeded} 失败=${result.failed}`,
    result.failed > 0 ? "warning" : "success",
  );
  await router.push({ name: "job-trace", params: { jobId: result.job_id } });
}

async function prepareSessionOtp(rows: Row[]) {
  const ids = rows.map((row) => String(row.id || "")).filter(Boolean);
  if (!ids.length) {
    store.toast("未选择成员", "请先勾选要获取验证码的成员。", "warning");
    return;
  }
  const result = await resourcesApi.membershipSessionOtpPrepare({
    membership_ids: ids,
    created_by: "ops-ui",
    concurrency: sessionOtpConcurrency.value,
  });
  store.toast(
    "验证码准备完成",
    `work=${result.work_count} 并发=${result.concurrency} 成功=${result.succeeded} 失败=${result.failed}`,
    result.failed > 0 ? "warning" : "success",
  );
  await router.push({ name: "job-trace", params: { jobId: result.job_id } });
}

async function submitSessionOtp(rows: Row[]) {
  const ids = rows.map((row) => String(row.id || "")).filter(Boolean);
  if (!ids.length) {
    store.toast("未选择成员", "请先勾选要提交验证码的成员。", "warning");
    return;
  }
  const result = await resourcesApi.membershipSessionOtpSubmit({
    membership_ids: ids,
    created_by: "ops-ui",
    concurrency: sessionOtpConcurrency.value,
  });
  store.toast(
    "验证码提交完成",
    `work=${result.work_count} 并发=${result.concurrency} 成功=${result.succeeded} 失败=${result.failed}`,
    result.failed > 0 ? "warning" : "success",
  );
  await router.push({ name: "job-trace", params: { jobId: result.job_id } });
}

async function buildCodexCredentials(rows: Row[]) {
  const userAccountIds = [
    ...new Set(rows.map((row) => String(row.user_account_id || "")).filter(Boolean)),
  ];
  if (!userAccountIds.length) {
    store.toast("未选择成员", "请先勾选要获取 Codex 授权的成员。", "warning");
    return;
  }
  const workspaceIds = new Set(rows.map((row) => String(row.team_workspace_id || "")).filter(Boolean));
  if (workspaceIds.size !== 1) {
    store.toast("空间不一致", "选中成员必须属于同一个团队空间。", "warning");
    return;
  }
  if (!codexClientId.value.trim()) {
    store.toast("缺少客户端", "Codex Client 不能为空。", "warning");
    return;
  }
  const result = await resourcesApi.buildCredentials({
    user_account_ids: userAccountIds,
    team_workspace_id: [...workspaceIds][0],
    codex_client_id: codexClientId.value.trim(),
    created_by: "ops-ui-memberships",
    concurrency: authConcurrency.value,
    force_reauthorize: false,
  });
  store.toast(
    "Codex 授权完成",
    `work=${result.work_count} 并发=${result.concurrency} 成功=${result.succeeded} 失败=${result.failed}`,
    result.failed > 0 ? "warning" : "success",
  );
  await router.push({ name: "job-trace", params: { jobId: result.job_id } });
}

async function backfillSessionForMemberships(rows: Row[]) {
  const ids = Array.from(new Set(rows.map((row) => String(row.user_account_id || "")).filter(Boolean)));
  if (!ids.length) {
    store.toast("未选择成员", "请先勾选要补 Session 的成员关系。", "warning");
    return;
  }
  const result = await resourcesApi.backfillSession({
    user_account_ids: ids,
    created_by: "ops-ui",
    concurrency: sessionConcurrency.value,
  });
  store.toast(
    "补 Session 执行完成",
    `账号=${ids.length} work=${result.work_count} 并发=${result.concurrency} 成功=${result.succeeded} 失败=${result.failed}`,
    result.failed > 0 ? "warning" : "success",
  );
  await router.push({ name: "job-trace", params: { jobId: result.job_id } });
}

async function acceptOne(row: Row) {
  await acceptMemberships([row]);
}

async function backfillSessionOne(row: Row) {
  await backfillSessionForMemberships([row]);
}

onMounted(loadWorkspaces);
</script>

<template>
  <ResourcePage
    ref="pageRef"
    title="空间成员"
    description="账号与 Team Workspace 的当前关系、邀请状态和接受邀请动作。"
    :columns="columns"
    :loader="loadMemberships"
    empty-text="暂无成员关系。"
    selectable
    @selection-change="updateSelection"
  >
    <template #actionCards>
      <section class="panel action-card">
        <div class="action-heading">
          <div>
            <h2>筛选条件</h2>
            <p>只放表格查询条件，不放业务动作。</p>
          </div>
          <button class="btn" @click="reload">筛选</button>
        </div>
        <div class="filter-grid">
          <label class="field">
            <span>管理员邮箱</span>
            <input v-model="adminEmail" class="input" placeholder="按管理员邮箱筛选" @keyup.enter="reload" />
          </label>
          <label class="field">
            <span>账号邮箱</span>
            <input v-model="userEmail" class="input" placeholder="按账号邮箱筛选" @keyup.enter="reload" />
          </label>
          <label class="field">
            <span>外部空间 ID</span>
            <input
              v-model="externalWorkspaceId"
              class="input"
              placeholder="按 external_workspace_id 筛选"
              @keyup.enter="reload"
            />
          </label>
          <label class="field">
            <span>空间</span>
            <select v-model="workspace" class="select">
              <option value="">全部空间</option>
              <option v-for="item in workspaces" :key="String(item.id)" :value="String(item.id)">
                {{ item.name || item.id }} / {{ item.external_workspace_id || "" }}
              </option>
            </select>
          </label>
          <label class="field">
            <span>成员状态</span>
            <select v-model="membershipStatus" class="select">
              <option value="">全部</option>
              <option value="unknown">unknown</option>
              <option value="invited">invited</option>
              <option value="accepted">accepted</option>
              <option value="active">active</option>
              <option value="left">left</option>
              <option value="disabled">disabled</option>
              <option value="banned">banned</option>
              <option value="failed">failed</option>
            </select>
          </label>
          <label class="field">
            <span>是否授权</span>
            <select v-model="hasCodexCredential" class="select">
              <option value="">全部</option>
              <option value="yes">已授权</option>
              <option value="no">未授权</option>
            </select>
          </label>
          <label class="field">
            <span>验证码状态</span>
            <select v-model="sessionOtpStatus" class="select">
              <option value="">全部</option>
              <option value="otp_collected">otp_collected</option>
              <option value="otp_pending">otp_pending</option>
              <option value="otp_validated">otp_validated</option>
              <option value="otp_missing">otp_missing</option>
              <option value="failed">failed</option>
            </select>
          </label>
        </div>
      </section>

      <section class="panel action-card">
        <div class="action-heading">
          <div>
            <h2>Codex 授权</h2>
            <p>对选中的成员账号，在其所属空间生成 Codex 授权。</p>
          </div>
          <span class="selected-hint">已选 {{ selectedCount }} 条</span>
        </div>
        <div class="action-row">
          <label class="inline-control wide-control">
            <span>Codex Client</span>
            <input v-model="codexClientId" class="input" />
          </label>
          <label class="inline-control">
            <span>授权并发</span>
            <input v-model.number="authConcurrency" class="input small-input" type="number" min="1" max="500" />
          </label>
          <button class="btn primary" :disabled="selectedCount === 0" @click="buildCodexCredentials(selectedRows)">
            获取授权（{{ selectedCount }}）
          </button>
          <span class="operation-hint">
            预计 {{ authBatchCount }} 批；选中成员必须属于同一个团队空间。
          </span>
        </div>
      </section>

      <section class="panel action-card">
        <div class="action-heading">
          <div>
            <h2>验证码两阶段</h2>
            <p>第一阶段获取邮箱验证码并保存快照；第二阶段读取快照并同步提交验证码。</p>
          </div>
          <span class="selected-hint">已选 {{ selectedCount }} 条</span>
        </div>
        <div class="action-row">
          <label class="inline-control">
            <span>阶段并发</span>
            <input v-model.number="sessionOtpConcurrency" class="input small-input" type="number" min="1" max="500" />
          </label>
          <button class="btn" :disabled="selectedCount === 0" @click="prepareSessionOtp(selectedRows)">
            获取验证码（{{ selectedCount }}）
          </button>
          <button class="btn primary" :disabled="selectedCount === 0" @click="submitSessionOtp(selectedRows)">
            提交验证码（{{ selectedCount }}）
          </button>
          <span class="operation-hint">
            预计 {{ sessionOtpBatchCount }} 批；提交阶段会在真正 validate 前等待同批次就绪。
          </span>
        </div>
      </section>

      <section class="panel action-card">
        <div class="action-heading">
          <div>
            <h2>接受邀请</h2>
            <p>对选中的成员关系执行接受邀请。</p>
          </div>
          <span class="selected-hint">已选 {{ selectedCount }} 条</span>
        </div>
        <div class="action-row">
          <label class="inline-control">
            <span>接受并发</span>
            <input v-model.number="acceptConcurrency" class="input small-input" type="number" min="1" max="500" />
          </label>
          <button class="btn primary" :disabled="selectedCount === 0" @click="acceptMemberships(selectedRows)">
            接受选中邀请（{{ selectedCount }}）
          </button>
        </div>
      </section>

      <section class="panel action-card">
        <div class="action-heading">
          <div>
            <h2>补 Session</h2>
            <p>按选中成员提取账号 ID，复用账号补 Session 流程。</p>
          </div>
          <span class="selected-hint">已选 {{ selectedCount }} 条</span>
        </div>
        <div class="action-row">
          <label class="inline-control">
            <span>补 Session 并发</span>
            <input v-model.number="sessionConcurrency" class="input small-input" type="number" min="1" max="500" />
          </label>
          <button class="btn" :disabled="selectedCount === 0" @click="backfillSessionForMemberships(selectedRows)">
            补选中 Session（{{ selectedCount }}）
          </button>
        </div>
      </section>

      <section class="panel action-card">
        <div class="action-heading">
          <div>
            <h2>远端同步</h2>
            <p>读取远端成员和邀请，剔除本地不存在于远端的数据。</p>
          </div>
        </div>
        <div class="action-row">
          <label class="inline-control wide-control">
            <span>同步空间</span>
            <select v-model="syncWorkspaceId" class="select">
              <option value="">请选择</option>
              <option v-for="item in workspaces" :key="String(item.id)" :value="String(item.id)">
                {{ item.name || item.id }} / {{ item.external_workspace_id || "" }}
              </option>
            </select>
          </label>
          <label class="inline-control">
            <span>同步分页</span>
            <input v-model.number="syncPageSize" class="input small-input" type="number" min="1" max="200" />
          </label>
          <button class="btn danger" :disabled="!syncWorkspaceId" @click="syncRemoteState">
            同步远端成员和邀请，并剔除本地
          </button>
        </div>
      </section>
    </template>
    <template #rowActions="{ row }">
      <div class="row-actions">
        <button class="btn small" @click="acceptOne(row)">接受邀请</button>
        <button class="btn small" @click="backfillSessionOne(row)">补 Session</button>
      </div>
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
  align-items: center;
  border-bottom: 1px solid var(--border);
  display: flex;
  gap: 12px;
  justify-content: space-between;
  padding: 14px 16px;
}

.action-heading h2 {
  font-size: 14px;
  letter-spacing: -0.01em;
  margin: 0;
}

.action-heading p {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.45;
  margin: 5px 0 0;
}

.filter-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(4, minmax(180px, 1fr));
  padding: 14px 16px 16px;
}

.action-row {
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
  white-space: nowrap;
}

.operation-hint {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.4;
}

.wide-control {
  min-width: min(520px, 100%);
}

.small {
  padding: 8px 10px;
  white-space: nowrap;
}

.row-actions {
  display: flex;
  gap: 8px;
}

@media (max-width: 980px) {
  .filter-grid {
    grid-template-columns: 1fr;
  }

  .action-heading,
  .action-row {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
