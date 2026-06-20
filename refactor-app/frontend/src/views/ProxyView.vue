<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";

import ResourcePage from "../components/ResourcePage.vue";
import { resourcesApi } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const router = useRouter();
const store = useOpsStore();
const userAccountId = ref("");
const webshareDownloadUrl = ref(
  "https://proxy.webshare.io/api/v2/proxy/list/download/moxpwbdapgcdyarkksjyczhsadwugnbywquzjuyg/-/any/username/direct/-/?plan_id=13623688",
);
const isImporting = ref(false);

const columns = [
  { key: "id", label: "代理 ID", mono: true },
  { key: "proxy_host", label: "主机" },
  { key: "proxy_port", label: "端口" },
  { key: "country_code", label: "国家" },
  { key: "city_name", label: "城市" },
  { key: "proxy_status", label: "状态", badge: true },
  { key: "provider_valid", label: "供应商有效" },
  { key: "last_healthcheck_at", label: "最近健康检查" },
];

async function submitProxyImport() {
  if (isImporting.value) return;
  const downloadUrl = webshareDownloadUrl.value.trim();
  if (!downloadUrl) {
    store.toast("缺少下载地址", "请先填写 Webshare download URL", "error");
    return;
  }

  isImporting.value = true;
  try {
    const result = await resourcesApi.refreshProxies({ download_url: downloadUrl });
    store.toast("Webshare 代理池导入任务已创建", result.job_id, "success");
    await router.push(`/jobs/${result.job_id}`);
  } finally {
    isImporting.value = false;
  }
}

async function bindProxy() {
  const result = await resourcesApi.bindProxy({ user_account_id: userAccountId.value });
  store.toast("代理绑定任务已创建", result.job_id, "success");
  await router.push(`/jobs/${result.job_id}`);
}

async function healthcheckProxy(row: Record<string, unknown>, reload: () => Promise<void>) {
  const id = String(row.id || "");
  if (!id) return;
  const result = await resourcesApi.healthcheckProxy(id);
  store.toast(
    result.alive ? "代理检测成功" : "代理检测失败",
    `释放绑定 ${result.released_bind_count} 个，job=${result.job_id}`,
    result.alive ? "success" : "warning",
  );
  await reload();
}
</script>

<template>
  <ResourcePage
    title="代理"
    description="Webshare IP 池和账号代理绑定。代理绑定在 User Account 上。"
    :columns="columns"
    :loader="resourcesApi.proxies"
    empty-text="暂无代理。"
  >
    <template #before>
      <div class="grid-2 action-panels">
        <form class="panel filter-panel action-form" @submit.prevent="submitProxyImport">
          <h3>导入 Webshare IP 池</h3>
          <p class="muted">提交后才会创建导入任务；任务会下载文本代理池并 upsert 到 proxy_inventory。</p>
          <label class="field">
            <span>Webshare download URL</span>
            <textarea
              v-model="webshareDownloadUrl"
              class="input"
              rows="3"
              required
              placeholder="https://proxy.webshare.io/api/v2/proxy/list/download/..."
            />
          </label>
          <button class="btn primary" :disabled="isImporting">
            {{ isImporting ? "提交中..." : "提交导入任务" }}
          </button>
        </form>
        <form class="panel filter-panel action-form" @submit.prevent="bindProxy">
          <h3>绑定账号代理</h3>
          <label class="field">
            <span>账号 ID</span>
            <input v-model="userAccountId" class="input" required />
          </label>
          <button class="btn primary">创建绑定任务</button>
        </form>
      </div>
    </template>
    <template #rowActions="{ row, reload }">
      <button class="btn compact-action" @click="healthcheckProxy(row, reload)">检测</button>
    </template>
  </ResourcePage>
</template>

<style scoped>
.action-panels {
  margin-bottom: 18px;
}

.action-form {
  display: grid;
  gap: 12px;
}

h3,
p {
  margin: 0;
}

.compact-action {
  min-height: 30px;
  padding: 0 10px;
}
</style>
