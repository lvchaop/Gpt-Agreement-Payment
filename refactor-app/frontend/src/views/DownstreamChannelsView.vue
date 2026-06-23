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
const form = ref({
  provider_type: "sub2api",
  name: "",
  base_url: "",
  admin_key: "",
  enabled: true,
  update_existing: true,
  timeout_s: 30,
  max_active_slots: 1,
  push_balance: 0,
});
const isLocalSub2api = computed(() => form.value.provider_type === "local_sub2api");
const addressLabel = computed(() => (isLocalSub2api.value ? "输出目录" : "地址"));
const addressPlaceholder = computed(() =>
  isLocalSub2api.value
    ? "留空使用 runtime/local-sub2api"
    : "https://...",
);
const secretLabel = computed(() => (isLocalSub2api.value ? "密钥（不需要）" : "密钥"));
const secretPlaceholder = computed(() => (isLocalSub2api.value ? "本地推送无需填写" : "admin key"));

watch(
  () => form.value.provider_type,
  (providerType) => {
    if (providerType === "local_sub2api") {
      form.value.admin_key = "";
    }
  },
);

const columns: Column[] = [
  { key: "id", label: "渠道 ID", mono: true, summary: 26 },
  { key: "provider_type", label: "类型", badge: true },
  { key: "name", label: "名称" },
  { key: "base_url", label: "地址", mono: true, summary: 38 },
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
  if (!form.value.name.trim() || (!local && (!form.value.base_url.trim() || !form.value.admin_key.trim()))) {
    store.toast(
      "参数不完整",
      local ? "本地推送只需要填写名称。" : "名称、地址、密钥都需要填写。",
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
    description="维护 sub2api / CPA / 本地 sub2api 文件推送渠道配置。"
    :columns="columns"
    :loader="loader"
    empty-text="暂无下游渠道。"
  >
    <template #actionCards="{ reload }">
      <div class="action-card">
        <div>
          <h2>新增渠道</h2>
          <p>功能按钮和可选参数放在独立区域，不和表格筛选混在一起。</p>
        </div>
        <div class="form-grid">
          <label>
            <span>类型</span>
            <select v-model="form.provider_type">
              <option value="sub2api">sub2api</option>
              <option value="cpa">CPA</option>
              <option value="local_sub2api">本地 sub2api 文件</option>
            </select>
          </label>
          <label>
            <span>名称</span>
            <input v-model="form.name" placeholder="渠道名称" />
          </label>
          <label>
            <span>{{ addressLabel }}</span>
            <input v-model="form.base_url" :placeholder="addressPlaceholder" />
          </label>
          <label>
            <span>{{ secretLabel }}</span>
            <input v-model="form.admin_key" :disabled="isLocalSub2api" :placeholder="secretPlaceholder" />
          </label>
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
          <label class="check">
            <input v-model="form.update_existing" type="checkbox" />
            <span>更新已有</span>
          </label>
          <button class="btn primary" @click="createChannel(reload)">新增渠道</button>
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
</style>
