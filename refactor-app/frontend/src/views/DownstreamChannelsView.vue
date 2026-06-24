<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";

import type { Column } from "../components/DataTable.vue";
import ResourcePage from "../components/ResourcePage.vue";
import { resourcesApi, type Row } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();
const router = useRouter();
const pendingPushLimit = ref(1);
const pendingPushConcurrency = ref(5);
const balanceAmounts = ref<Record<string, number>>({});
const editingChannel = ref<Row | null>(null);
const editSaving = ref(false);
const form = ref({
  provider_type: "sub2api",
  name: "",
  base_url: "",
  admin_key: "",
  custom_payload_type: "sub2api",
  custom_auth_header_name: "",
  custom_auth_header_value: "",
  enabled: true,
  update_existing: true,
  timeout_s: 30,
  max_active_slots: 1,
  push_balance: 0,
});
const editForm = ref({
  provider_type: "sub2api",
  name: "",
  base_url: "",
  admin_key: "",
  custom_payload_type: "sub2api",
  custom_auth_header_name: "",
  custom_auth_header_value: "",
  enabled: true,
  update_existing: true,
  timeout_s: 30,
  max_active_slots: 1,
});
const isLocalSub2api = computed(() => form.value.provider_type === "local_sub2api");
const isCustomHttp = computed(() => form.value.provider_type === "custom_http");
const addressLabel = computed(() => {
  if (isLocalSub2api.value) return "输出目录";
  if (isCustomHttp.value) return "完整接口地址";
  return "地址";
});
const addressPlaceholder = computed(() =>
  isLocalSub2api.value
    ? "留空使用 runtime/local-sub2api"
    : isCustomHttp.value
      ? "https://example.com/push"
    : "https://...",
);
const secretLabel = computed(() => (isLocalSub2api.value || isCustomHttp.value ? "密钥（不需要）" : "密钥"));
const secretPlaceholder = computed(() =>
  isLocalSub2api.value || isCustomHttp.value ? "该类型不使用 admin_key" : "admin key",
);
const isEditingLocalSub2api = computed(() => editForm.value.provider_type === "local_sub2api");
const isEditingCustomHttp = computed(() => editForm.value.provider_type === "custom_http");
const editAddressLabel = computed(() => {
  if (isEditingLocalSub2api.value) return "输出目录";
  if (isEditingCustomHttp.value) return "完整接口地址";
  return "地址";
});
const editAddressPlaceholder = computed(() =>
  isEditingLocalSub2api.value
    ? "留空使用 runtime/local-sub2api"
    : isEditingCustomHttp.value
      ? "https://example.com/push"
    : "https://...",
);
const editSecretPlaceholder = computed(() =>
  isEditingLocalSub2api.value || isEditingCustomHttp.value
    ? "该类型不使用 admin_key"
    : "留空则不修改原密钥",
);

watch(
  () => form.value.provider_type,
  (providerType) => {
    if (providerType === "local_sub2api" || providerType === "custom_http") {
      form.value.admin_key = "";
    }
    if (providerType !== "custom_http") {
      form.value.custom_auth_header_name = "";
      form.value.custom_auth_header_value = "";
    }
  },
);

watch(
  () => editForm.value.provider_type,
  (providerType) => {
    if (providerType === "local_sub2api" || providerType === "custom_http") {
      editForm.value.admin_key = "";
    }
    if (providerType !== "custom_http") {
      editForm.value.custom_auth_header_name = "";
      editForm.value.custom_auth_header_value = "";
    }
  },
);

const columns: Column[] = [
  { key: "id", label: "渠道 ID", mono: true, summary: 26 },
  { key: "provider_type", label: "类型", badge: true },
  { key: "custom_payload_type", label: "自定义格式", badge: true },
  { key: "name", label: "名称" },
  { key: "base_url", label: "地址", mono: true, summary: 38 },
  { key: "custom_auth_header_name", label: "认证头" },
  { key: "enabled", label: "启用", badge: true },
  { key: "update_existing", label: "更新已有", badge: true },
  { key: "timeout_s", label: "超时" },
  { key: "max_active_slots", label: "同时占用上限" },
  { key: "allowed_active_slots", label: "当前开放坑位" },
  { key: "active_slot_count", label: "当前占用" },
  { key: "remaining_active_slots", label: "剩余坑位" },
  { key: "push_balance", label: "推送余额" },
  { key: "remaining_push_count", label: "本轮可推" },
  { key: "claimed_push_count", label: "已消耗余额" },
  { key: "pushed_count", label: "成功" },
  { key: "failed_push_count", label: "失败" },
  { key: "used_count", label: "已使用" },
  { key: "updated_at", label: "更新时间", mono: true, summary: 28 },
];

async function loader() {
  return resourcesApi.downstreamChannels();
}

async function createChannel(reload: () => Promise<void>) {
  const local = form.value.provider_type === "local_sub2api";
  const custom = form.value.provider_type === "custom_http";
  if (
    !form.value.name.trim()
    || (!local && !form.value.base_url.trim())
    || (!local && !custom && !form.value.admin_key.trim())
    || (custom && !["sub2api", "cpa"].includes(form.value.custom_payload_type))
    || (custom && Boolean(form.value.custom_auth_header_name.trim()) !== Boolean(form.value.custom_auth_header_value.trim()))
  ) {
    store.toast(
      "参数不完整",
      custom
        ? "自定义接口需要名称、完整地址、推送 JSON 类型；认证头名称和值必须同时填写或同时留空。"
        : local
          ? "本地推送只需要填写名称。"
          : "名称、地址、密钥都需要填写。",
      "warning",
    );
    return;
  }
  try {
    await resourcesApi.createDownstreamChannel({ ...form.value });
    store.toast("渠道已创建", form.value.name, "success");
    form.value.name = "";
    form.value.base_url = "";
    form.value.admin_key = "";
    form.value.custom_auth_header_name = "";
    form.value.custom_auth_header_value = "";
    await reload();
  } catch (err) {
    store.toast("创建失败", String((err as Error).message ?? err), "error");
  }
}

async function toggleEnabled(row: Row, reload: () => Promise<void>) {
  const id = String(row.id || "");
  if (!id) return;
  try {
    await resourcesApi.patchDownstreamChannel(id, { enabled: !Boolean(row.enabled) });
    store.toast("渠道已更新", id, "success");
    await reload();
  } catch (err) {
    store.toast("更新失败", String((err as Error).message ?? err), "error");
  }
}

function openEditChannel(row: Row) {
  editingChannel.value = row;
  editForm.value = {
    provider_type: String(row.provider_type || "sub2api"),
    name: String(row.name || ""),
    base_url: String(row.base_url || ""),
    admin_key: "",
    custom_payload_type: String(row.custom_payload_type || "sub2api"),
    custom_auth_header_name: String(row.custom_auth_header_name || ""),
    custom_auth_header_value: "",
    enabled: Boolean(row.enabled),
    update_existing: Boolean(row.update_existing),
    timeout_s: Number(row.timeout_s || 30),
    max_active_slots: Number(row.max_active_slots || 0),
  };
}

function closeEditChannel() {
  if (editSaving.value) return;
  editingChannel.value = null;
  editForm.value.admin_key = "";
}

async function saveEditChannel(reload: () => Promise<void>) {
  const row = editingChannel.value;
  if (!row) return;
  const id = String(row.id || "");
  if (!id) return;
  const nextProvider = editForm.value.provider_type.trim();
  const wasLocal = String(row.provider_type || "") === "local_sub2api";
  const wasCustom = String(row.provider_type || "") === "custom_http";
  const nextLocal = nextProvider === "local_sub2api";
  const nextCustom = nextProvider === "custom_http";
  const name = editForm.value.name.trim();
  const baseUrl = editForm.value.base_url.trim();
  const adminKey = editForm.value.admin_key.trim();
  const authHeaderName = editForm.value.custom_auth_header_name.trim();
  const authHeaderValue = editForm.value.custom_auth_header_value.trim();
  const hasExistingCustomAuthValue = Boolean(String(row.custom_auth_header_value_summary || "").trim());
  if (!name) {
    store.toast("参数不完整", "渠道名称不能为空。", "warning");
    return;
  }
  if (!nextLocal && !baseUrl) {
    store.toast("参数不完整", "非本地渠道必须填写地址。", "warning");
    return;
  }
  if ((wasLocal || wasCustom) && !nextLocal && !nextCustom && !adminKey) {
    store.toast("参数不完整", "本地渠道改为远端渠道时必须填写密钥。", "warning");
    return;
  }
  if (nextCustom && !["sub2api", "cpa"].includes(editForm.value.custom_payload_type)) {
    store.toast("参数不完整", "自定义接口必须选择 sub2api 或 CPA JSON。", "warning");
    return;
  }
  if (nextCustom && !authHeaderName && authHeaderValue) {
    store.toast("参数不完整", "填写认证头值时必须填写认证头名称。", "warning");
    return;
  }
  if (nextCustom && authHeaderName && !authHeaderValue && !hasExistingCustomAuthValue) {
    store.toast("参数不完整", "新增认证头时必须填写认证头值。", "warning");
    return;
  }

  const body: Record<string, unknown> = {
    provider_type: nextProvider,
    name,
    base_url: baseUrl,
    custom_payload_type: nextCustom ? editForm.value.custom_payload_type : "",
    custom_auth_header_name: nextCustom ? authHeaderName : "",
    enabled: editForm.value.enabled,
    update_existing: editForm.value.update_existing,
    timeout_s: Number(editForm.value.timeout_s || 30),
    max_active_slots: Number(editForm.value.max_active_slots || 0),
  };
  if (nextLocal || nextCustom) {
    body.admin_key = "";
  } else if (adminKey) {
    body.admin_key = adminKey;
  }
  if (nextCustom && authHeaderValue) {
    body.custom_auth_header_value = authHeaderValue;
  } else if (nextCustom && !authHeaderName) {
    body.custom_auth_header_value = "";
  }

  editSaving.value = true;
  try {
    const result = await resourcesApi.patchDownstreamChannel(id, body);
    store.toast("渠道已保存", `${String(result.provider_type || nextProvider)} / ${String(result.name || name)}`, "success");
    editingChannel.value = null;
    editForm.value.admin_key = "";
    editForm.value.custom_auth_header_value = "";
    await reload();
  } catch (err) {
    store.toast("保存失败", String((err as Error).message ?? err), "error");
  } finally {
    editSaving.value = false;
  }
}

async function addBalance(row: Row, reload: () => Promise<void>) {
  const id = String(row.id || "");
  if (!id) return;
  const amount = Number(balanceAmounts.value[id] || 0);
  if (!Number.isFinite(amount) || amount <= 0) {
    store.toast("参数错误", "添加余额必须大于 0。", "warning");
    return;
  }
  try {
    const result = await resourcesApi.addDownstreamChannelBalance(id, { amount });
    store.toast(
      "余额已添加",
      `${String(row.name || id)} 当前余额=${String(result.push_balance ?? "")}`,
      "success",
    );
    balanceAmounts.value[id] = 0;
    await reload();
  } catch (err) {
    store.toast("添加余额失败", String((err as Error).message ?? err), "error");
  }
}

async function pushPending(row: Row) {
  const id = String(row.id || "");
  if (!id) return;
  try {
    const result = await resourcesApi.pushPendingCredentials({
      downstream_channel_id: id,
      limit: pendingPushLimit.value,
      concurrency: pendingPushConcurrency.value,
      created_by: "ops-ui-channel",
    });
    store.toast(
      "待推送凭证已推送",
      `work=${result.work_count} 成功=${result.succeeded} 失败=${result.failed}`,
      result.failed > 0 ? "warning" : "success",
    );
    await router.push({ name: "job-trace", params: { jobId: result.job_id } });
  } catch (err) {
    store.toast("推送失败", String((err as Error).message ?? err), "error");
  }
}

async function deleteChannel(row: Row, reload: () => Promise<void>) {
  const id = String(row.id || "");
  if (!id) return;
  const name = String(row.name || id);
  if (!window.confirm(`确认删除下游渠道：${name}？`)) return;
  try {
    const result = await resourcesApi.deleteDownstreamChannel(id);
    store.toast(
      "渠道已删除",
      `已解绑推送记录 ${String(result.detached_push_records_count ?? 0)} 条`,
      "success",
    );
    await reload();
  } catch (err) {
    store.toast("删除失败", String((err as Error).message ?? err), "error");
  }
}

</script>

<template>
  <ResourcePage
    title="下游渠道"
    description="维护 sub2api / CPA / 本地 sub2api 文件 / 自定义接口推送渠道配置。"
    :columns="columns"
    :loader="loader"
    empty-text="暂无下游渠道。"
  >
    <template #actionCards="{ reload }">
      <div class="action-card">
        <div>
          <h2>新增渠道</h2>
          <p>先选渠道类型，再按类型填写远端密钥或自定义接口参数。</p>
        </div>
        <div class="channel-create-layout">
          <section class="mini-section">
            <h3>基础信息</h3>
            <div class="form-grid">
              <label>
                <span>类型</span>
                <select v-model="form.provider_type">
                  <option value="sub2api">sub2api</option>
                  <option value="cpa">CPA</option>
                  <option value="local_sub2api">本地 sub2api 文件</option>
                  <option value="custom_http">自定义接口</option>
                </select>
              </label>
              <label>
                <span>名称</span>
                <input v-model="form.name" placeholder="渠道名称" />
              </label>
              <label class="wide-field">
                <span>{{ addressLabel }}</span>
                <input v-model="form.base_url" :placeholder="addressPlaceholder" />
              </label>
            </div>
          </section>

          <section v-if="!isCustomHttp" class="mini-section">
            <h3>平台认证</h3>
            <div class="form-grid">
              <label>
                <span>{{ secretLabel }}</span>
                <input
                  v-model="form.admin_key"
                  :disabled="isLocalSub2api"
                  :placeholder="secretPlaceholder"
                />
              </label>
              <label class="check">
                <input v-model="form.update_existing" type="checkbox" />
                <span>更新已有</span>
              </label>
            </div>
          </section>

          <section v-if="isCustomHttp" class="mini-section accent-section">
            <h3>自定义接口</h3>
            <p>sub2api 格式推送 raw 授权 JSON，也就是原 content 里的内容；CPA 格式推送 CPA auth file JSON。</p>
            <div class="form-grid">
              <label>
                <span>推送 JSON 类型</span>
                <select v-model="form.custom_payload_type">
                  <option value="sub2api">sub2api 授权 JSON</option>
                  <option value="cpa">CPA 授权 JSON</option>
                </select>
              </label>
              <label>
                <span>认证头名称</span>
                <input v-model="form.custom_auth_header_name" placeholder="Authorization / x-api-key" />
              </label>
              <label class="wide-field">
                <span>认证头值</span>
                <input v-model="form.custom_auth_header_value" placeholder="Bearer xxx / sk-xxx" />
              </label>
            </div>
          </section>

          <section class="mini-section">
            <h3>推送规则</h3>
            <div class="form-grid">
              <label>
                <span>超时秒</span>
                <input v-model.number="form.timeout_s" type="number" min="1" />
              </label>
              <label>
                <span>同时占用上限</span>
                <input v-model.number="form.max_active_slots" type="number" min="0" />
              </label>
              <label>
                <span>推送余额</span>
                <input v-model.number="form.push_balance" type="number" min="0" />
              </label>
              <label class="check">
                <input v-model="form.enabled" type="checkbox" />
                <span>启用</span>
              </label>
              <button class="btn primary create-submit" @click="createChannel(reload)">新增渠道</button>
            </div>
          </section>
        </div>
      </div>
      <div class="action-card">
        <div>
          <h2>待推送处理</h2>
          <p>推送需要同时满足：还有推送余额、当前占用小于同时占用上限。开始推送即消耗余额。</p>
        </div>
        <div class="form-grid">
          <label>
            <span>默认推送数量</span>
            <input v-model.number="pendingPushLimit" type="number" min="1" />
          </label>
          <label>
            <span>默认并发</span>
            <input v-model.number="pendingPushConcurrency" type="number" min="1" max="500" />
          </label>
        </div>
      </div>
    </template>
    <template #rowActions="{ row, reload }">
      <button class="btn compact-action" @click="openEditChannel(row)">
        编辑
      </button>
      <div class="inline-balance">
        <input
          v-model.number="balanceAmounts[String(row.id || '')]"
          class="compact-number"
          type="number"
          min="1"
          placeholder="余额"
        />
        <button class="btn compact-action" @click="addBalance(row, reload)">
          加余额
        </button>
      </div>
      <button class="btn compact-action" @click="toggleEnabled(row, reload)">
        {{ row.enabled ? "禁用" : "启用" }}
      </button>
      <button class="btn compact-action primary" @click="pushPending(row)">
        推送待推送
      </button>
      <button class="btn compact-action danger" @click="deleteChannel(row, reload)">
        删除
      </button>
    </template>
    <template #before="{ reload }">
      <Teleport to="body">
        <div v-if="editingChannel" class="edit-overlay" @click.self="closeEditChannel">
          <section class="edit-modal panel">
            <header class="edit-header">
              <div>
                <h2>编辑渠道</h2>
                <p>{{ editingChannel.provider_type }} / {{ editingChannel.name }}</p>
              </div>
              <button class="btn compact-action" :disabled="editSaving" @click="closeEditChannel">关闭</button>
            </header>

            <div class="edit-content">
              <section class="edit-section">
                <div class="section-title">
                  <h3>基础信息</h3>
                  <p>修改渠道类型、名称、地址和密钥。密钥留空表示不修改原密钥。</p>
                </div>
                <div class="edit-grid">
                  <label>
                    <span>类型</span>
                    <select v-model="editForm.provider_type" class="input">
                      <option value="sub2api">sub2api</option>
                      <option value="cpa">CPA</option>
                      <option value="local_sub2api">本地 sub2api 文件</option>
                      <option value="custom_http">自定义接口</option>
                    </select>
                  </label>
                  <label>
                    <span>名称</span>
                    <input v-model="editForm.name" class="input" placeholder="渠道名称" />
                  </label>
                  <label class="wide-field">
                    <span>{{ editAddressLabel }}</span>
                    <input v-model="editForm.base_url" class="input" :placeholder="editAddressPlaceholder" />
                  </label>
                  <label class="wide-field">
                    <span>密钥</span>
                    <input
                      v-model="editForm.admin_key"
                      class="input"
                      :disabled="isEditingLocalSub2api || isEditingCustomHttp"
                      :placeholder="editSecretPlaceholder"
                    />
                  </label>
                </div>
              </section>

              <section v-if="isEditingCustomHttp" class="edit-section accent-section">
                <div class="section-title">
                  <h3>自定义接口</h3>
                  <p>sub2api 推 raw 授权 JSON；CPA 推 CPA auth file JSON。认证头名称和值同时留空表示不加认证头。</p>
                </div>
                <div class="edit-grid">
                  <label>
                    <span>推送 JSON 类型</span>
                    <select v-model="editForm.custom_payload_type" class="input">
                      <option value="sub2api">sub2api 授权 JSON</option>
                      <option value="cpa">CPA 授权 JSON</option>
                    </select>
                  </label>
                  <label>
                    <span>认证头名称</span>
                    <input
                      v-model="editForm.custom_auth_header_name"
                      class="input"
                      placeholder="Authorization / x-api-key"
                    />
                  </label>
                  <label class="wide-field">
                    <span>认证头值</span>
                    <input
                      v-model="editForm.custom_auth_header_value"
                      class="input"
                      placeholder="留空则不修改原认证头值"
                    />
                  </label>
                </div>
              </section>

              <section class="edit-section">
                <div class="section-title">
                  <h3>推送规则</h3>
                  <p>编辑运行规则，不在这里覆盖余额。</p>
                </div>
                <div class="edit-grid compact-grid">
                  <label>
                    <span>超时秒</span>
                    <input v-model.number="editForm.timeout_s" class="input" type="number" min="1" />
                  </label>
                  <label>
                    <span>同时占用上限</span>
                    <input v-model.number="editForm.max_active_slots" class="input" type="number" min="0" />
                  </label>
                  <label class="check edit-check">
                    <input v-model="editForm.enabled" type="checkbox" />
                    <span>启用</span>
                  </label>
                  <label class="check edit-check">
                    <input v-model="editForm.update_existing" type="checkbox" />
                    <span>更新已有</span>
                  </label>
                </div>
              </section>

              <section class="edit-section readonly-section">
                <div class="section-title">
                  <h3>余额与占用</h3>
                  <p>余额用“加余额”动作增量处理，避免误覆盖。</p>
                </div>
                <div class="metric-grid">
                  <div>
                    <span>当前余额</span>
                    <strong>{{ editingChannel.push_balance }}</strong>
                  </div>
                  <div>
                    <span>已消耗余额</span>
                    <strong>{{ editingChannel.claimed_push_count }}</strong>
                  </div>
                  <div>
                    <span>当前占用</span>
                    <strong>{{ editingChannel.active_slot_count }}</strong>
                  </div>
                  <div>
                    <span>剩余坑位</span>
                    <strong>{{ editingChannel.remaining_active_slots }}</strong>
                  </div>
                </div>
              </section>
            </div>

            <footer class="edit-footer">
              <button class="btn" :disabled="editSaving" @click="closeEditChannel">取消</button>
              <button class="btn primary" :disabled="editSaving" @click="saveEditChannel(reload)">
                {{ editSaving ? "保存中..." : "保存修改" }}
              </button>
            </footer>
          </section>
        </div>
      </Teleport>
    </template>
  </ResourcePage>
</template>

<style scoped>
.action-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  display: grid;
  gap: 16px;
  padding: 16px;
}

.action-card h2 {
  font-size: 16px;
  margin: 0 0 6px;
}

.action-card p {
  color: var(--text-muted);
  margin: 0;
}

.form-grid {
  align-items: end;
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}

.channel-create-layout {
  display: grid;
  gap: 14px;
}

.mini-section {
  background: rgba(8, 13, 25, 0.36);
  border: 1px solid rgba(38, 50, 73, 0.68);
  border-radius: 14px;
  display: grid;
  gap: 12px;
  padding: 14px;
}

.mini-section h3 {
  font-size: 14px;
  margin: 0;
}

.mini-section p {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.45;
  margin: 0;
}

.accent-section {
  background:
    linear-gradient(135deg, rgba(59, 130, 246, 0.12), rgba(16, 185, 129, 0.06)),
    rgba(8, 13, 25, 0.44);
  border-color: rgba(96, 165, 250, 0.42);
}

.create-submit {
  align-self: end;
}

label {
  display: grid;
  gap: 7px;
}

label span {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 800;
}

.check {
  align-items: center;
  display: flex;
  gap: 8px;
  min-height: 44px;
}

.compact-action {
  min-height: 30px;
  padding: 0 10px;
}

.inline-balance {
  align-items: center;
  display: inline-flex;
  gap: 6px;
}

.compact-number {
  min-height: 30px;
  padding: 0 8px;
  width: 82px;
}

.edit-overlay {
  align-items: center;
  background: rgba(2, 6, 23, 0.72);
  display: flex;
  inset: 0;
  justify-content: center;
  padding: 22px;
  position: fixed;
  z-index: 60;
}

.edit-modal {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  height: min(88vh, 760px);
  height: min(88dvh, 760px);
  max-height: min(88vh, 760px);
  max-width: 860px;
  overflow: hidden;
  width: min(100%, 860px);
}

.edit-header,
.edit-footer {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
  padding: 16px 18px;
}

.edit-header {
  border-bottom: 1px solid var(--border);
}

.edit-header h2 {
  font-size: 18px;
  margin: 0;
}

.edit-header p {
  color: var(--text-muted);
  font-size: 12px;
  margin: 5px 0 0;
}

.edit-content {
  display: grid;
  gap: 14px;
  min-height: 0;
  overflow: auto;
  padding: 16px 18px;
}

.edit-section {
  background: rgba(8, 13, 25, 0.42);
  border: 1px solid rgba(38, 50, 73, 0.72);
  border-radius: 14px;
  display: grid;
  gap: 14px;
  padding: 14px;
}

.section-title h3 {
  font-size: 14px;
  margin: 0;
}

.section-title p {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.45;
  margin: 5px 0 0;
}

.edit-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.compact-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.wide-field {
  grid-column: span 2;
}

.edit-check {
  align-self: end;
  background: rgba(13, 20, 38, 0.66);
  border: 1px solid var(--border);
  border-radius: 10px;
  min-height: 38px;
  padding: 0 11px;
}

.metric-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.metric-grid div {
  background: rgba(13, 20, 38, 0.66);
  border: 1px solid var(--border);
  border-radius: 12px;
  display: grid;
  gap: 5px;
  padding: 11px;
}

.metric-grid span {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 800;
}

.metric-grid strong {
  font-size: 18px;
}

.edit-footer {
  background: rgba(17, 24, 39, 0.98);
  border-top: 1px solid var(--border);
  justify-content: flex-end;
}

@media (max-width: 767px) {
  .edit-overlay {
    align-items: stretch;
    padding: 12px;
  }

  .edit-modal {
    height: calc(100vh - 24px);
    height: calc(100dvh - 24px);
    max-height: none;
  }

  .edit-header,
  .edit-footer {
    align-items: stretch;
    flex-direction: column;
  }

  .edit-grid,
  .compact-grid,
  .metric-grid {
    grid-template-columns: 1fr;
  }

  .wide-field {
    grid-column: auto;
  }
}
</style>
