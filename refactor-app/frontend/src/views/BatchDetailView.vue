<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import DataTable, { type Column } from "../components/DataTable.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { resourcesApi, type Row } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const route = useRoute();
const router = useRouter();
const store = useOpsStore();
const batchId = computed(() => String(route.params.batchId));
const batch = ref<Row | null>(null);
const items = ref<Row[]>([]);
const loading = ref(false);
const error = ref("");

const columns: Column[] = [
  { key: "user_account_id", label: "账号", mono: true },
  { key: "codex_credential_id", label: "Codex 授权", mono: true, summary: 28 },
  { key: "item_status", label: "明细状态", badge: true },
  { key: "batch_binding_status", label: "占用状态", badge: true },
  { key: "join_status", label: "加入状态", badge: true },
  { key: "token_status", label: "Token 状态", badge: true },
  { key: "push_status", label: "推送状态", badge: true },
  { key: "failure_code", label: "失败码", badge: true },
  { key: "failure_message", label: "失败原因" },
];

async function load() {
  loading.value = true;
  error.value = "";
  try {
    [batch.value, items.value] = await Promise.all([
      resourcesApi.batch(batchId.value),
      resourcesApi.batchItems(batchId.value),
    ]);
    store.touchRefresh();
  } catch (err) {
    error.value = String((err as Error).message ?? err);
  } finally {
    loading.value = false;
  }
}

async function activate() {
  const result = await resourcesApi.activateBatch(batchId.value);
  store.toast("批次生效任务已创建", result.job_id, "success");
  await router.push(`/jobs/${result.job_id}`);
}

function exportFailed() {
  const failed = items.value.filter((item) => item.failure_code || item.item_status === "failed");
  const blob = new Blob([JSON.stringify(failed, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${batchId.value}-failed-items.json`;
  link.click();
  URL.revokeObjectURL(link.href);
}

onMounted(load);
</script>

<template>
  <PageHeader title="批次详情" :description="batchId">
    <button class="btn" @click="exportFailed">导出失败明细</button>
    <button class="btn primary" @click="activate">生效批次</button>
    <button class="btn" @click="load">刷新</button>
  </PageHeader>
  <section v-if="batch" class="panel summary">
    <div><span>批次状态</span><StatusBadge :value="batch.batch_status" /></div>
    <div><span>生效状态</span><StatusBadge :value="batch.activation_status" /></div>
    <div><span>总数</span><strong>{{ batch.total_count }}</strong></div>
    <div><span>成功数</span><strong>{{ batch.success_count }}</strong></div>
    <div><span>失败数</span><strong>{{ batch.failed_count }}</strong></div>
  </section>
  <DataTable :columns="columns" :rows="items" :loading="loading" :error="error" empty-text="暂无批次明细。" />
</template>

<style scoped>
.summary {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr));
  margin-bottom: 18px;
  padding: 16px;
}

.summary span {
  color: var(--text-muted);
  display: block;
  font-size: 12px;
  font-weight: 800;
  margin-bottom: 8px;
}
</style>
