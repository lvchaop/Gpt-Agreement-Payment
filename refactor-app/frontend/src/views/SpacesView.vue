<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { BadgePercent, CreditCard, Expand, KeyRound, Plus, Power, PowerOff, RefreshCw, Server, ServerOff, Trash2, Upload, UserPlus } from "@lucide/vue";

import DataTable from "../components/DataTable.vue";
import type { Column, TableFilter } from "../components/DataTable.vue";
import ConfirmModal from "../components/ConfirmModal.vue";
import FormDrawer from "../components/FormDrawer.vue";
import EntitySelect from "../components/EntitySelect.vue";
import ResourcePage from "../components/ResourcePage.vue";
import { resourcesApi, type Row } from "../api/resources";
import { useOpsStore } from "../stores/ops";
import { splitPaymentImportLines } from "../utils/paymentMethodImport";

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
const autoInviteTarget = ref<Row | null>(null);
const hostingTarget = ref<Row | null>(null);
const unhostingTarget = ref<Row | null>(null);
const paymentBindTarget = ref<Row | null>(null);
const plusCheckoutTarget = ref<Row | null>(null);
const selectedSpaces = ref<Row[]>([]);
const selectedPaymentBindOpen = ref(false);
const selectedPromotionCheckOpen = ref(false);
const checkingSelectedPromotions = ref(false);
const promotionProxyCountry = ref("JP");
const promotionWorkCount = ref(5);
const expandingSpaceId = ref("");
const updatingSpaceStatusId = ref("");
const updatingAutoReplenishId = ref("");
const preparingAutoInviteId = ref("");
const updatingHostingSpaceId = ref("");
const bindingPaymentSpaceId = ref("");
const plusCheckoutSpaceId = ref("");
const plusCheckoutCreateCountry = ref("US");
const plusCheckoutPromoCountry = ref("JP");
const plusCheckoutCampaign = ref("plus-1-month-free");
const autoStartPlusCheckout = ref(true);
const bindingSelectedPaymentSpaces = ref(false);
const showPaymentPoolPanel = ref(false);
const paymentNamesText = ref("");
const paymentAddressesText = ref("");
const paymentCardsText = ref("");
const paymentInventorySummary = ref<Row>({});
const importingPaymentInventory = ref(false);
const showReplenishEmailPanel = ref(false);
const replenishEmailsText = ref("");
const replenishEmailSummary = ref<Row>({});
const importingReplenishEmails = ref(false);
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
const selectedSpaceIds = computed(() => Array.from(new Set(
  selectedSpaces.value.map((row) => String(row.id || "").trim()).filter(Boolean),
)));
const selectedPersonalSpaceCount = computed(() => selectedSpaces.value.filter(
  (row) => String(row.space_type || "") === "personal",
).length);
const selectedUnboundPersonalSpaceCount = computed(() => selectedSpaces.value.filter(
  (row) => String(row.space_type || "") === "personal"
    && String(row.space_status || "") === "active"
    && Boolean(row.has_promotion)
    && !Boolean(row.has_payment_method)
    && String(row.payment_method_status || "") !== "bound"
    && !Boolean(row.payment_method_cooldown_active),
).length);

const columns: Column[] = [
  { key: "id", label: "空间 ID", mono: true, summary: 26 },
  { key: "name", label: "名称" },
  { key: "external_space_id", label: "外部空间 ID", mono: true, summary: 26 },
  { key: "space_type", label: "空间类型", badge: true },
  { key: "plan_type", label: "订阅类型", badge: true, sortable: true },
  { key: "has_promotion", label: "是否有优惠", type: "boolean" },
  { key: "promotion_id", label: "优惠 ID", mono: true },
  { key: "last_session_refresh_at", label: "最近 Session 时间", type: "datetime", relativeTime: true, sortable: true },
  { key: "credential_type", label: "凭证类型", badge: true },
  { key: "auth_mode", label: "授权模式", badge: true },
  { key: "provider", label: "来源" },
  { key: "seat_limit", label: "席位上限" },
  { key: "payment_method_status", label: "支付状态", badge: true, sortable: true },
  { key: "payment_method_last4", label: "卡尾号", mono: true },
  { key: "payment_method_attempt_count", label: "绑卡次数" },
  { key: "payment_method_cooldown_until", label: "绑卡冷却至", type: "datetime", relativeTime: true },
  { key: "auto_replenish_enabled", label: "自动补号", type: "boolean" },
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
    key: "auth_mode",
    label: "授权模式",
    options: [
      { label: "codex_oauth", value: "codex_oauth" },
      { label: "backend_access_token", value: "backend_access_token" },
    ],
  },
  {
    key: "has_promotion",
    label: "是否有优惠",
    options: [
      { label: "有优惠", value: "true" },
      { label: "无优惠", value: "false" },
    ],
  },
  {
    key: "payment_method_status",
    label: "支付状态",
    options: [
      { label: "未绑定", value: "missing" },
      { label: "绑定中", value: "binding" },
      { label: "已绑定", value: "bound" },
      { label: "失败", value: "failed" },
    ],
  },
  {
    key: "has_payment_method",
    label: "是否绑定支付方式",
    options: [
      { label: "已绑定", value: "true" },
      { label: "未绑定", value: "false" },
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

async function updateAutoReplenish(row: Row, event: Event) {
  const id = String(row.id || "");
  if (!id) return;
  const enabled = (event.target as HTMLInputElement).checked;
  updatingAutoReplenishId.value = id;
  try {
    await resourcesApi.patchSpace(id, { auto_replenish_enabled: enabled });
    store.toast(enabled ? "自动补号已开启" : "自动补号已关闭", String(row.name || row.external_space_id || id), "success");
    await pageRef.value?.load();
  } catch (err) {
    store.toast("自动补号配置失败", String((err as Error).message ?? err), "error");
    await pageRef.value?.load();
  } finally {
    updatingAutoReplenishId.value = "";
  }
}

async function loadReplenishEmailSummary() {
  try {
    replenishEmailSummary.value = await resourcesApi.spaceReplenishEmailSummary();
  } catch (err) {
    store.toast("补号邮箱库存读取失败", String((err as Error).message ?? err), "error");
  }
}

async function openReplenishEmailImport() {
  showReplenishEmailPanel.value = true;
  await loadReplenishEmailSummary();
}

async function importReplenishEmails() {
  const emails = replenishEmailsText.value
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (!emails.length) {
    store.toast("缺少邮箱", "请填写至少一个邮箱。", "warning");
    return;
  }
  importingReplenishEmails.value = true;
  try {
    const result = await resourcesApi.importSpaceReplenishEmails({ emails });
    replenishEmailSummary.value = result;
    replenishEmailsText.value = "";
    store.toast("补号邮箱已导入", `新增=${result.inserted ?? 0} 已存在=${result.existing ?? 0} 可用=${result.available_count ?? 0}`, "success");
  } catch (err) {
    store.toast("补号邮箱导入失败", String((err as Error).message ?? err), "error");
  } finally {
    importingReplenishEmails.value = false;
  }
}

async function prepareAutoReplenishInvites() {
  const id = String(autoInviteTarget.value?.id || "");
  if (!id) return;
  preparingAutoInviteId.value = id;
  try {
    const result = await resourcesApi.prepareSpaceAutoReplenishInvites(id, {
      created_by: "ops:space-server-invite",
    });
    const name = String(autoInviteTarget.value?.name || autoInviteTarget.value?.external_space_id || id);
    autoInviteTarget.value = null;
    store.toast("服务端邀请 Job 已创建", `${name} · 固定 1000 个补号邮箱`, "success");
    if (result.job_id) await router.push({ name: "job-trace", params: { jobId: result.job_id } });
  } catch (err) {
    store.toast("服务端邀请 Job 创建失败", String((err as Error).message ?? err), "error");
  } finally {
    preparingAutoInviteId.value = "";
  }
}

async function hostAutoReplenishment() {
  const id = String(hostingTarget.value?.id || "");
  if (!id) return;
  updatingHostingSpaceId.value = id;
  try {
    const result = await resourcesApi.hostSpaceAutoReplenishment(id);
    const name = String(hostingTarget.value?.name || hostingTarget.value?.external_space_id || id);
    hostingTarget.value = null;
    store.toast("空间已托管", `${name} · ${String(result.external_space_id || "")}`, "success");
    await pageRef.value?.load();
  } catch (err) {
    store.toast("手动托管失败", String((err as Error).message ?? err), "error");
  } finally {
    updatingHostingSpaceId.value = "";
  }
}

async function cancelAutoReplenishmentHosting() {
  const id = String(unhostingTarget.value?.id || "");
  if (!id) return;
  updatingHostingSpaceId.value = id;
  try {
    await resourcesApi.cancelSpaceAutoReplenishmentHosting(id);
    const name = String(unhostingTarget.value?.name || unhostingTarget.value?.external_space_id || id);
    unhostingTarget.value = null;
    store.toast("空间已取消托管", name, "success");
    await pageRef.value?.load();
  } catch (err) {
    store.toast("取消托管失败", String((err as Error).message ?? err), "error");
  } finally {
    updatingHostingSpaceId.value = "";
  }
}

async function loadPaymentInventorySummary() {
  try {
    paymentInventorySummary.value = await resourcesApi.paymentMethodPoolSummary();
  } catch (err) {
    store.toast("支付资料库存读取失败", String((err as Error).message ?? err), "error");
  }
}

async function openPaymentPoolImport() {
  showPaymentPoolPanel.value = true;
  await loadPaymentInventorySummary();
}

async function importPaymentMethodPools() {
  const names = paymentNamesText.value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  const addresses = splitPaymentImportLines(paymentAddressesText.value);
  const cards = splitPaymentImportLines(paymentCardsText.value);
  if (!names.length && !addresses.length && !cards.length) {
    store.toast("缺少支付资料", "请至少填写姓名、地址或卡片中的一项。", "warning");
    return;
  }
  importingPaymentInventory.value = true;
  try {
    const result = await resourcesApi.importPaymentMethodPools({ names, addresses, cards });
    paymentInventorySummary.value = (result.summary as Row) || {};
    paymentNamesText.value = "";
    paymentAddressesText.value = "";
    paymentCardsText.value = "";
    store.toast(
      "支付资料已导入",
      `新增=${result.inserted_count ?? 0} 已存在=${result.existing_count ?? 0}`,
      "success",
    );
  } catch (err) {
    store.toast("支付资料导入失败", String((err as Error).message ?? err), "error");
  } finally {
    importingPaymentInventory.value = false;
  }
}

async function bindPersonalPaymentMethod() {
  const id = String(paymentBindTarget.value?.id || "");
  if (!id) return;
  bindingPaymentSpaceId.value = id;
  try {
    const name = String(paymentBindTarget.value?.name || paymentBindTarget.value?.external_space_id || id);
    const result = await resourcesApi.bindPersonalPaymentMethod(id, {
      auto_start_plus_checkout: autoStartPlusCheckout.value,
      checkout_ui_mode: "custom",
      created_by: "ops:personal-payment-method-bind",
    });
    paymentBindTarget.value = null;
    store.toast("绑卡 Job 已创建", name, "success");
    await pageRef.value?.load();
    if (result.job_id) {
      await router.push({ name: "job-trace", params: { jobId: result.job_id } });
    }
  } catch (err) {
    store.toast("绑卡 Job 创建失败", String((err as Error).message ?? err), "error");
  } finally {
    bindingPaymentSpaceId.value = "";
  }
}

async function createPersonalPlusCheckout() {
  const id = String(plusCheckoutTarget.value?.id || "");
  if (!id) return;
  const createCountry = plusCheckoutCreateCountry.value.trim().toUpperCase();
  const promoCountry = plusCheckoutPromoCountry.value.trim().toUpperCase();
  const campaign = plusCheckoutCampaign.value.trim();
  if (!/^[A-Z]{2}$/.test(createCountry) || !/^[A-Z]{2}$/.test(promoCountry) || !campaign) {
    store.toast("支付配置无效", "US/JP 必须是两位国家代码，优惠 ID 不能为空。", "warning");
    return;
  }
  plusCheckoutSpaceId.value = id;
  try {
    const name = String(plusCheckoutTarget.value?.name || plusCheckoutTarget.value?.external_space_id || id);
    const result = await resourcesApi.createPersonalPlusCheckout(id, {
      create_proxy_country: createCountry,
      promo_proxy_country: promoCountry,
      promo_campaign_id: campaign,
      created_by: "ops:personal-plus-checkout",
    });
    plusCheckoutTarget.value = null;
    store.toast("Plus 支付 Job 已创建", `${name} · ${createCountry}/${promoCountry}`, "success");
    await pageRef.value?.load();
    if (result.job_id) await router.push({ name: "job-trace", params: { jobId: result.job_id } });
  } catch (err) {
    store.toast("Plus 支付 Job 创建失败", String((err as Error).message ?? err), "error");
  } finally {
    plusCheckoutSpaceId.value = "";
  }
}

function updateSelection(rows: Row[]) {
  selectedSpaces.value = rows;
}

async function openSelectedPaymentMethodBind() {
  if (!selectedSpaceIds.value.length) {
    store.toast("未选择账号", "请先选择需要绑定支付方式的个人空间。", "warning");
    return;
  }
  selectedPaymentBindOpen.value = true;
  await loadPaymentInventorySummary();
}

async function bindSelectedPersonalPaymentMethods() {
  const spaceIds = selectedSpaceIds.value;
  if (!spaceIds.length) return;
  bindingSelectedPaymentSpaces.value = true;
  try {
    const result = await resourcesApi.bindSelectedPersonalPaymentMethods({
      space_ids: spaceIds,
      auto_start_plus_checkout: autoStartPlusCheckout.value,
      checkout_ui_mode: "custom",
      created_by: "ops:personal-payment-method-bind-selected",
    });
    if (!result.job_id) {
      const firstReason = result.selection_skipped[0]?.reason || "没有符合条件的个人空间";
      store.toast(
        "未创建绑卡 Job",
        `选中=${result.requested_count} 跳过=${result.selection_skipped_count} · ${firstReason}`,
        "warning",
      );
      return;
    }
    selectedPaymentBindOpen.value = false;
    store.toast(
      "批量绑卡 Job 已创建",
      `选中=${result.requested_count} 排队=${result.selected_count} 跳过=${result.selection_skipped_count}`,
      result.selection_skipped_count ? "warning" : "success",
    );
    pageRef.value?.clearSelection();
    await pageRef.value?.load();
    await router.push({ name: "job-trace", params: { jobId: result.job_id } });
  } catch (err) {
    store.toast("批量绑卡 Job 创建失败", String((err as Error).message ?? err), "error");
  } finally {
    bindingSelectedPaymentSpaces.value = false;
  }
}

function openSelectedPromotionCheck() {
  if (!selectedSpaceIds.value.length) {
    store.toast("未选择账号", "请先选择需要检测优惠的个人空间。", "warning");
    return;
  }
  selectedPromotionCheckOpen.value = true;
}

async function checkSelectedPersonalPromotions() {
  const spaceIds = selectedSpaceIds.value;
  if (!spaceIds.length) return;
  const proxyCountry = promotionProxyCountry.value.trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(proxyCountry)) {
    store.toast("代理国家无效", "请输入两位国家代码，例如 JP。", "warning");
    return;
  }
  const workCount = Number(promotionWorkCount.value);
  if (!Number.isInteger(workCount) || workCount < 1 || workCount > 50) {
    store.toast("并发数无效", "并发数必须是 1 到 50 的整数。", "warning");
    return;
  }
  checkingSelectedPromotions.value = true;
  try {
    const result = await resourcesApi.checkSelectedPersonalPromotions({
      space_ids: spaceIds,
      proxy_country: proxyCountry,
      work_count: workCount,
      created_by: "ops:personal-promotion-check-selected",
    });
    if (!result.job_id) {
      const firstReason = result.selection_skipped[0]?.reason || "没有符合条件的个人空间";
      store.toast(
        "未创建优惠检测 Job",
        `选中=${result.requested_count} 跳过=${result.selection_skipped_count} · ${firstReason}`,
        "warning",
      );
      return;
    }
    promotionProxyCountry.value = proxyCountry;
    selectedPromotionCheckOpen.value = false;
    store.toast(
      "优惠检测 Job 已创建",
      `国家=${proxyCountry} 选中=${result.requested_count} 排队=${result.selected_count} 跳过=${result.selection_skipped_count}`,
      result.selection_skipped_count ? "warning" : "success",
    );
    pageRef.value?.clearSelection();
    await pageRef.value?.load();
    await router.push({ name: "job-trace", params: { jobId: result.job_id } });
  } catch (err) {
    store.toast("优惠检测 Job 创建失败", String((err as Error).message ?? err), "error");
  } finally {
    checkingSelectedPromotions.value = false;
  }
}

onMounted(() => {
  void loadAdminSessions();
  void loadReplenishEmailSummary();
  void loadPaymentInventorySummary();
});
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
    @selection-change="updateSelection"
  >
    <template #actions>
      <button class="btn primary" @click="showCredentialPanel = true"><KeyRound :size="16" />创建 Business AT</button>
      <button class="btn" :disabled="!selectedSpaceIds.length || bindingSelectedPaymentSpaces" @click="openSelectedPaymentMethodBind">
        <CreditCard :size="16" />绑定选中账号（{{ selectedSpaceIds.length }}）
      </button>
      <button class="btn" :disabled="!selectedSpaceIds.length || checkingSelectedPromotions" @click="openSelectedPromotionCheck">
        <BadgePercent :size="16" />检测选中优惠（{{ selectedSpaceIds.length }}）
      </button>
      <button class="btn" @click="openPaymentPoolImport"><CreditCard :size="16" />支付资料池</button>
      <button class="btn" @click="openReplenishEmailImport"><Upload :size="16" />导入补号邮箱</button>
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
          v-if="String(row.space_type || '') === 'personal' && Boolean(row.has_promotion) && !Boolean(row.has_payment_method)"
          class="btn primary small"
          :disabled="String(row.space_status || '') !== 'active' || Boolean(row.payment_method_cooldown_active) || bindingPaymentSpaceId === String(row.id || '')"
          title="为个人空间创建绑卡 Job"
          @click.stop="paymentBindTarget = row"
        >
          <CreditCard :size="14" />绑定支付方式
        </button>
        <button
          v-if="String(row.space_type || '') === 'personal' && Boolean(row.has_promotion) && Boolean(row.has_payment_method) && String(row.payment_method_status || '') === 'bound'"
          class="btn primary small"
          :disabled="String(row.space_status || '') !== 'active' || plusCheckoutSpaceId === String(row.id || '')"
          title="使用已有支付方式提交 Plus Checkout"
          @click.stop="plusCheckoutTarget = row"
        >
          <BadgePercent :size="14" />Plus 支付
        </button>
        <label
          v-if="String(row.space_type || '') === 'business'"
          class="auto-replenish-toggle"
          title="开启或关闭该空间的自动补号"
          @click.stop
        >
          <input
            type="checkbox"
            :checked="Boolean(row.auto_replenish_enabled)"
            :disabled="updatingAutoReplenishId === String(row.id || '')"
            @change="updateAutoReplenish(row, $event)"
          />
          <span>自动补号</span>
        </label>
        <button
          v-if="String(row.space_type || '') === 'business'"
          class="btn primary small"
          :disabled="String(row.space_status || '') !== 'active' || preparingAutoInviteId === String(row.id || '')"
          title="提交 1000 个邮箱到邀请服务器，并启用该空间的服务端自动补号"
          @click.stop="autoInviteTarget = row"
        >
          <UserPlus :size="14" />服务端邀请
        </button>
        <button
          v-if="String(row.space_type || '') === 'business'"
          class="btn small"
          :disabled="String(row.space_status || '') !== 'active' || updatingHostingSpaceId === String(row.id || '')"
          title="将管理员登录态、静态住宅代理和空间配置注册到服务端"
          @click.stop="hostingTarget = row"
        >
          <Server :size="14" />{{ row.auto_replenish_enabled ? '更新托管' : '手动托管' }}
        </button>
        <button
          v-if="String(row.space_type || '') === 'business' && Boolean(row.auto_replenish_enabled)"
          class="btn danger small"
          :disabled="updatingHostingSpaceId === String(row.id || '')"
          title="从服务端删除该空间的自动补号配置"
          @click.stop="unhostingTarget = row"
        >
          <ServerOff :size="14" />取消托管
        </button>
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

  <FormDrawer :open="showReplenishEmailPanel" title="导入补号邮箱" submit-text="导入邮箱" :busy="importingReplenishEmails" width="wide" @close="showReplenishEmailPanel = false" @submit="importReplenishEmails">
    <div class="inventory-summary">
      <span>总库存 <strong>{{ replenishEmailSummary.total ?? 0 }}</strong></span>
      <span>当前可用 <strong>{{ replenishEmailSummary.available_count ?? 0 }}</strong></span>
    </div>
    <label class="field"><span>邮箱列表</span><textarea v-model="replenishEmailsText" class="textarea large-textarea" required placeholder="每行一个邮箱" /></label>
  </FormDrawer>

  <FormDrawer :open="showPaymentPoolPanel" title="支付资料池" description="填哪类就导入哪类，未填写的类型直接跳过。" submit-text="导入资料" :busy="importingPaymentInventory" width="wide" @close="showPaymentPoolPanel = false" @submit="importPaymentMethodPools">
    <div class="inventory-summary payment-inventory-summary">
      <span>姓名 <strong>{{ paymentInventorySummary.active_name_count ?? 0 }}</strong></span>
      <span>地址 <strong>{{ paymentInventorySummary.active_address_count ?? 0 }}</strong></span>
      <span>可用卡 <strong>{{ paymentInventorySummary.available_card_count ?? 0 }}</strong></span>
      <span>待绑定空间 <strong>{{ paymentInventorySummary.pending_personal_space_count ?? 0 }}</strong></span>
    </div>
    <label class="field"><span>姓名</span><textarea v-model="paymentNamesText" class="textarea compact-textarea" placeholder="Ada Lovelace" /></label>
    <label class="field"><span>地址列表</span><textarea v-model="paymentAddressesText" class="textarea large-textarea" placeholder="310 Jefferson Street, Middletown, Delaware 19709, United States" /></label>
    <label class="field"><span>卡片列表</span><textarea v-model="paymentCardsText" class="textarea large-textarea" placeholder="Live | CARD_NUMBER|01|2030|CVC | [BIN: ...] | Charge OK." /></label>
  </FormDrawer>

  <ConfirmModal :open="Boolean(deleteAdminTarget)" title="删除空间管理员及关联空间" message="会删除该管理员、本地空间、空间成员和空间凭证；保留任务与推送记录，不调用远端删除。" :summary="{ '管理员邮箱': deleteAdminTarget?.admin_email, 'Session ID': deleteAdminTarget?.id }" confirm-text="确认删除" danger :busy="Boolean(deletingAdminSessionId)" @close="deleteAdminTarget = null" @confirm="deleteAdminSession" />
  <ConfirmModal :open="Boolean(syncTarget)" title="同步远端成员" message="读取远端 users 和 invites 后覆盖本地成员关系；本地存在但远端不存在的该空间成员关系会被物理删除，不会发送邀请。" :summary="{ '空间': syncTarget?.name, '外部空间 ID': syncTarget?.external_space_id }" confirm-text="开始同步" :busy="Boolean(syncingSpaceId)" @close="syncTarget = null" @confirm="syncRemoteMemberships" />
  <ConfirmModal :open="Boolean(seatExpansionTarget)" title="扩到 999 席位" message="使用该空间管理员登录态和静态住宅代理，分阶段提交席位更新并读取远端结果确认。" :summary="{ '空间': seatExpansionTarget?.name, '外部空间 ID': seatExpansionTarget?.external_space_id, '当前席位': seatExpansionTarget?.seats_entitled }" confirm-text="创建扩席位 Job" :busy="Boolean(expandingSpaceId)" @close="seatExpansionTarget = null" @confirm="expandSeats" />
  <ConfirmModal
    :open="Boolean(paymentBindTarget)"
    title="绑定个人空间支付方式"
    message="使用该账号绑定的静态代理登录个人空间，并依次尝试最多三张未使用卡片。"
    :summary="{ '空间': paymentBindTarget?.name, '外部空间 ID': paymentBindTarget?.external_space_id, '已尝试': paymentBindTarget?.payment_method_attempt_count, '冷却至': paymentBindTarget?.payment_method_cooldown_until || '无', '可用卡': paymentInventorySummary.available_card_count ?? 0 }"
    confirm-text="创建绑卡 Job"
    :busy="Boolean(bindingPaymentSpaceId)"
    @close="paymentBindTarget = null"
    @confirm="bindPersonalPaymentMethod"
  >
    <label class="auto-replenish-toggle">
      <input v-model="autoStartPlusCheckout" type="checkbox" />
      <span>绑卡成功后继续 Plus 支付</span>
    </label>
  </ConfirmModal>
  <ConfirmModal
    :open="Boolean(plusCheckoutTarget)"
    title="提交 Plus Checkout"
    message="前置要求为有效优惠和已绑定支付方式；先用 US 创建 Checkout，再用 JP 更新优惠并提交。支付成功后重新获取 Session。"
    :summary="{ '空间': plusCheckoutTarget?.name, '优惠': plusCheckoutTarget?.promotion_id, '支付卡': plusCheckoutTarget?.payment_method_last4 || '已绑定' }"
    confirm-text="创建 Plus 支付 Job"
    :busy="Boolean(plusCheckoutSpaceId)"
    @close="plusCheckoutTarget = null"
    @confirm="createPersonalPlusCheckout"
  >
    <div class="promotion-check-config">
      <label class="field"><span>创建 Checkout 代理国家</span><input v-model="plusCheckoutCreateCountry" class="input" maxlength="2" autocomplete="off" /></label>
      <label class="field"><span>更新优惠代理国家</span><input v-model="plusCheckoutPromoCountry" class="input" maxlength="2" autocomplete="off" /></label>
      <label class="field"><span>优惠 campaign</span><input v-model="plusCheckoutCampaign" class="input" autocomplete="off" /></label>
    </div>
  </ConfirmModal>
  <ConfirmModal
    :open="selectedPaymentBindOpen"
    title="批量绑定个人空间支付方式"
    message="为选中的有效个人空间创建绑卡 Work；已绑定、冷却中、非个人空间、无效账号和已有活动绑卡任务的项目会跳过。每个空间仍按现有规则最多尝试三张卡。"
    :summary="{ '选中空间': selectedSpaceIds.length, '个人空间': selectedPersonalSpaceCount, '未绑定且可尝试': selectedUnboundPersonalSpaceCount, '可用卡': paymentInventorySummary.available_card_count ?? 0 }"
    confirm-text="创建批量绑卡 Job"
    :busy="bindingSelectedPaymentSpaces"
    @close="selectedPaymentBindOpen = false"
    @confirm="bindSelectedPersonalPaymentMethods"
  >
    <label class="auto-replenish-toggle">
      <input v-model="autoStartPlusCheckout" type="checkbox" />
      <span>绑卡成功后继续 Plus 支付</span>
    </label>
  </ConfirmModal>
  <ConfirmModal
    :open="selectedPromotionCheckOpen"
    title="检测选中个人空间优惠"
    message="使用配置国家的 Backbone 代理检测选中个人空间，检测结果会更新空间列表中的优惠状态。"
    :summary="{ '选中空间': selectedSpaceIds.length, '个人空间': selectedPersonalSpaceCount }"
    confirm-text="创建优惠检测 Job"
    :busy="checkingSelectedPromotions"
    @close="selectedPromotionCheckOpen = false"
    @confirm="checkSelectedPersonalPromotions"
  >
    <div class="promotion-check-config">
      <label class="field">
        <span>代理国家</span>
        <input v-model="promotionProxyCountry" class="input" maxlength="2" autocomplete="off" placeholder="JP" />
      </label>
      <label class="field">
        <span>并发数</span>
        <input v-model.number="promotionWorkCount" class="input" type="number" min="1" max="50" step="1" />
      </label>
    </div>
  </ConfirmModal>
  <ConfirmModal
    :open="Boolean(autoInviteTarget)"
    title="服务端邀请"
    message="只从本地补号邮箱选择 1000 个并提交到邀请服务器，同时开启该 Space 的服务端自动补号；库存不足时不会从账号表补齐。"
    :summary="{ '空间': autoInviteTarget?.name, '外部空间 ID': autoInviteTarget?.external_space_id, '自动补号': autoInviteTarget?.auto_replenish_enabled ? '已开启' : '确认后开启', '本地邮箱可用': replenishEmailSummary.available_count ?? 0 }"
    confirm-text="创建服务端邀请 Job"
    :busy="Boolean(preparingAutoInviteId)"
    @close="autoInviteTarget = null"
    @confirm="prepareAutoReplenishInvites"
  />
  <ConfirmModal
    :open="Boolean(hostingTarget)"
    title="手动托管空间"
    message="把该空间的管理员登录态、绑定的静态住宅代理和补号配置注册到服务端；不会发送邀请。"
    :summary="{ '空间': hostingTarget?.name, '外部空间 ID': hostingTarget?.external_space_id, '席位上限': hostingTarget?.seat_limit, '托管状态': hostingTarget?.auto_replenish_enabled ? '更新现有配置' : '新增托管' }"
    confirm-text="确认托管"
    :busy="Boolean(updatingHostingSpaceId)"
    @close="hostingTarget = null"
    @confirm="hostAutoReplenishment"
  />
  <ConfirmModal
    :open="Boolean(unhostingTarget)"
    title="取消空间托管"
    message="从服务端删除该空间的自动补号配置；不会删除本地空间、成员、凭证和历史记录。"
    :summary="{ '空间': unhostingTarget?.name, '外部空间 ID': unhostingTarget?.external_space_id }"
    confirm-text="确认取消托管"
    danger
    :busy="Boolean(updatingHostingSpaceId)"
    @close="unhostingTarget = null"
    @confirm="cancelAutoReplenishmentHosting"
  />
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
  align-items: center;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.auto-replenish-toggle {
  align-items: center;
  color: var(--text-muted);
  display: inline-flex;
  font-size: 12px;
  gap: 6px;
  white-space: nowrap;
}

.auto-replenish-toggle input { accent-color: var(--accent); }

.browser-mode-checkbox {
  align-items: center;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text);
  display: flex;
  font-size: 13px;
  gap: 8px;
  min-height: 42px;
  padding: 0 12px;
}

.browser-mode-checkbox input { accent-color: var(--accent); }

.inventory-summary {
  align-items: center;
  border-bottom: 1px solid var(--border);
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  padding-bottom: 12px;
}

.inventory-summary span { color: var(--text-muted); font-size: 12px; }
.inventory-summary strong { color: var(--text); font-size: 16px; margin-left: 5px; }

.small {
  padding: 8px 10px;
  white-space: nowrap;
}

.promotion-check-config {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

@media (max-width: 767px) {
  .panel-heading {
    align-items: stretch;
    flex-direction: column;
  }

  .promotion-check-config {
    grid-template-columns: 1fr;
  }
}
</style>
