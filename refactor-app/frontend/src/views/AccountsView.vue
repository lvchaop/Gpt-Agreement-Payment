<script setup lang="ts">
import { Copy, Trash2 } from "@lucide/vue";
import { computed, ref } from "vue";
import { useRouter } from "vue-router";

import ResourcePage from "../components/ResourcePage.vue";
import ConfirmModal from "../components/ConfirmModal.vue";
import type { Column, TableFilter } from "../components/DataTable.vue";
import type { Row } from "../api/resources";
import { resourcesApi } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();
const router = useRouter();
const pageRef = ref<InstanceType<typeof ResourcePage> | null>(null);

const columns: Column[] = [
  { key: "id", label: "账号 ID", mono: true, summary: 24, copyable: true },
  { key: "email", label: "邮箱", copyable: true, sortable: true },
  { key: "phone_number", label: "手机号" },
  { key: "openai_user_id", label: "OpenAI 用户 ID", mono: true },
  { key: "personal_plan_type", label: "个人订阅", badge: true, sortable: true },
  { key: "account_status", label: "账号状态", badge: true },
  { key: "session_status", label: "Session 状态", badge: true },
  { key: "codex_select_channel_required", label: "选择验证方式", type: "boolean" },
  { key: "last_session_refresh_at", label: "最近 Session 时间", type: "datetime", relativeTime: true, sortable: true },
  { key: "last_login_error_code", label: "登录错误码", badge: true },
  { key: "created_at", label: "创建时间", type: "datetime", sortable: true },
];

const filters: TableFilter[] = [
  {
    key: "account_status",
    label: "账号状态",
    options: [
      { label: "active", value: "active" },
      { label: "invalid", value: "invalid" },
      { label: "registering", value: "registering" },
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
    key: "personal_plan_type",
    label: "个人订阅",
    options: [
      { label: "未知", value: "unknown" },
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
    key: "codex_select_channel_required",
    label: "选择验证方式",
    options: [
      { label: "已标记（永久跳过）", value: "true" },
      { label: "未标记", value: "false" },
    ],
  },
];

const selectedCount = ref(0);
const selectedRows = ref<Row[]>([]);
const backfillWorkCount = ref(10);
const backfillProxyCountry = ref("US");
const backfillConfirmOpen = ref(false);
const backfillBusy = ref(false);
const deleteTarget = ref<Row | null>(null);
const bulkDeleteOpen = ref(false);
const deleting = ref(false);
const copyingAccessTokenId = ref("");
const selectedEmailPreview = computed(() => {
  const emails = selectedRows.value.map((row) => String(row.email || row.id || "")).filter(Boolean);
  const preview = emails.slice(0, 3).join("、");
  return emails.length > 3 ? `${preview} 等 ${emails.length} 个账号` : preview;
});

function updateSelection(rows: Record<string, unknown>[]) {
  selectedRows.value = rows as Row[];
  selectedCount.value = rows.length;
}

async function copyAccessToken(row: Row) {
  const id = String(row.id || "");
  if (!id) return;
  copyingAccessTokenId.value = id;
  try {
    const result = await resourcesApi.accountAccessToken(id);
    await navigator.clipboard.writeText(result.access_token);
    store.toast("Access Token 已复制", String(row.email || id), "success");
  } catch (err) {
    store.toast("复制失败", String((err as Error).message ?? err), "error");
  } finally {
    copyingAccessTokenId.value = "";
  }
}

async function runSelectedAccountJob() {
  const ids = selectedRows.value.map((row) => String(row.id || "")).filter(Boolean);
  if (!ids.length) {
    store.toast("未选择账号", "请先勾选账号。", "warning");
    return;
  }
  const proxyCountry = backfillProxyCountry.value.trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(proxyCountry)) {
    store.toast("代理国家无效", "请输入两位国家代码，例如 US。", "warning");
    return;
  }
  backfillProxyCountry.value = proxyCountry;
  const payload = {
    user_account_ids: ids,
    created_by: "ops-ui",
    work_count: backfillWorkCount.value,
    proxy_country: proxyCountry,
  };
  backfillBusy.value = true;
  try {
    const result = await resourcesApi.backfillSession(payload);
    backfillConfirmOpen.value = false;
    store.toast(
      "补 Session Job 已创建",
      `账号=${ids.length} 代理=${proxyCountry} Work=${result.work_count}`,
      "success",
    );
    await router.push({ name: "job-trace", params: { jobId: result.job_id } });
  } catch (err) {
    store.toast("补 Session Job 创建失败", String((err as Error).message ?? err), "error");
  } finally {
    backfillBusy.value = false;
  }
}

async function deleteAccount() {
  const id = String(deleteTarget.value?.id || "");
  if (!id) return;
  deleting.value = true;
  try {
    const result = await resourcesApi.deleteAccount(id);
    store.toast(
      "账号已删除",
      `账号=${result.user_account_id} 个人空间=${result.deleted_personal_spaces} 代理绑定=${result.deleted_proxy_bindings}`,
      "success",
    );
    deleteTarget.value = null;
    await pageRef.value?.load();
  } catch (err) { store.toast("删除失败", String((err as Error).message ?? err), "error"); }
  finally { deleting.value = false; }
}

function openSelectedDelete() {
  if (!selectedCount.value) {
    store.toast("未选择账号", "请先勾选账号。", "warning");
    return;
  }
  bulkDeleteOpen.value = true;
}

async function deleteSelectedAccounts() {
  const ids = selectedRows.value.map((row) => String(row.id || "")).filter(Boolean);
  if (!ids.length) return;
  deleting.value = true;
  try {
    const result = await resourcesApi.deleteAccounts(ids);
    store.toast(
      "选中账号已删除",
      `删除=${result.deleted_count} 未找到=${result.missing_count} 个人空间=${result.deleted_personal_spaces} 代理绑定=${result.deleted_proxy_bindings}`,
      result.missing_count ? "warning" : "success",
    );
    bulkDeleteOpen.value = false;
    pageRef.value?.clearSelection();
    selectedRows.value = [];
    selectedCount.value = 0;
    await pageRef.value?.load();
  } catch (err) {
    store.toast("批量删除失败", String((err as Error).message ?? err), "error");
  } finally {
    deleting.value = false;
  }
}
</script>

<template>
  <ResourcePage
    ref="pageRef"
    title="账号"
    description="账号基本信息与账号级登录状态。Space token 只在空间凭证表维护。"
    :columns="columns"
    :loader="resourcesApi.accounts"
    :filters="filters"
    batch-search
    selectable
    empty-text="暂无账号。"
    @selection-change="updateSelection"
  >
    <template #actions>
      <div class="action-group">
          <button class="btn primary" :disabled="selectedCount === 0" @click="backfillConfirmOpen = true">补 Session（{{ selectedCount }}）</button>
          <button class="btn danger" :disabled="selectedCount === 0 || deleting" @click="openSelectedDelete">
            <Trash2 :size="16" />删除选中（{{ selectedCount }}）
          </button>
      </div>
    </template>
    <template #rowActions="{ row }">
      <button
        class="btn"
        :disabled="!row.has_access_token || copyingAccessTokenId === String(row.id || '')"
        :title="row.has_access_token ? '复制个人 Access Token' : '该账号没有 Access Token'"
        @click="copyAccessToken(row)"
      >
        <Copy :size="15" />复制 Token
      </button>
      <button class="btn danger" @click="deleteTarget = row"><Trash2 :size="15" />删除</button>
    </template>
  </ResourcePage>
  <ConfirmModal
    :open="backfillConfirmOpen"
    title="补 Session"
    message="选择本次登录使用的代理国家，确认后为选中账号创建补 Session Work。"
    :summary="{ '选中账号': selectedCount, '代理国家': backfillProxyCountry.toUpperCase(), '同时执行 Work': backfillWorkCount }"
    confirm-text="创建补 Session Job"
    :busy="backfillBusy"
    @close="backfillConfirmOpen = false"
    @confirm="runSelectedAccountJob"
  >
    <div class="backfill-config">
      <label class="field">
        <span>代理国家</span>
        <input v-model="backfillProxyCountry" class="input" maxlength="2" pattern="[A-Za-z]{2}" placeholder="US" @input="backfillProxyCountry = backfillProxyCountry.toUpperCase()" />
      </label>
      <label class="field">
        <span>并发数</span>
        <input v-model.number="backfillWorkCount" class="input" type="number" min="1" max="500" />
      </label>
    </div>
  </ConfirmModal>
  <ConfirmModal :open="Boolean(deleteTarget)" title="删除账号" message="会同时删除该账号拥有的个人空间、个人空间关联数据和代理绑定。" :summary="{ '账号邮箱': deleteTarget?.email, '账号 ID': deleteTarget?.id }" confirm-text="确认删除" danger :busy="deleting" @close="deleteTarget = null" @confirm="deleteAccount" />
  <ConfirmModal
    :open="bulkDeleteOpen"
    title="删除选中账号"
    message="会删除选中账号、账号拥有的个人空间、个人空间关联数据和代理绑定，该操作不可撤销。"
    :summary="{ '选中数量': selectedCount, '账号示例': selectedEmailPreview }"
    confirm-text="确认批量删除"
    danger
    :busy="deleting"
    @close="bulkDeleteOpen = false"
    @confirm="deleteSelectedAccounts"
  />
</template>

<style scoped>
.action-group { align-items: center; display: flex; gap: 8px; }
.backfill-config { display: grid; gap: 10px; grid-template-columns: 1fr 1fr; }
@media (max-width: 520px) { .backfill-config { grid-template-columns: 1fr; } }
</style>
