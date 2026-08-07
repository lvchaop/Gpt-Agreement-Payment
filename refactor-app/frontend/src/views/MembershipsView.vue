<script setup lang="ts">
import { KeyRound, RefreshCw } from "@lucide/vue";
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
const spaceDetectionBusy = ref(false);
const authorizationWorkCount = ref(1);
const authorizationBusy = ref(false);
const authorizationConfirmOpen = ref(false);
const authorizationUseHeroSms = ref(false);
const authorizationHeroCountry = ref("");
const authorizationHeroMaxPrice = ref("0.05");
const otpSpaceIds = ref<string[]>([]);
const otpPrepareWorkCount = ref(50);
const otpPrepareAccountCount = ref<number | "">("");
const otpSummary = ref<Row | null>(null);
const otpSummaryLoading = ref(false);
const otpAction = ref<"prepare" | "remote_submit" | "">("");
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
const otpRemoteSubmitCount = computed(() => (
  Number(otpSummary.value?.remote_submit_snapshot_count || 0)
));
const otpRemoteRemainingCount = computed(() => (
  Number(otpSummary.value?.remote_submit_remaining_count || 0)
));
const otpActiveJob = computed(() => otpSummary.value?.active_job as Row | undefined);
const otpSpaceSummaryLabel = computed(() => {
  const names = Array.isArray(otpSummary.value?.space_names)
    ? otpSummary.value.space_names.map((item) => String(item || "")).filter(Boolean)
    : [];
  if (names.length === 1) return names[0];
  return names.length ? `${names.length} 个 Space` : `${otpSpaceIds.value.length} 个 Space`;
});

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
    { label: "未知", value: "unknown" },
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
  if (!otpSpaceIds.value.length) return;
  otpSummaryLoading.value = true;
  try {
    const summary = await resourcesApi.multiSpaceSessionOtpSummary({
      space_ids: otpSpaceIds.value,
    });
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

watch(otpSpaceIds, () => {
  otpPrepareAccountCount.value = "";
  void refreshOtpSummary();
});

function openOtpAction(action: "prepare" | "remote_submit") {
  if (!otpSpaceIds.value.length) {
    store.toast("未选择 Space", "请先选择一个或多个要处理的 Space。", "warning");
    return;
  }
  if (otpActiveJob.value?.job_id) {
    store.toast("所选账号正在执行 OTP Job", String(otpActiveJob.value.job_id), "warning");
    return;
  }
  if (action === "prepare" && otpPrepareCount.value < 1) {
    store.toast("没有有效成员", "所选 Space 没有可执行 Prepare 的 active 账号。", "warning");
    return;
  }
  if (action === "prepare" && otpSelectedAccountIds.value.length) {
    const selectedSpaceIds = new Set(otpSpaceIds.value);
    const invalidSpaceRows = selectedRows.value.filter(
      (row) => !selectedSpaceIds.has(String(row.space_id || "")),
    );
    if (invalidSpaceRows.length) {
      store.toast("勾选成员不在所选 Space", "请只勾选已选 OTP Space 下的成员。", "warning");
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
  if (action === "remote_submit" && otpRemoteSubmitCount.value < 1) {
    store.toast("没有可提交快照", "所选 Space 的有效账号没有 otp_collected 快照。", "warning");
    return;
  }
  otpAction.value = action;
}

async function runOtpAction() {
  if (!otpAction.value || !otpSpaceIds.value.length) return;
  otpBusy.value = true;
  try {
    const prepareAccountCount = otpPrepareAccountCount.value === ""
      ? undefined
      : Number(otpPrepareAccountCount.value);
    const prepareUserAccountIds = otpSelectedAccountIds.value;
    const result = otpAction.value === "prepare"
      ? await resourcesApi.prepareMultiSpaceSessionOtp({
          space_ids: otpSpaceIds.value,
          created_by: "ops-ui",
          work_count: Math.max(1, Number(otpPrepareWorkCount.value || 1)),
          account_count: prepareUserAccountIds.length ? undefined : prepareAccountCount,
          user_account_ids: prepareUserAccountIds.length ? prepareUserAccountIds : undefined,
        })
      : await resourcesApi.submitMultiSpaceSessionOtpRemote({
          space_ids: otpSpaceIds.value,
          created_by: "ops-ui",
        });
    const title = otpAction.value === "prepare"
      ? "OTP Prepare Job 已创建"
      : "服务器 OTP Submit Job 已创建";
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

async function refreshSessionSpaceDetection(rows: Row[]) {
  const ids = Array.from(new Set(
    rows.map((row) => String(row.user_account_id || "")).filter(Boolean),
  ));
  if (!ids.length) {
    store.toast("未选择成员", "请先勾选成员。", "warning");
    return;
  }
  spaceDetectionBusy.value = true;
  try {
    const result = await resourcesApi.refreshSessionSpaceDetection({
      user_account_ids: ids,
      created_by: "ops-ui",
      work_count: sessionWorkCount.value,
    });
    store.toast("刷新识别空间 Job 已创建", `账号=${ids.length} Work=${result.work_count}`, "success");
    await router.push({ name: "job-trace", params: { jobId: result.job_id } });
  } catch (err) {
    store.toast("创建刷新识别空间 Job 失败", String((err as Error).message ?? err), "error");
  } finally {
    spaceDetectionBusy.value = false;
  }
}

function openPersonalCodexAuthorization() {
  const ids = selectedMembershipIds.value;
  if (!ids.length) {
    store.toast("未选择成员", "请先勾选个人空间成员。", "warning");
    return;
  }
  authorizationUseHeroSms.value = false;
  authorizationHeroCountry.value = "";
  authorizationHeroMaxPrice.value = "0.05";
  authorizationConfirmOpen.value = true;
}

function closePersonalCodexAuthorization() {
  if (!authorizationBusy.value) authorizationConfirmOpen.value = false;
}

async function authorizeSelectedPersonalCodex() {
  const ids = selectedMembershipIds.value;
  if (authorizationUseHeroSms.value) {
    if (!/^\d+$/.test(authorizationHeroCountry.value.trim())) {
      store.toast("国家编号无效", "请输入 Hero 的数字国家编号。", "warning");
      return;
    }
    const maxPrice = Number(authorizationHeroMaxPrice.value);
    if (!Number.isFinite(maxPrice) || maxPrice <= 0) {
      store.toast("最大价格无效", "最大价格必须是大于 0 的数字。", "warning");
      return;
    }
  }
  authorizationBusy.value = true;
  try {
    const result = await resourcesApi.authorizePersonalCodexMemberships({
      space_membership_ids: ids,
      created_by: "ops-ui",
      work_count: authorizationWorkCount.value,
      use_hero_sms_for_add_phone: authorizationUseHeroSms.value,
      ...(authorizationUseHeroSms.value ? {
        hero_sms_country: authorizationHeroCountry.value.trim(),
        hero_sms_max_price: String(authorizationHeroMaxPrice.value),
      } : {}),
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
    authorizationConfirmOpen.value = false;
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
          <EntitySelect v-model="otpSpaceIds" :loader="spaceLoader" placeholder="选择一个或多个 OTP Space" multiple />
        </div>
        <label class="inline-control"><span>账号数（未勾选时）</span><input v-model.number="otpPrepareAccountCount" class="input small-input" type="number" min="1" :max="otpPrepareCount || undefined" :disabled="otpSelectedAccountIds.length > 0" placeholder="全部" /></label>
        <label class="inline-control"><span>Prepare Work</span><input v-model.number="otpPrepareWorkCount" class="input small-input" type="number" min="1" :max="Number(otpSummary?.worker_capacity || 2000)" /></label>
        <button class="btn" :disabled="otpSummaryLoading || !otpSpaceIds.length || Boolean(otpActiveJob?.job_id)" @click="openOtpAction('prepare')">预取 OTP（{{ otpPlannedPrepareCount }}）</button>
        <button class="btn primary" :disabled="otpSummaryLoading || !otpSpaceIds.length || Boolean(otpActiveJob?.job_id)" @click="openOtpAction('remote_submit')">服务器提交 OTP（{{ otpRemoteSubmitCount }}）</button>
      </div>
      <div class="action-group">
        <label class="inline-control"><span>Work 数</span><input v-model.number="sessionWorkCount" class="input small-input" type="number" min="1" max="500" /></label>
        <button class="btn primary" :disabled="selectedRows.length === 0" @click="backfillSession(selectedRows)">补选中账号 Session（{{ selectedRows.length }}）</button>
        <button class="btn" :disabled="selectedRows.length === 0 || spaceDetectionBusy" @click="refreshSessionSpaceDetection(selectedRows)">
          <RefreshCw :size="16" />刷新识别空间（{{ selectedRows.length }}）
        </button>
      </div>
      <div class="action-group">
        <label class="inline-control"><span>授权 Work</span><input v-model.number="authorizationWorkCount" class="input small-input" type="number" min="1" max="350" /></label>
        <button class="btn primary" :disabled="selectedMembershipIds.length === 0 || authorizationBusy" @click="openPersonalCodexAuthorization">
          <KeyRound :size="16" />个人 Codex 授权（{{ selectedMembershipIds.length }}）
        </button>
      </div>
    </template>
    <template #rowActions="{ row }">
      <button class="btn" @click="backfillSession([row])">补 Session</button>
      <button class="btn" :disabled="spaceDetectionBusy" @click="refreshSessionSpaceDetection([row])">
        <RefreshCw :size="15" />刷新识别
      </button>
    </template>
  </ResourcePage>
  <ConfirmModal
    :open="Boolean(otpAction)"
    :title="otpAction === 'prepare' ? '预取成员 OTP' : '服务器提交成员 OTP'"
    :message="otpAction === 'prepare' ? '合并所选 Space 的有效成员，按账号去重生成快照，不提交验证码。' : '合并所选 Space 的 otp_collected 快照，按账号去重后发送到服务器提交。'"
    :summary="otpAction === 'prepare'
      ? { 'Space 范围': otpSpaceSummaryLabel, '去重后有效账号': otpPrepareCount, '选择方式': otpSelectedAccountIds.length ? `勾选账号（${otpSelectedAccountIds.length}）` : otpPrepareAccountCount === '' ? `全部（${otpPrepareCount}）` : `指定数量（${otpPrepareAccountCount}）`, '本次账号数': otpPlannedPrepareCount, '同时执行 Work': otpPrepareWorkCount }
      : { 'Space 范围': otpSpaceSummaryLabel, '去重后本次提交': otpRemoteSubmitCount, '提交后剩余': otpRemoteRemainingCount, '本地 Work': 1, '单批上限': 1000 }"
    :confirm-text="otpAction === 'prepare' ? '创建 Prepare Job' : '创建服务器 Submit Job'"
    :busy="otpBusy"
    @close="otpAction = ''"
    @confirm="runOtpAction"
  />
  <ConfirmModal
    :open="authorizationConfirmOpen"
    title="个人 Codex 授权"
    message="为选中的个人空间成员创建授权 Job。Hero 仅在授权进入 add_phone 时申请号码。"
    :summary="{ '选中成员': selectedMembershipIds.length, '同时执行 Work': authorizationWorkCount, 'Hero 接码': authorizationUseHeroSms ? '启用' : '关闭' }"
    confirm-text="创建授权 Job"
    :busy="authorizationBusy"
    @close="closePersonalCodexAuthorization"
    @confirm="authorizeSelectedPersonalCodex"
  >
    <div class="authorization-options">
      <label class="authorization-check">
        <input v-model="authorizationUseHeroSms" type="checkbox" />
        <span>add_phone 时使用 Hero 接码</span>
      </label>
      <div v-if="authorizationUseHeroSms" class="authorization-fields">
        <label>
          <span>国家编号</span>
          <input v-model.trim="authorizationHeroCountry" class="input" type="text" inputmode="numeric" placeholder="Hero country ID" />
        </label>
        <label>
          <span>最大价格</span>
          <input v-model="authorizationHeroMaxPrice" class="input" type="number" min="0.0001" step="0.01" />
        </label>
      </div>
    </div>
  </ConfirmModal>
</template>

<style scoped>
.otp-space-select { min-width: 260px; width: min(360px, 36vw); }
.authorization-options { display: grid; gap: 12px; }
.authorization-check { align-items: center; display: flex; font-size: 13px; gap: 8px; }
.authorization-check input { accent-color: var(--accent); height: 16px; width: 16px; }
.authorization-fields { display: grid; gap: 10px; grid-template-columns: 1fr 1fr; }
.authorization-fields label { color: var(--text-muted); display: grid; font-size: 11px; font-weight: 700; gap: 6px; }
@media (max-width: 760px) { .otp-space-select { width: 100%; } }
@media (max-width: 520px) { .authorization-fields { grid-template-columns: 1fr; } }
</style>
