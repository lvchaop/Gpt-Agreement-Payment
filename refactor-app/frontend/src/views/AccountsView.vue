<script setup lang="ts">
import { ref } from "vue";
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
  { key: "account_status", label: "账号状态", badge: true },
  { key: "session_status", label: "Session 状态", badge: true },
  { key: "last_session_refresh_at", label: "最近 Session 刷新", summary: 30 },
  { key: "last_login_error_code", label: "登录错误码", badge: true },
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
];

const selectedCount = ref(0);
const selectedRows = ref<Row[]>([]);
const backfillConcurrency = ref(10);

function updateSelection(rows: Record<string, unknown>[]) {
  selectedRows.value = rows as Row[];
  selectedCount.value = rows.length;
}

async function runSelectedAccountJob() {
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
  const result = await resourcesApi.backfillSession(payload);
  store.toast(
    "补 Session 执行完成",
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
    description="账号基本信息与账号级登录状态。Space token 只在空间凭证表维护。"
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
            <p>账号页只维护账号级登录材料；Space token 在空间凭证页维护。</p>
          </div>
          <span class="selected-hint">已选 {{ selectedCount }} 个账号</span>
        </div>
        <div class="account-action-body">
          <label class="inline-control">
            <span>并发 Work</span>
            <input v-model.number="backfillConcurrency" class="input small-input" type="number" min="1" max="500" />
          </label>
          <button class="btn" :disabled="selectedCount === 0" @click="runSelectedAccountJob">
            补 Session
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
