<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import ResourcePage from "../components/ResourcePage.vue";
import type { Column, TableFilter } from "../components/DataTable.vue";
import type { Row } from "../api/resources";
import { resourcesApi } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const router = useRouter();
const store = useOpsStore();
const selectedRows = ref<Row[]>([]);
const selectedCount = ref(0);
const pushWorkCount = ref(5);
const downstreamChannelId = ref("");
const downstreamChannels = ref<Row[]>([]);

const filters: TableFilter[] = [{ key: "credential_status", label: "凭证状态", options: [
  { label: "有效", value: "active" }, { label: "无效", value: "invalid" },
  { label: "过期", value: "expired" }, { label: "错误", value: "error" },
] }];

const columns: Column[] = [
  { key: "id", label: "空间凭证 ID", mono: true, summary: 24, copyable: true },
  { key: "email", label: "账号邮箱", summary: 30, copyable: true },
  { key: "user_account_id", label: "账号 ID", mono: true, summary: 28 },
  { key: "space_id", label: "空间 ID", mono: true, summary: 28 },
  { key: "external_space_id", label: "外部空间 ID", mono: true, summary: 28 },
  { key: "space_type", label: "空间类型", badge: true },
  { key: "credential_type", label: "凭证类型", badge: true },
  { key: "credential_status", label: "凭证状态", badge: true },
  { key: "external_credential_id", label: "外部凭证 ID", mono: true, summary: 28 },
  { key: "account_id", label: "Account ID", mono: true, summary: 28 },
  { key: "token_chatgpt_account_id", label: "Token Account ID", mono: true, summary: 28 },
  { key: "has_access_token", label: "Access Token", badge: true },
  { key: "has_refresh_token", label: "Refresh Token", badge: true },
  { key: "expires_at", label: "过期时间", type: "datetime", relativeTime: true, sortable: true },
  { key: "last_probe_status", label: "探测状态", badge: true },
  { key: "last_authorized_at", label: "最近授权时间", type: "datetime", relativeTime: true },
  { key: "updated_at", label: "更新时间", type: "datetime", relativeTime: true, sortable: true },
];

function updateSelection(rows: Record<string, unknown>[]) {
  selectedRows.value = rows as Row[];
  selectedCount.value = rows.length;
}

onMounted(async () => {
  try {
    downstreamChannels.value = (await resourcesApi.downstreamChannels({ page_size: 100, sort: "name" })).items;
    const firstEnabled = downstreamChannels.value.find((row) => Boolean(row.enabled));
    downstreamChannelId.value = String(firstEnabled?.id || downstreamChannels.value[0]?.id || "");
  } catch {
    downstreamChannels.value = [];
  }
});

async function pushSelected() {
  const ids = selectedRows.value.map((row) => String(row.id || "")).filter(Boolean);
  if (!ids.length) {
    store.toast("未选择凭证", "请先勾选要推送的空间凭证。", "warning");
    return;
  }
  if (!downstreamChannelId.value) {
    store.toast("未选择渠道", "请先选择下游渠道。", "warning");
    return;
  }
  const result = await resourcesApi.pushCredentials({
    space_credential_ids: ids,
    downstream_channel_id: downstreamChannelId.value,
    created_by: "ops-ui",
    work_count: pushWorkCount.value,
  });
  store.toast(
    "下游推送完成",
    `work=${result.work_count} 成功=${result.succeeded} 失败=${result.failed}`,
    result.failed > 0 ? "warning" : "success",
  );
  await router.push(`/jobs/${result.job_id}`);
}
</script>

<template>
  <ResourcePage
    title="空间凭证"
    description="每个账号在某个 Space 下的当前凭证；payload 和余额按 spaces.credential_type 分支。"
    :columns="columns"
    :loader="resourcesApi.credentials"
    :filters="filters"
    empty-text="暂无空间凭证。"
    selectable
    @selection-change="updateSelection"
  >
    <template #actions>
      <div class="push-action-body">
          <label class="field">
            <span>下游渠道</span>
            <select v-model="downstreamChannelId" class="input">
              <option value="">请选择</option>
              <option v-for="channel in downstreamChannels" :key="String(channel.id)" :value="String(channel.id)">
                {{ channel.provider_type }} / {{ channel.name }}
              </option>
            </select>
          </label>
          <label class="field">
            <span>Work 数</span>
            <input v-model.number="pushWorkCount" class="input small-input" type="number" min="1" max="500" />
          </label>
        <button class="btn primary" :disabled="selectedCount === 0 || !downstreamChannelId" @click="pushSelected">推送选中凭证（{{ selectedCount }}）</button>
      </div>
    </template>
  </ResourcePage>
</template>

<style scoped>
.push-action-body {
  align-items: end;
  display: grid;
  grid-template-columns: minmax(220px, 1fr) 100px auto;
  width: 100%;
}

@media (max-width: 767px) {
  .push-action-body {
    grid-template-columns: 1fr;
  }
}
</style>
