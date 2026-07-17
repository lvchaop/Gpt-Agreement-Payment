<script setup lang="ts">
import { MailPlus, Settings2 } from "@lucide/vue";
import { ref } from "vue";
import { useRouter } from "vue-router";

import { resourcesApi, type Row } from "../api/resources";
import type { Column, TableFilter } from "../components/DataTable.vue";
import FormDrawer from "../components/FormDrawer.vue";
import EntitySelect from "../components/EntitySelect.vue";
import ResourcePage from "../components/ResourcePage.vue";
import { useOpsStore } from "../stores/ops";

const router = useRouter();
const store = useOpsStore();
const allocateOpen = ref(false);
const lifecycleOpen = ref(false);
const busy = ref(false);
const allocate = ref({ user_account_id: "", purpose: "register" });
const lifecycle = ref({ mail_lease_id: "", timeout_s: 60, failure_code: "", failure_message: "", reason: "" });
const accountLoader = async (query: string) => (await resourcesApi.accountOptions(query)).items;

const columns: Column[] = [
  { key: "id", label: "租约 ID", mono: true, summary: 24, copyable: true },
  { key: "email", label: "邮箱", copyable: true }, { key: "lease_status", label: "状态", badge: true, sortable: true },
  { key: "purpose", label: "用途" }, { key: "user_account_id", label: "账号 ID", mono: true, summary: 22 },
  { key: "external_lease_id", label: "外部租约 ID", mono: true, summary: 22 },
  { key: "failure_code", label: "失败码", badge: true }, { key: "failure_message", label: "失败信息", summary: 36 },
  { key: "created_at", label: "分配时间", type: "datetime", relativeTime: true, sortable: true },
];
const filters: TableFilter[] = [{ key: "lease_status", label: "租约状态", options: [
  { label: "已分配", value: "allocated" }, { label: "已使用", value: "used" },
  { label: "失败", value: "failed" }, { label: "已释放", value: "released" },
] }];

async function go(request: Promise<{ job_id: string }>) {
  busy.value = true;
  try { const result = await request; store.toast("邮箱任务已创建", result.job_id, "success"); await router.push(`/jobs/${result.job_id}`); }
  catch (err) { store.toast("创建任务失败", String((err as Error).message ?? err), "error"); }
  finally { busy.value = false; }
}

async function allocateLease() {
  allocateOpen.value = false;
  await go(resourcesApi.allocateMail({ user_account_id: allocate.value.user_account_id || null, purpose: allocate.value.purpose }));
}

function openLifecycle(row: Row) {
  lifecycle.value = { mail_lease_id: String(row.id || ""), timeout_s: 60, failure_code: "", failure_message: "", reason: "" };
  lifecycleOpen.value = true;
}

async function runMailAction(action: "poll" | "used" | "failed" | "release") {
  lifecycleOpen.value = false;
  if (action === "poll") await go(resourcesApi.pollOtp(lifecycle.value));
  else if (action === "used") await go(resourcesApi.markMailUsed(lifecycle.value));
  else if (action === "failed") await go(resourcesApi.markMailFailed(lifecycle.value));
  else await go(resourcesApi.releaseMail(lifecycle.value));
}
</script>

<template>
  <ResourcePage title="邮箱租约" description="查看邮箱分配、验证码等待和最终释放状态。" :columns="columns" :loader="resourcesApi.mailLeases" :filters="filters" empty-text="暂无邮箱租约。">
    <template #actions><button class="btn primary" @click="allocateOpen = true"><MailPlus :size="16" />分配邮箱</button></template>
    <template #rowActions="{ row }"><button class="icon-btn labeled" @click="openLifecycle(row)"><Settings2 :size="15" />处理</button></template>
  </ResourcePage>
  <FormDrawer :open="allocateOpen" title="分配邮箱租约" submit-text="创建分配任务" :busy="busy" @close="allocateOpen = false" @submit="allocateLease">
    <label class="field"><span>账号（可选）</span><EntitySelect v-model="allocate.user_account_id" :loader="accountLoader" placeholder="按邮箱或账号 ID 搜索" /></label>
    <label class="field"><span>用途</span><input v-model="allocate.purpose" class="input" /></label>
  </FormDrawer>
  <FormDrawer :open="lifecycleOpen" title="处理邮箱租约" :description="lifecycle.mail_lease_id" submit-text="拉取验证码" :busy="busy" @close="lifecycleOpen = false" @submit="runMailAction('poll')">
    <label class="field"><span>等待秒数</span><input v-model.number="lifecycle.timeout_s" class="input" type="number" min="1" /></label>
    <label class="field"><span>失败码</span><input v-model="lifecycle.failure_code" class="input" /></label>
    <label class="field"><span>失败原因</span><textarea v-model="lifecycle.failure_message" class="textarea" /></label>
    <label class="field"><span>释放原因</span><textarea v-model="lifecycle.reason" class="textarea" /></label>
    <div class="mail-actions"><button class="btn" type="button" @click="runMailAction('used')">标记已用</button><button class="btn danger" type="button" @click="runMailAction('failed')">标记失败</button><button class="btn" type="button" @click="runMailAction('release')">释放租约</button></div>
  </FormDrawer>
</template>

<style scoped>.mail-actions { border-top: 1px solid var(--border); display: flex; flex-wrap: wrap; gap: 7px; padding-top: 12px; }</style>
