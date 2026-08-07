<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { CreditCard, Edit3, MapPin, Plus, Trash2, Upload, UserRound } from "@lucide/vue";

import { resourcesApi, type Row } from "../api/resources";
import type { PageQuery, PagedResult } from "../api/types";
import ConfirmModal from "../components/ConfirmModal.vue";
import FormDrawer from "../components/FormDrawer.vue";
import ResourcePage from "../components/ResourcePage.vue";
import type { Column, TableFilter } from "../components/DataTable.vue";
import { useOpsStore } from "../stores/ops";
import { splitPaymentImportLines } from "../utils/paymentMethodImport";

type PoolKind = "names" | "addresses" | "cards";

type PoolConfig = {
  label: string;
  description: string;
  icon: typeof UserRound;
  loader: (params: PageQuery) => Promise<PagedResult<Row>>;
  columns: Column[];
  filters: TableFilter[];
};

const store = useOpsStore();
const activePool = ref<PoolKind>("names");
const pageRef = ref<InstanceType<typeof ResourcePage> | null>(null);
const summary = ref<Row>({});
const formOpen = ref(false);
const importOpen = ref(false);
const editingId = ref("");
const editingKind = ref<PoolKind>("names");
const deletingRow = ref<Row | null>(null);
const deletingKind = ref<PoolKind>("names");
const saving = ref(false);
const importing = ref(false);

const nameValue = ref("");
const nameStatus = ref("active");
const addressLine1 = ref("");
const addressLine2 = ref("");
const addressCity = ref("");
const addressState = ref("");
const addressPostalCode = ref("");
const addressCountry = ref("");
const addressPhone = ref("");
const addressStatus = ref("active");
const cardNumber = ref("");
const cardCvc = ref("");
const cardExpMonth = ref("");
const cardExpYear = ref("");
const cardStatus = ref("available");

const importNamesText = ref("");
const importAddressesText = ref("");
const importCardsText = ref("");

const configs: Record<PoolKind, PoolConfig> = {
  names: {
    label: "姓名池",
    description: "维护绑卡时随机使用的账单姓名。",
    icon: UserRound,
    loader: resourcesApi.paymentNamePool,
    columns: [
      { key: "full_name", label: "姓名", sortable: true },
      { key: "name_status", label: "状态", badge: true },
      { key: "use_count", label: "使用次数", type: "number", sortable: true },
      { key: "last_used_at", label: "最近使用", type: "datetime", relativeTime: true, sortable: true },
      { key: "updated_at", label: "更新时间", type: "datetime", relativeTime: true, sortable: true },
      { key: "id", label: "ID", mono: true, summary: 24, copyable: true },
    ],
    filters: [
      {
        key: "name_status",
        label: "状态",
        options: [
          { label: "有效", value: "active" },
          { label: "禁用", value: "disabled" },
        ],
      },
    ],
  },
  addresses: {
    label: "地址池",
    description: "维护 Stripe 账单地址，绑卡时随机选择。",
    icon: MapPin,
    loader: resourcesApi.paymentAddressPool,
    columns: [
      { key: "line1", label: "地址", summary: 34 },
      { key: "city", label: "城市", sortable: true },
      { key: "state", label: "州/省" },
      { key: "postal_code", label: "邮编", mono: true },
      { key: "country", label: "国家", mono: true, sortable: true },
      { key: "address_status", label: "状态", badge: true },
      { key: "use_count", label: "使用次数", type: "number", sortable: true },
      { key: "last_used_at", label: "最近使用", type: "datetime", relativeTime: true, sortable: true },
      { key: "id", label: "ID", mono: true, summary: 24, copyable: true },
    ],
    filters: [
      {
        key: "address_status",
        label: "状态",
        options: [
          { label: "有效", value: "active" },
          { label: "禁用", value: "disabled" },
        ],
      },
    ],
  },
  cards: {
    label: "卡片池",
    description: "管理卡片状态和失败记录；完整卡号与 CVC 不在列表中回显。",
    icon: CreditCard,
    loader: resourcesApi.paymentCardPool,
    columns: [
      { key: "card_number_masked", label: "卡号", mono: true },
      { key: "last4", label: "尾号", mono: true },
      { key: "exp_month", label: "月" },
      { key: "exp_year", label: "年" },
      { key: "card_status", label: "状态", badge: true, sortable: true },
      { key: "use_count", label: "使用次数", type: "number", sortable: true },
      { key: "last_error_code", label: "最近错误", summary: 30 },
      { key: "updated_at", label: "更新时间", type: "datetime", relativeTime: true, sortable: true },
      { key: "id", label: "ID", mono: true, summary: 24, copyable: true },
    ],
    filters: [
      {
        key: "card_status",
        label: "状态",
        options: [
          { label: "可用", value: "available" },
          { label: "使用中", value: "in_use" },
          { label: "已使用", value: "used" },
          { label: "失效", value: "failed" },
          { label: "禁用", value: "disabled" },
        ],
      },
    ],
  },
};

const activeConfig = computed(() => configs[activePool.value]);
const formTitle = computed(() => `${editingId.value ? "编辑" : "新增"}${configs[editingKind.value].label}`);

function resetForm() {
  nameValue.value = "";
  nameStatus.value = "active";
  addressLine1.value = "";
  addressLine2.value = "";
  addressCity.value = "";
  addressState.value = "";
  addressPostalCode.value = "";
  addressCountry.value = "";
  addressPhone.value = "";
  addressStatus.value = "active";
  cardNumber.value = "";
  cardCvc.value = "";
  cardExpMonth.value = "";
  cardExpYear.value = "";
  cardStatus.value = "available";
}

function openCreate(kind: PoolKind = activePool.value) {
  resetForm();
  editingId.value = "";
  editingKind.value = kind;
  formOpen.value = true;
}

function openEdit(kind: PoolKind, row: Row) {
  resetForm();
  editingId.value = String(row.id || "");
  editingKind.value = kind;
  if (kind === "names") {
    nameValue.value = String(row.full_name || "");
    nameStatus.value = String(row.name_status || "active");
  } else if (kind === "addresses") {
    addressLine1.value = String(row.line1 || "");
    addressLine2.value = String(row.line2 || "");
    addressCity.value = String(row.city || "");
    addressState.value = String(row.state || "");
    addressPostalCode.value = String(row.postal_code || "");
    addressCountry.value = String(row.country || "");
    addressPhone.value = String(row.phone || "");
    addressStatus.value = String(row.address_status || "active");
  } else {
    cardExpMonth.value = String(row.exp_month || "");
    cardExpYear.value = String(row.exp_year || "");
    cardStatus.value = String(row.card_status || "available");
  }
  formOpen.value = true;
}

async function savePoolItem() {
  const kind = editingKind.value;
  let body: Record<string, unknown>;
  if (kind === "names") {
    if (!nameValue.value.trim()) {
      store.toast("缺少姓名", "请填写姓名。", "warning");
      return;
    }
    body = { full_name: nameValue.value.trim(), name_status: nameStatus.value };
  } else if (kind === "addresses") {
    body = {
      line1: addressLine1.value,
      line2: addressLine2.value,
      city: addressCity.value,
      state: addressState.value,
      postal_code: addressPostalCode.value,
      country: addressCountry.value,
      phone: addressPhone.value,
      address_status: addressStatus.value,
    };
    if (!editingId.value && (!addressLine1.value.trim() || !addressCity.value.trim() || !addressPostalCode.value.trim() || !addressCountry.value.trim())) {
      store.toast("地址不完整", "请填写地址、城市、邮编和国家。", "warning");
      return;
    }
  } else {
    body = { card_status: cardStatus.value };
    if (!editingId.value) {
      body.card_number = cardNumber.value;
      body.cvc = cardCvc.value;
      body.exp_month = Number(cardExpMonth.value);
      body.exp_year = Number(cardExpYear.value);
      if (!cardNumber.value.trim() || !cardCvc.value.trim() || !cardExpMonth.value || !cardExpYear.value) {
        store.toast("卡片不完整", "请填写卡号、CVC、有效期。", "warning");
        return;
      }
    } else {
      if (cardNumber.value.trim()) body.card_number = cardNumber.value.trim();
      if (cardCvc.value.trim()) body.cvc = cardCvc.value.trim();
      if (cardExpMonth.value) body.exp_month = Number(cardExpMonth.value);
      if (cardExpYear.value) body.exp_year = Number(cardExpYear.value);
    }
  }

  saving.value = true;
  try {
    if (kind === "names") {
      if (editingId.value) await resourcesApi.patchPaymentName(editingId.value, body);
      else await resourcesApi.createPaymentName(body);
    } else if (kind === "addresses") {
      if (editingId.value) await resourcesApi.patchPaymentAddress(editingId.value, body);
      else await resourcesApi.createPaymentAddress(body);
    } else if (editingId.value) {
      await resourcesApi.patchPaymentCard(editingId.value, body);
    } else {
      await resourcesApi.createPaymentCard(body);
    }
    store.toast(editingId.value ? "资料已更新" : "资料已新增", configs[kind].label, "success");
    formOpen.value = false;
    await pageRef.value?.load();
    await loadSummary();
  } catch (err) {
    store.toast("保存失败", String((err as Error).message ?? err), "error");
  } finally {
    saving.value = false;
  }
}

async function deletePoolItem() {
  const row = deletingRow.value;
  const id = String(row?.id || "");
  if (!id) return;
  try {
    if (deletingKind.value === "names") await resourcesApi.deletePaymentName(id);
    else if (deletingKind.value === "addresses") await resourcesApi.deletePaymentAddress(id);
    else await resourcesApi.deletePaymentCard(id);
    store.toast("资料已删除", configs[deletingKind.value].label, "success");
    deletingRow.value = null;
    await pageRef.value?.load();
    await loadSummary();
  } catch (err) {
    store.toast("删除失败", String((err as Error).message ?? err), "error");
  }
}

async function importPools() {
  const addresses = splitPaymentImportLines(importAddressesText.value);
  const cards = splitPaymentImportLines(importCardsText.value);
  const names = importNamesText.value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
  if (!names.length && !addresses.length && !cards.length) {
    store.toast("没有可导入资料", "请至少填写一项。", "warning");
    return;
  }
  importing.value = true;
  try {
    const result = await resourcesApi.importPaymentMethodPools({ names, addresses, cards });
    store.toast("批量导入完成", `新增 ${result.inserted_count ?? 0} 条，重复 ${result.existing_count ?? 0} 条`, "success");
    importNamesText.value = "";
    importAddressesText.value = "";
    importCardsText.value = "";
    importOpen.value = false;
    await loadSummary();
    await pageRef.value?.load();
  } catch (err) {
    store.toast("批量导入失败", String((err as Error).message ?? err), "error");
  } finally {
    importing.value = false;
  }
}

async function loadSummary() {
  try {
    summary.value = await resourcesApi.paymentMethodPoolSummary();
  } catch (err) {
    store.toast("库存汇总读取失败", String((err as Error).message ?? err), "error");
  }
}

function selectPool(kind: PoolKind) {
  activePool.value = kind;
}

onMounted(() => { void loadSummary(); });
</script>

<template>
  <div class="pool-page">
    <div class="pool-summary">
      <div><span>有效姓名</span><strong>{{ summary.active_name_count ?? 0 }}</strong></div>
      <div><span>有效地址</span><strong>{{ summary.active_address_count ?? 0 }}</strong></div>
      <div><span>可用卡片</span><strong>{{ summary.available_card_count ?? 0 }}</strong></div>
      <div><span>待绑个人空间</span><strong>{{ summary.pending_personal_space_count ?? 0 }}</strong></div>
    </div>

    <div class="pool-tabs" role="tablist" aria-label="支付资料类型">
      <button
        v-for="(config, kind) in configs"
        :key="kind"
        class="pool-tab"
        :class="{ active: activePool === kind }"
        role="tab"
        :aria-selected="activePool === kind"
        @click="selectPool(kind as PoolKind)"
      >
        <component :is="config.icon" :size="16" />{{ config.label }}
      </button>
    </div>

    <ResourcePage
      :key="activePool"
      ref="pageRef"
      :title="activeConfig.label"
      :description="activeConfig.description"
      :columns="activeConfig.columns"
      :filters="activeConfig.filters"
      :loader="activeConfig.loader"
      :selectable="false"
      empty-text="暂无资料。"
    >
      <template #headerActions>
        <button class="btn" title="批量导入姓名、地址或卡片" @click="importOpen = true"><Upload :size="16" />批量导入</button>
        <button class="btn primary" title="新增一条资料" @click="openCreate()"><Plus :size="16" />新增{{ activeConfig.label }}</button>
      </template>
      <template #rowActions="{ row }">
        <div class="row-actions">
          <button class="icon-btn labeled" title="编辑资料" @click="openEdit(activePool, row)"><Edit3 :size="14" />编辑</button>
          <button class="icon-btn labeled danger" title="删除资料" @click="deletingKind = activePool; deletingRow = row"><Trash2 :size="14" />删除</button>
        </div>
      </template>
    </ResourcePage>
  </div>

  <FormDrawer
    :open="formOpen"
    :title="formTitle"
    :description="editingId && editingKind === 'cards' ? '卡号和 CVC 留空表示保持原值。' : ''"
    :submit-text="editingId ? '保存修改' : '创建资料'"
    :busy="saving"
    width="wide"
    @close="formOpen = false"
    @submit="savePoolItem"
  >
    <template v-if="editingKind === 'names'">
      <label class="field"><span>姓名</span><input v-model="nameValue" class="input" autocomplete="off" required /></label>
      <label class="field"><span>状态</span><select v-model="nameStatus" class="select"><option value="active">有效</option><option value="disabled">禁用</option></select></label>
    </template>
    <template v-else-if="editingKind === 'addresses'">
      <div class="drawer-grid">
        <label class="field wide"><span>地址第一行</span><input v-model="addressLine1" class="input" required /></label>
        <label class="field wide"><span>地址第二行</span><input v-model="addressLine2" class="input" /></label>
        <label class="field"><span>城市</span><input v-model="addressCity" class="input" required /></label>
        <label class="field"><span>州/省</span><input v-model="addressState" class="input" /></label>
        <label class="field"><span>邮编</span><input v-model="addressPostalCode" class="input" required /></label>
        <label class="field"><span>国家代码</span><input v-model="addressCountry" class="input" maxlength="2" placeholder="US" required /></label>
        <label class="field wide"><span>电话</span><input v-model="addressPhone" class="input" /></label>
        <label class="field"><span>状态</span><select v-model="addressStatus" class="select"><option value="active">有效</option><option value="disabled">禁用</option></select></label>
      </div>
    </template>
    <template v-else>
      <div class="drawer-grid">
        <label class="field wide"><span>卡号</span><input v-model="cardNumber" class="input" inputmode="numeric" :placeholder="editingId ? '留空保持原卡号' : '仅输入数字或带空格卡号'" :required="!editingId" autocomplete="off" /></label>
        <label class="field"><span>CVC</span><input v-model="cardCvc" class="input" inputmode="numeric" :placeholder="editingId ? '留空保持原 CVC' : '3 或 4 位'" :required="!editingId" autocomplete="off" /></label>
        <label class="field"><span>有效期月份</span><input v-model="cardExpMonth" class="input" inputmode="numeric" placeholder="12" required /></label>
        <label class="field"><span>有效期年份</span><input v-model="cardExpYear" class="input" inputmode="numeric" placeholder="2030" required /></label>
        <label class="field"><span>状态</span><select v-model="cardStatus" class="select"><option value="available">可用</option><option value="failed">失效</option><option value="disabled">禁用</option><option value="used">已使用</option></select></label>
      </div>
    </template>
  </FormDrawer>

  <FormDrawer :open="importOpen" title="批量导入支付资料" description="只填写需要导入的资料类型，其他类型留空；每行一条，重复项自动跳过。地址和卡片继续兼容旧 JSON 行格式。" submit-text="导入资料" :busy="importing" width="wide" @close="importOpen = false" @submit="importPools">
    <label class="field"><span>姓名列表</span><textarea v-model="importNamesText" class="textarea compact-textarea" placeholder="Ada Lovelace" /></label>
    <label class="field"><span>地址列表</span><textarea v-model="importAddressesText" class="textarea large-textarea" placeholder="310 Jefferson Street, Middletown, Delaware 19709, United States" /></label>
    <label class="field"><span>卡片列表</span><textarea v-model="importCardsText" class="textarea large-textarea" placeholder="Live | CARD_NUMBER|01|2030|CVC | [BIN: ...] | Charge OK." /></label>
  </FormDrawer>

  <ConfirmModal
    :open="Boolean(deletingRow)"
    title="删除支付资料"
    message="删除后该资料不会再参与后续绑卡；已使用记录不受影响。"
    :summary="{ 类型: configs[deletingKind].label, ID: deletingRow?.id }"
    confirm-text="确认删除"
    danger
    @close="deletingRow = null"
    @confirm="deletePoolItem"
  />
</template>

<style scoped>
.pool-page { display: grid; gap: 12px; }
.pool-summary { display: grid; gap: 10px; grid-template-columns: repeat(4, minmax(0, 1fr)); }
.pool-summary > div { background: var(--panel-bg); border: 1px solid var(--border); border-radius: var(--radius-md); display: grid; gap: 5px; padding: 12px 14px; }
.pool-summary span { color: var(--text-muted); font-size: 11px; font-weight: 700; }
.pool-summary strong { font-size: 21px; line-height: 1; }
.pool-tabs { display: flex; flex-wrap: wrap; gap: 6px; }
.pool-tab { align-items: center; background: var(--panel-bg-2); border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text-muted); cursor: pointer; display: inline-flex; font-size: 12px; font-weight: 750; gap: 7px; min-height: 36px; padding: 0 13px; }
.pool-tab:hover { border-color: var(--border-strong); color: var(--text-primary); }
.pool-tab.active { background: var(--accent-soft); border-color: var(--accent); color: var(--text-primary); }
.row-actions { display: flex; gap: 6px; }
.danger { color: var(--danger-text); }
.drawer-grid { display: grid; gap: 12px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.wide { grid-column: 1 / -1; }

@media (max-width: 760px) {
  .pool-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .drawer-grid { grid-template-columns: 1fr; }
  .wide { grid-column: auto; }
}
</style>
