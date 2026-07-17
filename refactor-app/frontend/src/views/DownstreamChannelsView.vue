<script setup lang="ts">
import { Plus, Send, Settings2, Trash2 } from "@lucide/vue";
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";

import type { PagedResult, PageQuery, Row } from "../api/types";
import { resourcesApi } from "../api/resources";
import ConfirmModal from "../components/ConfirmModal.vue";
import type { Column, TableFilter } from "../components/DataTable.vue";
import FormDrawer from "../components/FormDrawer.vue";
import ResourcePage from "../components/ResourcePage.vue";
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();
const router = useRouter();
const pageRef = ref<InstanceType<typeof ResourcePage> | null>(null);
const createOpen = ref(false);
const editingChannel = ref<Row | null>(null);
const deleteTarget = ref<Row | null>(null);
const saving = ref(false);
const deleting = ref(false);
const pendingPushWorkCount = ref(5);
const balanceAmounts = ref<Record<string, number>>({});
const slotAmounts = ref<Record<string, number>>({});

const emptyForm = () => ({
  provider_type: "sub2api", name: "", base_url: "", admin_key: "",
  custom_payload_type: "sub2api", custom_auth_header_name: "", custom_auth_header_value: "",
  enabled: true, update_existing: true, timeout_s: 30, sub2api_concurrency: 10,
  sub2api_group_ids: "", max_active_slots: 1,
});
const form = ref(emptyForm());
const editForm = ref(emptyForm());

const columns: Column[] = [
  { key: "name", label: "渠道名称", sortable: true },
  { key: "provider_type", label: "类型", badge: true, sortable: true },
  { key: "custom_payload_type", label: "Payload", badge: true },
  { key: "enabled", label: "启用", type: "boolean" },
  { key: "base_url", label: "地址", mono: true, summary: 42, copyable: true },
  { key: "balance_summary", label: "余额 / 占用 / 最大坑位", summary: 64 },
  { key: "sub2api_concurrency", label: "下游同时账号数" },
  { key: "timeout_s", label: "超时（秒）" },
  { key: "updated_at", label: "更新时间", type: "datetime", relativeTime: true, sortable: true },
];
const filters: TableFilter[] = [
  { key: "provider_type", label: "渠道类型", options: [
    { label: "sub2api", value: "sub2api" }, { label: "CPA", value: "cpa" },
    { label: "本地文件", value: "local_sub2api" }, { label: "自定义 HTTP", value: "custom_http" },
  ] },
  { key: "enabled", label: "启用状态", options: [
    { label: "启用", value: "yes" }, { label: "停用", value: "no" },
  ] },
];

const credentialTypeLabels: Record<string, string> = {
  personal_account: "个人账号", team_5h_weekly: "Team 5h/周", team_monthly: "Team 月",
};
const activeForm = computed(() => editingChannel.value ? editForm.value : form.value);
const isLocal = computed(() => activeForm.value.provider_type === "local_sub2api");
const isCustom = computed(() => activeForm.value.provider_type === "custom_http");

watch(() => activeForm.value.provider_type, (providerType) => {
  if (["local_sub2api", "custom_http"].includes(providerType)) activeForm.value.admin_key = "";
  if (providerType !== "custom_http") {
    activeForm.value.custom_auth_header_name = "";
    activeForm.value.custom_auth_header_value = "";
  }
});

function balances(row: Row) {
  return Array.isArray(row.credential_type_balances) ? row.credential_type_balances as Row[] : [];
}
function balanceKey(row: Row, balance: Row) { return `${row.id}:${balance.credential_type}`; }
function typeName(value: unknown) { return credentialTypeLabels[String(value || "")] || String(value || ""); }
function balanceSummary(row: Row) {
  return balances(row).map((item) =>
    `${typeName(item.credential_type)} ${item.push_balance ?? 0}/${item.active_slot_count ?? 0}/${item.max_active_slots ?? 0}`,
  ).join("；") || "-";
}

async function loader(query: PageQuery): Promise<PagedResult<Row>> {
  const result = await resourcesApi.downstreamChannels(query);
  return { ...result, items: result.items.map((row) => ({ ...row, balance_summary: balanceSummary(row) })) };
}

function validate(value: ReturnType<typeof emptyForm>) {
  if (!value.name.trim()) return "渠道名称不能为空。";
  if (value.provider_type !== "local_sub2api" && !value.base_url.trim()) return "渠道地址不能为空。";
  if (!["local_sub2api", "custom_http"].includes(value.provider_type) && !value.admin_key.trim() && !editingChannel.value) return "管理密钥不能为空。";
  if (value.provider_type === "custom_http") {
    if (!value.custom_payload_type) return "请选择自定义 Payload 类型。";
    if (Boolean(value.custom_auth_header_name.trim()) !== Boolean(value.custom_auth_header_value.trim())) return "认证头名称和值必须同时填写。";
  }
  return "";
}

function payload(value: ReturnType<typeof emptyForm>) {
  const localOrCustom = ["local_sub2api", "custom_http"].includes(value.provider_type);
  return {
    ...value,
    name: value.name.trim(), base_url: value.base_url.trim(),
    admin_key: localOrCustom ? "" : value.admin_key.trim(),
    custom_payload_type: value.provider_type === "custom_http" ? value.custom_payload_type : "",
    custom_auth_header_name: value.provider_type === "custom_http" ? value.custom_auth_header_name.trim() : "",
    custom_auth_header_value: value.provider_type === "custom_http" ? value.custom_auth_header_value.trim() : "",
    timeout_s: Number(value.timeout_s || 30), sub2api_concurrency: Number(value.sub2api_concurrency || 0),
  };
}

async function createChannel() {
  const issue = validate(form.value);
  if (issue) { store.toast("参数不完整", issue, "warning"); return; }
  saving.value = true;
  try {
    await resourcesApi.createDownstreamChannel(payload(form.value));
    store.toast("渠道已创建", form.value.name, "success");
    form.value = emptyForm(); createOpen.value = false; await pageRef.value?.load();
  } catch (err) { store.toast("创建失败", String((err as Error).message ?? err), "error"); }
  finally { saving.value = false; }
}

function openEdit(row: Row) {
  editingChannel.value = row;
  editForm.value = {
    provider_type: String(row.provider_type || "sub2api"), name: String(row.name || ""),
    base_url: String(row.base_url || ""), admin_key: "",
    custom_payload_type: String(row.custom_payload_type || "sub2api"),
    custom_auth_header_name: String(row.custom_auth_header_name || ""), custom_auth_header_value: "",
    enabled: Boolean(row.enabled), update_existing: Boolean(row.update_existing),
    timeout_s: Number(row.timeout_s || 30), sub2api_concurrency: Number(row.sub2api_concurrency || 0),
    sub2api_group_ids: String(row.sub2api_group_ids || ""), max_active_slots: Number(row.max_active_slots || 0),
  };
  balances(row).forEach((item) => { slotAmounts.value[balanceKey(row, item)] = Number(item.max_active_slots || 0); });
}

async function saveChannel() {
  const row = editingChannel.value; if (!row?.id) return;
  const issue = validate(editForm.value);
  if (issue) { store.toast("参数不完整", issue, "warning"); return; }
  const body = payload(editForm.value);
  if (!editForm.value.admin_key.trim() && !["local_sub2api", "custom_http"].includes(editForm.value.provider_type)) delete (body as Record<string, unknown>).admin_key;
  if (!editForm.value.custom_auth_header_value.trim() && editForm.value.provider_type === "custom_http") delete (body as Record<string, unknown>).custom_auth_header_value;
  saving.value = true;
  try {
    await resourcesApi.patchDownstreamChannel(String(row.id), body);
    store.toast("渠道已保存", editForm.value.name, "success"); editingChannel.value = null; await pageRef.value?.load();
  } catch (err) { store.toast("保存失败", String((err as Error).message ?? err), "error"); }
  finally { saving.value = false; }
}

async function toggleEnabled(row: Row) {
  try { await resourcesApi.patchDownstreamChannel(String(row.id), { enabled: !Boolean(row.enabled) }); await pageRef.value?.load(); }
  catch (err) { store.toast("更新失败", String((err as Error).message ?? err), "error"); }
}

async function pushPending(row: Row) {
  try {
    const result = await resourcesApi.pushPendingCredentials({ downstream_channel_id: String(row.id), work_count: pendingPushWorkCount.value, created_by: "ops-ui-channel" });
    store.toast("推送任务已创建", `Work=${result.work_count}`, "success");
    await router.push({ name: "job-trace", params: { jobId: result.job_id } });
  } catch (err) { store.toast("推送失败", String((err as Error).message ?? err), "error"); }
}

async function addBalance(balance: Row) {
  const row = editingChannel.value; if (!row?.id) return;
  const key = balanceKey(row, balance); const amount = Number(balanceAmounts.value[key] || 0);
  if (amount <= 0) { store.toast("余额无效", "新增余额必须大于 0。", "warning"); return; }
  try {
    await resourcesApi.addDownstreamChannelBalance(String(row.id), { credential_type: String(balance.credential_type), amount });
    balanceAmounts.value[key] = 0; await refreshEdit(String(row.id));
  } catch (err) { store.toast("添加余额失败", String((err as Error).message ?? err), "error"); }
}

async function saveSlots(balance: Row) {
  const row = editingChannel.value; if (!row?.id) return;
  const key = balanceKey(row, balance); const value = Number(slotAmounts.value[key]);
  if (!Number.isFinite(value) || value < 0) { store.toast("坑位无效", "最大坑位不能小于 0。", "warning"); return; }
  try {
    await resourcesApi.patchDownstreamChannelCredentialTypeBalance(String(row.id), String(balance.credential_type), { max_active_slots: value });
    await refreshEdit(String(row.id));
  } catch (err) { store.toast("保存坑位失败", String((err as Error).message ?? err), "error"); }
}

async function refreshEdit(id: string) {
  const result = await resourcesApi.downstreamChannels({ q: id, page_size: 20 });
  const row = result.items.find((item) => String(item.id) === id);
  if (row) { editingChannel.value = row; balances(row).forEach((item) => { slotAmounts.value[balanceKey(row, item)] = Number(item.max_active_slots || 0); }); }
  await pageRef.value?.load();
}

async function deleteChannel() {
  const id = String(deleteTarget.value?.id || ""); if (!id) return;
  deleting.value = true;
  try { await resourcesApi.deleteDownstreamChannel(id); store.toast("渠道已删除", id, "success"); deleteTarget.value = null; await pageRef.value?.load(); }
  catch (err) { store.toast("删除失败", String((err as Error).message ?? err), "error"); }
  finally { deleting.value = false; }
}
</script>

<template>
  <ResourcePage ref="pageRef" title="下游渠道" description="维护渠道连接、Payload、按凭证类型的推送余额和最大坑位。" :columns="columns" :loader="loader" :filters="filters" empty-text="暂无下游渠道。">
    <template #actions>
      <div class="action-group"><label class="inline-control"><span>推送 Work 数</span><input v-model.number="pendingPushWorkCount" class="input small-input" type="number" min="1" max="500" /></label></div>
      <span class="action-spacer" />
      <button class="btn primary" @click="createOpen = true"><Plus :size="16" />新增渠道</button>
    </template>
    <template #rowActions="{ row }">
      <button class="icon-btn" title="编辑渠道" @click="openEdit(row)"><Settings2 :size="15" /></button>
      <button class="icon-btn" title="推送待推送凭证" @click="pushPending(row)"><Send :size="15" /></button>
      <button class="btn" @click="toggleEnabled(row)">{{ row.enabled ? "停用" : "启用" }}</button>
      <button class="icon-btn danger" title="删除渠道" @click="deleteTarget = row"><Trash2 :size="15" /></button>
    </template>
  </ResourcePage>

  <FormDrawer :open="createOpen" title="新增下游渠道" description="创建后再按凭证类型维护余额和坑位。" submit-text="新增渠道" :busy="saving" width="wide" @close="createOpen = false" @submit="createChannel">
    <section class="drawer-section"><h3>基础信息</h3><div class="drawer-grid">
      <label class="field"><span>渠道类型</span><select v-model="form.provider_type" class="select"><option value="sub2api">sub2api</option><option value="cpa">CPA</option><option value="local_sub2api">本地 sub2api 文件</option><option value="custom_http">自定义 HTTP</option></select></label>
      <label class="field"><span>渠道名称</span><input v-model="form.name" class="input" /></label>
      <label class="field wide"><span>{{ isLocal ? '输出目录' : '接口地址' }}</span><input v-model="form.base_url" class="input" /></label>
      <label v-if="!isLocal && !isCustom" class="field wide"><span>管理密钥</span><input v-model="form.admin_key" class="input" type="password" /></label>
    </div></section>
    <section v-if="isCustom" class="drawer-section"><h3>自定义 HTTP</h3><div class="drawer-grid">
      <label class="field"><span>Payload 类型</span><select v-model="form.custom_payload_type" class="select"><option value="sub2api">sub2api 授权 JSON</option><option value="sub2api_admin_accounts">sub2api Admin Accounts</option><option value="cpa">CPA 授权 JSON</option></select></label>
      <label class="field"><span>认证头名称</span><input v-model="form.custom_auth_header_name" class="input" /></label>
      <label class="field wide"><span>认证头值</span><input v-model="form.custom_auth_header_value" class="input" type="password" /></label>
    </div></section>
    <section class="drawer-section"><h3>推送规则</h3><div class="drawer-grid">
      <label class="field"><span>超时秒数</span><input v-model.number="form.timeout_s" class="input" type="number" min="1" /></label>
      <label class="field"><span>下游同时账号数</span><input v-model.number="form.sub2api_concurrency" class="input" type="number" min="0" /></label>
      <label class="field"><span>默认最大坑位</span><input v-model.number="form.max_active_slots" class="input" type="number" min="0" /></label>
      <label class="field"><span>sub2api 分组 ID</span><input v-model="form.sub2api_group_ids" class="input" /></label>
      <label class="check"><input v-model="form.enabled" type="checkbox" /><span>启用渠道</span></label>
      <label class="check"><input v-model="form.update_existing" type="checkbox" /><span>更新下游已有账号</span></label>
    </div></section>
  </FormDrawer>

  <FormDrawer :open="Boolean(editingChannel)" title="编辑下游渠道" :description="String(editingChannel?.name || '')" :busy="saving" width="wide" @close="editingChannel = null" @submit="saveChannel">
    <section class="drawer-section"><h3>基础信息</h3><div class="drawer-grid">
      <label class="field"><span>渠道类型</span><select v-model="editForm.provider_type" class="select"><option value="sub2api">sub2api</option><option value="cpa">CPA</option><option value="local_sub2api">本地 sub2api 文件</option><option value="custom_http">自定义 HTTP</option></select></label>
      <label class="field"><span>渠道名称</span><input v-model="editForm.name" class="input" /></label>
      <label class="field wide"><span>{{ isLocal ? '输出目录' : '接口地址' }}</span><input v-model="editForm.base_url" class="input" /></label>
      <label v-if="!isLocal && !isCustom" class="field wide"><span>管理密钥</span><input v-model="editForm.admin_key" class="input" type="password" placeholder="留空不修改" /></label>
    </div></section>
    <section v-if="isCustom" class="drawer-section"><h3>自定义 HTTP</h3><div class="drawer-grid">
      <label class="field"><span>Payload 类型</span><select v-model="editForm.custom_payload_type" class="select"><option value="sub2api">sub2api 授权 JSON</option><option value="sub2api_admin_accounts">sub2api Admin Accounts</option><option value="cpa">CPA 授权 JSON</option></select></label>
      <label class="field"><span>认证头名称</span><input v-model="editForm.custom_auth_header_name" class="input" /></label>
      <label class="field wide"><span>认证头值</span><input v-model="editForm.custom_auth_header_value" class="input" type="password" placeholder="留空不修改" /></label>
    </div></section>
    <section class="drawer-section"><h3>运行规则</h3><div class="drawer-grid">
      <label class="field"><span>超时秒数</span><input v-model.number="editForm.timeout_s" class="input" type="number" min="1" /></label>
      <label class="field"><span>下游同时账号数</span><input v-model.number="editForm.sub2api_concurrency" class="input" type="number" min="0" /></label>
      <label class="field wide"><span>sub2api 分组 ID</span><input v-model="editForm.sub2api_group_ids" class="input" /></label>
      <label class="check"><input v-model="editForm.enabled" type="checkbox" /><span>启用渠道</span></label>
      <label class="check"><input v-model="editForm.update_existing" type="checkbox" /><span>更新下游已有账号</span></label>
    </div></section>
    <section class="drawer-section"><h3>按凭证类型的余额与坑位</h3><div class="balance-table">
      <div v-for="balance in balances(editingChannel || {})" :key="String(balance.credential_type)" class="balance-row">
        <div><strong>{{ typeName(balance.credential_type) }}</strong><small>占用 {{ balance.active_slot_count ?? 0 }} · 剩余 {{ balance.remaining_active_slots ?? 0 }} · 已使用 {{ balance.used_count ?? 0 }}</small></div>
        <label><span>推送余额 {{ balance.push_balance ?? 0 }}</span><div><input v-model.number="balanceAmounts[balanceKey(editingChannel || {}, balance)]" class="input" type="number" min="1" placeholder="增加量" /><button class="btn" type="button" @click="addBalance(balance)">增加</button></div></label>
        <label><span>最大坑位</span><div><input v-model.number="slotAmounts[balanceKey(editingChannel || {}, balance)]" class="input" type="number" min="0" /><button class="btn" type="button" @click="saveSlots(balance)">保存</button></div></label>
      </div>
    </div></section>
  </FormDrawer>

  <ConfirmModal :open="Boolean(deleteTarget)" title="删除下游渠道" message="删除后该渠道不能继续接收推送。" :summary="{ '渠道名称': deleteTarget?.name, '渠道类型': deleteTarget?.provider_type, '渠道 ID': deleteTarget?.id }" confirm-text="确认删除" danger :busy="deleting" @close="deleteTarget = null" @confirm="deleteChannel" />
</template>

<style scoped>
.action-spacer { flex: 1; }.drawer-section { display: grid; gap: 10px; }.drawer-section + .drawer-section { border-top: 1px solid var(--border); padding-top: 14px; }.drawer-section h3 { font-size: 13px; margin: 0; }.drawer-grid { display: grid; gap: 10px; grid-template-columns: repeat(2, minmax(0, 1fr)); }.drawer-grid .wide { grid-column: 1 / -1; }.check { align-items: center; color: var(--text-muted); display: flex; font-size: 12px; gap: 7px; }.balance-table { border: 1px solid var(--border); border-radius: var(--radius-sm); }.balance-row { align-items: end; display: grid; gap: 10px; grid-template-columns: 1.2fr 1fr 1fr; padding: 10px; }.balance-row + .balance-row { border-top: 1px solid var(--border); }.balance-row strong, .balance-row small, .balance-row label > span { display: block; }.balance-row small, .balance-row label > span { color: var(--text-muted); font-size: 10px; margin-bottom: 4px; }.balance-row label > div { display: flex; gap: 5px; }.balance-row .input { min-width: 0; }
@media (max-width: 680px) { .drawer-grid, .balance-row { grid-template-columns: 1fr; } }
</style>
