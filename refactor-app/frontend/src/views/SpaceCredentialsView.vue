<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import ResourcePage from "../components/ResourcePage.vue";
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

const columns = [
  { key: "id", label: "空间凭证 ID", mono: true, summary: 28 },
  { key: "email", label: "账号邮箱", summary: 30 },
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
  { key: "expires_at", label: "过期时间", summary: 30 },
  { key: "last_probe_status", label: "探测状态", badge: true },
  { key: "last_authorized_at", label: "最近授权时间", summary: 30 },
  { key: "updated_at", label: "更新时间", summary: 30 },
];

function updateSelection(rows: Record<string, unknown>[]) {
  selectedRows.value = rows as Row[];
  selectedCount.value = rows.length;
}

onMounted(async () => {
  try {
    downstreamChannels.value = await resourcesApi.downstreamChannels();
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
    empty-text="暂无空间凭证。"
    selectable
    @selection-change="updateSelection"
  >
    <template #actionCards>
      <section class="panel credential-action-card">
        <div class="credential-action-heading">
          <div>
            <h2>下游推送</h2>
            <p>按下游渠道的 credential_type 余额和坑位推送选中的 Space 凭证。</p>
          </div>
          <span class="selected-hint">已选 {{ selectedCount }} 条凭证</span>
        </div>
        <div class="credential-action-body push-action-body">
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
            <span>同时 Work 数</span>
            <input v-model.number="pushWorkCount" class="input small-input" type="number" min="1" max="500" />
          </label>
          <button class="btn primary" :disabled="selectedCount === 0 || !downstreamChannelId" @click="pushSelected">
            推送选中凭证（{{ selectedCount }}）
          </button>
        </div>
      </section>
    </template>
  </ResourcePage>
</template>

<style scoped>
.credential-action-card {
  margin-bottom: 14px;
  overflow: hidden;
  padding: 0;
}

.credential-action-heading {
  align-items: center;
  border-bottom: 1px solid var(--border);
  display: flex;
  gap: 12px;
  justify-content: space-between;
  padding: 14px 16px;
}

.credential-action-heading h2 {
  font-size: 14px;
  letter-spacing: -0.01em;
  margin: 0;
}

.credential-action-heading p,
.selected-hint {
  color: var(--text-muted);
}

.credential-action-heading p {
  font-size: 12px;
  line-height: 1.45;
  margin: 5px 0 0;
}

.selected-hint {
  font-size: 13px;
  font-weight: 800;
}

.credential-action-body {
  align-items: end;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 14px 16px 16px;
  width: 100%;
}

.push-action-body {
  align-items: end;
  display: grid;
  grid-template-columns: minmax(260px, 1fr) 140px auto;
}

@media (max-width: 767px) {
  .credential-action-heading,
  .credential-action-body {
    align-items: stretch;
    flex-direction: column;
  }

  .push-action-body {
    grid-template-columns: 1fr;
  }
}
</style>
