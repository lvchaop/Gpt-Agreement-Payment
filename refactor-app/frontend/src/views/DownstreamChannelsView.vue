<script setup lang="ts">
import { ref } from "vue";

import type { Column } from "../components/DataTable.vue";
import ResourcePage from "../components/ResourcePage.vue";
import { resourcesApi, type Row } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();
const form = ref({
  provider_type: "sub2api",
  name: "",
  base_url: "",
  admin_key: "",
  enabled: true,
  update_existing: true,
  timeout_s: 30,
});

const columns: Column[] = [
  { key: "id", label: "渠道 ID", mono: true, summary: 26 },
  { key: "provider_type", label: "类型", badge: true },
  { key: "name", label: "名称" },
  { key: "base_url", label: "地址", mono: true, summary: 38 },
  { key: "enabled", label: "启用", badge: true },
  { key: "update_existing", label: "更新已有", badge: true },
  { key: "timeout_s", label: "超时" },
  { key: "updated_at", label: "更新时间", mono: true, summary: 28 },
];

async function loader() {
  return resourcesApi.downstreamChannels();
}

async function createChannel(reload: () => Promise<void>) {
  if (!form.value.name.trim() || !form.value.base_url.trim() || !form.value.admin_key.trim()) {
    store.toast("参数不完整", "名称、地址、密钥都需要填写。", "warning");
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

</script>

<template>
  <ResourcePage
    title="下游渠道"
    description="维护 sub2api / CPA 推送渠道配置。"
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
            </select>
          </label>
          <label>
            <span>名称</span>
            <input v-model="form.name" placeholder="渠道名称" />
          </label>
          <label>
            <span>地址</span>
            <input v-model="form.base_url" placeholder="https://..." />
          </label>
          <label>
            <span>密钥</span>
            <input v-model="form.admin_key" placeholder="admin key" />
          </label>
          <label>
            <span>超时秒</span>
            <input v-model.number="form.timeout_s" type="number" min="1" />
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
    </template>
    <template #rowActions="{ row, reload }">
      <button class="btn compact-action" @click="toggleEnabled(row, reload)">
        {{ row.enabled ? "禁用" : "启用" }}
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
</style>
