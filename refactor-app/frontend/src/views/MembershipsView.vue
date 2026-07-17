<script setup lang="ts">
import { KeyRound } from "@lucide/vue";
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";

import { resourcesApi, type Row } from "../api/resources";
import ConfirmModal from "../components/ConfirmModal.vue";
import type { Column, TableFilter } from "../components/DataTable.vue";
import EntitySelect from "../components/EntitySelect.vue";
import ResourcePage from "../components/ResourcePage.vue";
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();
const router = useRouter();
const selectedRows = ref<Row[]>([]);
const sessionWorkCount = ref(10);
const authorizationWorkCount = ref(1);
const authorizationBusy = ref(false);
const otpSpaceId = ref("");
const otpPrepareWorkCount = ref(50);
const otpPrepareAccountCount = ref<number | "">("");
const otpSummary = ref<Row | null>(null);
const otpSummaryLoading = ref(false);
const otpAction = ref<"prepare" | "submit" | "">("");
const otpBusy = ref(false);

const otpPrepareCount = computed(() => Number(otpSummary.value?.prepare_candidate_count || 0));
const otpSelectedAccountIds = computed(() => Array.from(new Set(
  selectedRows.value.map((row) => String(row.user_account_id || "")).filter(Boolean),
)));
const selectedMembershipIds = computed(() => Array.from(new Set(
  selectedRows.value.map((row) => String(row.id || "")).filter(Boolean),
)));
const otpPlannedPrepareCount = computed(() => {
  if (otpSelectedAccountIds.value.length) return otpSelectedAccountIds.value.length;
  const requested = Number(otpPrepareAccountCount.value);
  return Number.isInteger(requested) && requested > 0 ? requested : otpPrepareCount.value;
});
const otpSubmitCount = computed(() => Number(otpSummary.value?.submit_snapshot_count || 0));
const otpActiveJob = computed(() => otpSummary.value?.active_job as Row | undefined);

const columns: Column[] = [
  { key: "user_email", label: "账号邮箱", summary: 30, copyable: true },
  { key: "space_name", label: "空间" },
  { key: "space_plan_type", label: "订阅类型", badge: true, sortable: true },
  { key: "last_session_refresh_at", label: "最近 Session 时间", type: "datetime", relativeTime: true, sortable: true },
  { key: "external_space_id", label: "外部空间 ID", mono: true, summary: 22, copyable: true },
  { key: "admin_email", label: "管理员邮箱", summary: 28 },
  { key: "credential_type", label: "凭证类型", badge: true },
  { key: "membership_status", label: "成员状态", badge: true, sortable: true },
  { key: "session_status", label: "Session", badge: true },
  { key: "session_account_detected", label: "识别空间", type: "boolean" },
  { key: "has_space_credential", label: "已授权", type: "boolean" },
  { key: "codex_select_channel_required", label: "选择验证方式", type: "boolean" },
  { key: "failure_code", label: "失败码", badge: true },
  { key: "failure_message", label: "失败信息", summary: 42 },
  { key: "remote_synced_at", label: "远端同步", type: "datetime", relativeTime: true, sortable: true },
];

const filters: TableFilter[] = [
  { key: "credential_type", label: "空间类型", options: [
    { label: "个人", value: "personal_account" },
    { label: "Team 5h/周", value: "team_5h_weekly" },
    { label: "Team 月额度", value: "team_monthly" },
  ] },
  { key: "plan_type", label: "订阅类型", options: [
    { label: "Free", value: "free" },
    { label: "Plus", value: "plus" },
    { label: "Pro", value: "pro" },
    { label: "Team", value: "team" },
  ] },
  { key: "session_recency", label: "最近 Session 时间", options: [
    { label: "6 小时内", value: "within_6h" },
    { label: "12 小时内", value: "within_12h" },
    { label: "1 天内", value: "within_1d" },
    { label: "2 天内", value: "within_2d" },
    { label: "3 天内", value: "within_3d" },
    { label: "7 天内", value: "within_7d" },
    { label: "从未获取", value: "never" },
  ] },
  {
    key: "space_id",
    label: "Space",
    dependsOn: "credential_type",
    placeholder: "按空间名称或外部 ID 搜索",
    loader: async (query, values) => (
      await resourcesApi.spaceOptions(query, "", values.credential_type || "")
    ).items.map((item) => ({
      label: item.label,
      value: item.value,
      description: item.description,
      status: item.status,
    })),
  },
  { key: "membership_status", label: "成员状态", options: [
    { label: "有效", value: "active" }, { label: "已邀请", value: "invited" },
    { label: "已接受", value: "accepted" }, { label: "失败", value: "failed" },
    { label: "已离开", value: "left" }, { label: "禁用", value: "disabled" },
  ] },
  { key: "session_account_detected", label: "识别空间", options: [
    { label: "已识别", value: "yes" }, { label: "未识别", value: "no" },
  ] },
  { key: "has_space_credential", label: "授权状态", options: [
    { label: "已授权", value: "yes" }, { label: "未授权", value: "no" },
  ] },
  { key: "codex_select_channel_required", label: "选择验证方式", options: [
    { label: "已标记（永久跳过）", value: "true" },
    { label: "未标记", value: "false" },
  ] },
];

function updateSelection(rows: Record<string, unknown>[]) { selectedRows.value = rows as Row[]; }

async function spaceLoader(query: string) {
  const result = await resourcesApi.spaceOptions(query);
  return result.items;
}

async function refreshOtpSummary() {
  otpSummary.value = null;
  if (!otpSpaceId.value) return;
  otpSummaryLoading.value = true;
  try {
    const summary = await resourcesApi.spaceSessionOtpSummary(otpSpaceId.value);
    otpSummary.value = summary;
    const defaultCount = Number(summary.default_prepare_work_count || 50);
    if (!Number.isFinite(otpPrepareWorkCount.value) || otpPrepareWorkCount.value < 1) {
      otpPrepareWorkCount.value = defaultCount;
    }
  } catch (err) {
    store.toast("读取 OTP 状态失败", String((err as Error).message ?? err), "error");
  } finally {
    otpSummaryLoading.value = false;
  }
}

watch(otpSpaceId, () => {
  otpPrepareAccountCount.value = "";
  void refreshOtpSummary();
});

function openOtpAction(action: "prepare" | "submit") {
  if (!otpSpaceId.value) {
    store.toast("未选择 Space", "请先选择要处理的 Space。", "warning");
    return;
  }
  if (otpActiveJob.value?.job_id) {
    store.toast("该 Space 正在执行 OTP Job", String(otpActiveJob.value.job_id), "warning");
    return;
  }
  if (action === "prepare" && otpPrepareCount.value < 1) {
    store.toast("没有有效成员", "该 Space 没有可执行 Prepare 的 active 成员。", "warning");
    return;
  }
  if (action === "prepare" && otpSelectedAccountIds.value.length) {
    const invalidSpaceRows = selectedRows.value.filter(
      (row) => String(row.space_id || "") !== otpSpaceId.value,
    );
    if (invalidSpaceRows.length) {
      store.toast("勾选成员不属于当前 Space", "请只勾选当前 OTP Space 下的成员。", "warning");
      return;
    }
    const inactiveRows = selectedRows.value.filter(
      (row) => String(row.membership_status || "") !== "active",
    );
    if (inactiveRows.length) {
      store.toast("勾选成员不是有效成员", "预取 OTP 只能处理 membership_status=active 的成员。", "warning");
      return;
    }
  } else if (action === "prepare" && otpPrepareAccountCount.value !== "") {
    const requested = Number(otpPrepareAccountCount.value);
    if (!Number.isInteger(requested) || requested < 1) {
      store.toast("账号数量无效", "账号数量必须是大于 0 的整数，或留空处理全部成员。", "warning");
      return;
    }
    if (requested > otpPrepareCount.value) {
      store.toast("账号数量超过有效成员", `最多可预取 ${otpPrepareCount.value} 个账号。`, "warning");
      return;
    }
  }
  if (action === "submit" && otpSubmitCount.value < 1) {
    store.toast("没有可提交快照", "该 Space 的有效成员没有可提交 OTP 快照。", "warning");
    return;
  }
  otpAction.value = action;
}

async function runOtpAction() {
  if (!otpAction.value || !otpSpaceId.value) return;
  otpBusy.value = true;
  try {
    const prepareAccountCount = otpPrepareAccountCount.value === ""
      ? undefined
      : Number(otpPrepareAccountCount.value);
    const prepareUserAccountIds = otpSelectedAccountIds.value;
    const result = otpAction.value === "prepare"
      ? await resourcesApi.prepareSpaceSessionOtp(otpSpaceId.value, {
          created_by: "ops-ui",
          work_count: Math.max(1, Number(otpPrepareWorkCount.value || 1)),
          account_count: prepareUserAccountIds.length ? undefined : prepareAccountCount,
          user_account_ids: prepareUserAccountIds.length ? prepareUserAccountIds : undefined,
        })
      : await resourcesApi.submitSpaceSessionOtp(otpSpaceId.value, { created_by: "ops-ui" });
    const title = otpAction.value === "prepare" ? "OTP Prepare Job 已创建" : "OTP Submit Job 已创建";
    store.toast(title, `账号=${result.selected_count} Work=${result.work_count}`, "success");
    otpAction.value = "";
    await router.push({ name: "job-trace", params: { jobId: result.job_id } });
  } catch (err) {
    store.toast("创建 OTP Job 失败", String((err as Error).message ?? err), "error");
  } finally {
    otpBusy.value = false;
  }
}

async function backfillSession(rows: Row[]) {
  const ids = Array.from(new Set(rows.map((row) => String(row.user_account_id || "")).filter(Boolean)));
  if (!ids.length) { store.toast("未选择成员", "请先勾选成员。", "warning"); return; }
  try {
    const result = await resourcesApi.backfillSession({ user_account_ids: ids, created_by: "ops-ui", work_count: sessionWorkCount.value });
    store.toast("补 Session 任务已创建", `账号=${ids.length} Work=${result.work_count}`, "success");
    await router.push({ name: "job-trace", params: { jobId: result.job_id } });
  } catch (err) { store.toast("创建任务失败", String((err as Error).message ?? err), "error"); }
}

async function authorizeSelectedPersonalCodex() {
  const ids = selectedMembershipIds.value;
  if (!ids.length) {
    store.toast("未选择成员", "请先勾选个人空间成员。", "warning");
    return;
  }
  authorizationBusy.value = true;
  try {
    const result = await resourcesApi.authorizePersonalCodexMemberships({
      space_membership_ids: ids,
      created_by: "ops-ui",
      work_count: authorizationWorkCount.value,
    });
    if (!result.job_id) {
      const firstReason = result.selection_skipped[0]?.reason || "没有符合条件的个人空间成员";
      store.toast(
        "未创建个人 Codex 授权 Job",
        `选中=${result.requested_count} 跳过=${result.selection_skipped_count} · ${firstReason}`,
        "warning",
      );
      return;
    }
    store.toast(
      "个人 Codex 授权 Job 已创建",
      `选中=${result.requested_count} 授权=${result.selected_count} 跳过=${result.selection_skipped_count} Work=${result.work_count}`,
      result.selection_skipped_count ? "warning" : "success",
    );
    await router.push({ name: "job-trace", params: { jobId: result.job_id } });
  } catch (err) {
    store.toast("创建个人 Codex 授权 Job 失败", String((err as Error).message ?? err), "error");
  } finally {
    authorizationBusy.value = false;
  }
}
</script>

<template>
  <ResourcePage
    title="空间成员"
    description="查看账号在每个空间下的远端成员状态、Session 识别结果与授权结果。"
    :columns="columns"
    :loader="resourcesApi.memberships"
    :filters="filters"
    selectable
    empty-text="暂无空间成员。"
    @selection-change="updateSelection"
  >
    <template #actions>
      <div class="action-group">
        <div class="otp-space-select">
          <EntitySelect v-model="otpSpaceId" :loader="spaceLoader" placeholder="选择分阶段 OTP 的 Space" />
        </div>
        <label class="inline-control"><span>账号数（未勾选时）</span><input v-model.number="otpPrepareAccountCount" class="input small-input" type="number" min="1" :max="otpPrepareCount || undefined" :disabled="otpSelectedAccountIds.length > 0" placeholder="全部" /></label>
        <label class="inline-control"><span>Prepare Work</span><input v-model.number="otpPrepareWorkCount" class="input small-input" type="number" min="1" :max="Number(otpSummary?.worker_capacity || 2000)" /></label>
        <button class="btn" :disabled="otpSummaryLoading || !otpSpaceId || Boolean(otpActiveJob?.job_id)" @click="openOtpAction('prepare')">预取 OTP（{{ otpPlannedPrepareCount }}）</button>
        <button class="btn primary" :disabled="otpSummaryLoading || !otpSpaceId || Boolean(otpActiveJob?.job_id)" @click="openOtpAction('submit')">同时提交 OTP（{{ otpSubmitCount }}）</button>
      </div>
      <div class="action-group">
        <label class="inline-control"><span>Work 数</span><input v-model.number="sessionWorkCount" class="input small-input" type="number" min="1" max="500" /></label>
        <button class="btn primary" :disabled="selectedRows.length === 0" @click="backfillSession(selectedRows)">补选中账号 Session（{{ selectedRows.length }}）</button>
      </div>
      <div class="action-group">
        <label class="inline-control"><span>授权 Work</span><input v-model.number="authorizationWorkCount" class="input small-input" type="number" min="1" max="350" /></label>
        <button class="btn primary" :disabled="selectedMembershipIds.length === 0 || authorizationBusy" @click="authorizeSelectedPersonalCodex">
          <KeyRound :size="16" />个人 Codex 授权（{{ selectedMembershipIds.length }}）
        </button>
      </div>
    </template>
    <template #rowActions="{ row }"><button class="btn" @click="backfillSession([row])">补 Session</button></template>
  </ResourcePage>
  <ConfirmModal
    :open="Boolean(otpAction)"
    :title="otpAction === 'prepare' ? '预取成员 OTP' : '同时提交成员 OTP'"
    :message="otpAction === 'prepare' ? '从该 Space 的有效成员生成快照，不提交验证码。' : '按当前可提交快照数量一次启动全部 Work；所有 Work 共用一个内存屏障。'"
    :summary="otpAction === 'prepare'
      ? { 'Space': otpSummary?.space_name, '有效成员': otpPrepareCount, '选择方式': otpSelectedAccountIds.length ? `勾选账号（${otpSelectedAccountIds.length}）` : otpPrepareAccountCount === '' ? `全部（${otpPrepareCount}）` : `指定数量（${otpPrepareAccountCount}）`, '本次账号数': otpPlannedPrepareCount, '同时执行 Work': otpPrepareWorkCount }
      : { 'Space': otpSummary?.space_name, '可提交快照': otpSubmitCount, '启动 Work': otpSubmitCount, '内存屏障': 1 }"
    :confirm-text="otpAction === 'prepare' ? '创建 Prepare Job' : '创建 Submit Job'"
    :busy="otpBusy"
    @close="otpAction = ''"
    @confirm="runOtpAction"
  />
</template>

<style scoped>
.otp-space-select { min-width: 260px; width: min(360px, 36vw); }
@media (max-width: 760px) { .otp-space-select { width: 100%; } }
</style>
