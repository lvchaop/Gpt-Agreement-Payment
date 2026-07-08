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
const externalSpaceId = ref("");
const userEmail = ref("");
const spaceFilter = ref("");
const membershipStatus = ref("");
const hasSpaceCredential = ref("");
const sessionAccountDetected = ref("");
const sessionOtpStatus = ref("");
const sessionWorkCount = ref(10);
const spaces = ref<Row[]>([]);
const selectedAccountCount = computed(() =>
  new Set(selectedRows.value.map((row) => String(row.user_account_id || "")).filter(Boolean)).size,
);

const columns = [
  { key: "id", label: "成员关系 ID", mono: true, summary: 28 },
  { key: "user_email", label: "账号邮箱", summary: 30 },
  { key: "admin_email", label: "管理员邮箱", summary: 30 },
  { key: "external_space_id", label: "外部空间 ID", mono: true, summary: 28 },
  { key: "space_name", label: "空间名称" },
  { key: "space_plan_type", label: "空间订阅类型", summary: 24 },
  { key: "membership_status", label: "成员状态", badge: true },
  { key: "session_account_detected", label: "Session识别空间", badge: true },
  { key: "has_space_credential", label: "是否有空间凭证", badge: true },
  { key: "session_otp_status", label: "验证码状态", badge: true },
  { key: "session_otp_code_len", label: "验证码长度" },
  { key: "failure_code", label: "失败码", summary: 24 },
  { key: "failure_message", label: "失败信息", summary: 36 },
];

async function loadMemberships() {
  return resourcesApi.memberships({
    admin_email: adminEmail.value,
    external_space_id: externalSpaceId.value,
    user_email: userEmail.value,
    space_id: spaceFilter.value,
    membership_status: membershipStatus.value,
    session_account_detected: sessionAccountDetected.value,
    has_space_credential: hasSpaceCredential.value,
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

async function loadSpaces() {
  spaces.value = await resourcesApi.spaces();
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
    work_count: sessionWorkCount.value,
  });
  store.toast(
    "补 Session 执行完成",
    `账号=${ids.length} work=${result.work_count} 成功=${result.succeeded} 失败=${result.failed}`,
    result.failed > 0 ? "warning" : "success",
  );
  await router.push({ name: "job-trace", params: { jobId: result.job_id } });
}

async function backfillSessionOne(row: Row) {
  await backfillSessionForMemberships([row]);
}

onMounted(loadSpaces);
</script>

<template>
  <ResourcePage
    ref="pageRef"
    title="空间成员"
    description="账号与 Space 的当前成员关系。成员动作后续只接 Space 流程。"
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
              v-model="externalSpaceId"
              class="input"
              placeholder="按 external_space_id 筛选"
              @keyup.enter="reload"
            />
          </label>
          <label class="field">
            <span>空间</span>
            <select v-model="spaceFilter" class="select">
              <option value="">全部空间</option>
              <option v-for="item in spaces" :key="String(item.id)" :value="String(item.id)">
                {{ item.name || item.id }} / {{ item.external_space_id || "" }}
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
            <span>Session识别空间</span>
            <select v-model="sessionAccountDetected" class="select">
              <option value="">全部</option>
              <option value="yes">已识别</option>
              <option value="no">未识别</option>
            </select>
          </label>
          <label class="field">
            <span>是否授权</span>
            <select v-model="hasSpaceCredential" class="select">
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
            <h2>补 Session</h2>
            <p>按选中成员提取账号 ID，复用账号补 Session 流程。</p>
          </div>
          <span class="selected-hint">已选 {{ selectedCount }} 条</span>
        </div>
        <div class="action-row">
          <label class="inline-control">
            <span>同时 Work 数</span>
            <input v-model.number="sessionWorkCount" class="input small-input" type="number" min="1" max="500" />
          </label>
          <button class="btn" :disabled="selectedCount === 0" @click="backfillSessionForMemberships(selectedRows)">
            补选中账号 Session（{{ selectedAccountCount }}）
          </button>
        </div>
      </section>
    </template>
    <template #rowActions="{ row }">
      <div class="row-actions">
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
