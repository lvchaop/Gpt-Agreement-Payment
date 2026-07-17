<script setup lang="ts">
import { Download, Link2, Stethoscope } from "@lucide/vue";
import { ref } from "vue";
import { useRouter } from "vue-router";

import { resourcesApi } from "../api/resources";
import { getJob, listRuns } from "../api/jobs";
import type { Column, TableFilter } from "../components/DataTable.vue";
import FormDrawer from "../components/FormDrawer.vue";
import EntitySelect from "../components/EntitySelect.vue";
import ResourcePage from "../components/ResourcePage.vue";
import { useOpsStore } from "../stores/ops";

const router = useRouter();
const store = useOpsStore();
const importOpen = ref(false);
const bindOpen = ref(false);
const userAccountId = ref("");
const webshareDownloadUrl = ref("https://proxy.webshare.io/api/v2/proxy/list/download/moxpwbdapgcdyarkksjyczhsadwugnbywquzjuyg/-/any/username/direct/-/?plan_id=13623688");
const submitting = ref(false);
const checkingId = ref("");
const accountLoader = async (query: string) => (await resourcesApi.accountOptions(query)).items;

const columns: Column[] = [
  { key: "id", label: "代理 ID", mono: true, summary: 22, copyable: true },
  { key: "proxy_type", label: "代理类型", badge: true },
  { key: "proxy_host", label: "主机", copyable: true }, { key: "proxy_port", label: "端口" },
  { key: "country_code", label: "国家", sortable: true }, { key: "city_name", label: "城市" },
  { key: "proxy_status", label: "状态", badge: true, sortable: true },
  { key: "provider_valid", label: "供应商有效", type: "boolean" },
  { key: "active_account_binding_count", label: "绑定账号数", type: "number" },
  { key: "active_admin_binding_count", label: "绑定管理员数", type: "number" },
  { key: "last_healthcheck_at", label: "最近检测", type: "datetime", relativeTime: true },
  { key: "updated_at", label: "更新时间", type: "datetime", sortable: true },
];
const filters: TableFilter[] = [
  { key: "proxy_type", label: "代理类型", options: [
    { label: "静态住宅", value: "static_proxy" }, { label: "普通代理", value: "proxyserver" },
  ] },
  { key: "proxy_status", label: "代理状态", options: [
    { label: "可用", value: "available" }, { label: "已绑定", value: "bound" },
    { label: "错误", value: "error" }, { label: "无效", value: "invalid" },
    { label: "冷却", value: "cooldown" }, { label: "已退役", value: "retired" },
    { label: "未知", value: "unknown" },
  ] },
  { key: "provider_valid", label: "供应商状态", options: [
    { label: "有效", value: "yes" }, { label: "无效", value: "no" },
  ] },
];

async function submitProxyImport() {
  if (!webshareDownloadUrl.value.trim()) { store.toast("缺少下载地址", "请填写 Webshare 下载地址。", "warning"); return; }
  submitting.value = true;
  try {
    const result = await resourcesApi.refreshProxies({ download_url: webshareDownloadUrl.value.trim() });
    store.toast("代理导入任务已创建", result.job_id, "success"); importOpen.value = false;
    await router.push(`/jobs/${result.job_id}`);
  } catch (err) { store.toast("创建任务失败", String((err as Error).message ?? err), "error"); }
  finally { submitting.value = false; }
}

async function bindProxy() {
  if (!userAccountId.value.trim()) { store.toast("缺少账号", "请填写账号 ID。", "warning"); return; }
  submitting.value = true;
  try {
    const result = await resourcesApi.bindProxy({ user_account_id: userAccountId.value.trim() });
    store.toast("代理绑定任务已创建", result.job_id, "success"); bindOpen.value = false;
    await router.push(`/jobs/${result.job_id}`);
  } catch (err) { store.toast("创建任务失败", String((err as Error).message ?? err), "error"); }
  finally { submitting.value = false; }
}

async function healthcheckProxy(row: Record<string, unknown>, reload: () => Promise<void>) {
  const id = String(row.id || ""); if (!id) return;
  checkingId.value = id;
  try {
    const created = await resourcesApi.healthcheckProxy(id);
    store.toast("代理检测任务已创建", created.job_id, "success");
    const result = await waitForHealthcheckResult(created.job_id);
    store.toast(
      result.alive ? "代理检测成功" : "代理检测失败",
      `释放绑定 ${result.released_bind_count} 个`,
      result.alive ? "success" : "warning",
    );
    await reload();
  } catch (err) { store.toast("检测失败", String((err as Error).message ?? err), "error"); }
  finally { checkingId.value = ""; }
}

async function waitForHealthcheckResult(jobId: string) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const job = await getJob(jobId);
    if (["succeeded", "failed", "cancelled"].includes(job.job_status)) {
      const runs = await listRuns(jobId);
      const run = runs.at(-1);
      if (job.job_status !== "succeeded" || !run) {
        throw new Error(String(run?.error_message || `代理检测 Job ${job.job_status}`));
      }
      const output = run.output_json && typeof run.output_json === "object"
        ? run.output_json as Record<string, unknown>
        : {};
      return {
        alive: output.alive === true,
        released_bind_count: Number(output.released_bind_count || 0),
      };
    }
    await new Promise((resolve) => window.setTimeout(resolve, 500));
  }
  throw new Error("代理检测等待超时");
}
</script>

<template>
  <ResourcePage title="代理池" description="查看代理库存、供应商状态和最近检测结果。" :columns="columns" :loader="resourcesApi.proxies" :filters="filters" empty-text="暂无代理。">
    <template #actions>
      <button class="btn primary" @click="importOpen = true"><Download :size="16" />导入 Webshare</button>
      <button class="btn" @click="bindOpen = true"><Link2 :size="16" />绑定账号代理</button>
    </template>
    <template #rowActions="{ row, reload }"><button class="icon-btn labeled" :disabled="checkingId === row.id" @click="healthcheckProxy(row, reload)"><Stethoscope :size="15" />检测</button></template>
  </ResourcePage>
  <FormDrawer :open="importOpen" title="导入 Webshare 代理池" description="提交后创建后台导入任务。" submit-text="创建导入任务" :busy="submitting" @close="importOpen = false" @submit="submitProxyImport">
    <label class="field"><span>Webshare 下载地址</span><textarea v-model="webshareDownloadUrl" class="textarea" required /></label>
  </FormDrawer>
  <FormDrawer :open="bindOpen" title="绑定账号代理" description="按账号分配并绑定一条可用代理。" submit-text="创建绑定任务" :busy="submitting" @close="bindOpen = false" @submit="bindProxy">
    <label class="field"><span>账号</span><EntitySelect v-model="userAccountId" :loader="accountLoader" placeholder="按邮箱或账号 ID 搜索" /></label>
  </FormDrawer>
</template>
