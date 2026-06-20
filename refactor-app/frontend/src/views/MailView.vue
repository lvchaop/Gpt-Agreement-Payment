<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";

import ResourcePage from "../components/ResourcePage.vue";
import { resourcesApi } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const router = useRouter();
const store = useOpsStore();
const allocate = ref({ user_account_id: "", purpose: "register" });
const lifecycle = ref({
  mail_lease_id: "",
  timeout_s: 60,
  failure_code: "",
  failure_message: "",
  reason: "",
});

const columns = [
  { key: "id", label: "租约 ID", mono: true },
  { key: "email", label: "邮箱" },
  { key: "lease_status", label: "租约状态", badge: true },
  { key: "external_lease_id", label: "外部租约 ID", mono: true },
  { key: "failure_code", label: "失败码", badge: true },
];

async function go(result: { job_id: string }) {
  store.toast("邮箱任务已创建", result.job_id, "success");
  await router.push(`/jobs/${result.job_id}`);
}

async function allocateLease() {
  await go(
    await resourcesApi.allocateMail({
      user_account_id: allocate.value.user_account_id || null,
      purpose: allocate.value.purpose,
    }),
  );
}

async function runMailAction(action: "poll" | "used" | "failed" | "release") {
  if (action === "poll") {
    await go(await resourcesApi.pollOtp(lifecycle.value));
  } else if (action === "used") {
    await go(await resourcesApi.markMailUsed(lifecycle.value));
  } else if (action === "failed") {
    await go(await resourcesApi.markMailFailed(lifecycle.value));
  } else {
    await go(await resourcesApi.releaseMail(lifecycle.value));
  }
}
</script>

<template>
  <ResourcePage
    title="邮箱"
    description="外部邮箱租约生命周期：分配、拉取验证码、标记已用、标记失败、释放。"
    :columns="columns"
    :loader="resourcesApi.mailLeases"
    empty-text="暂无邮箱租约。"
  >
    <template #before>
      <div class="grid-2 action-panels">
        <form class="panel filter-panel action-form" @submit.prevent="allocateLease">
          <h3>分配邮箱租约</h3>
          <label class="field"><span>账号 ID（可选）</span><input v-model="allocate.user_account_id" class="input" /></label>
          <label class="field"><span>用途</span><input v-model="allocate.purpose" class="input" /></label>
          <button class="btn primary">创建分配任务</button>
        </form>
        <section class="panel filter-panel action-form">
          <h3>租约生命周期</h3>
          <label class="field"><span>邮箱租约 ID</span><input v-model="lifecycle.mail_lease_id" class="input" /></label>
          <label class="field"><span>等待秒数</span><input v-model.number="lifecycle.timeout_s" class="input" type="number" min="1" /></label>
          <label class="field"><span>失败码</span><input v-model="lifecycle.failure_code" class="input" /></label>
          <label class="field"><span>失败原因</span><input v-model="lifecycle.failure_message" class="input" /></label>
          <label class="field"><span>释放原因</span><input v-model="lifecycle.reason" class="input" /></label>
          <div class="actions">
            <button class="btn" @click="runMailAction('poll')">拉取验证码</button>
            <button class="btn" @click="runMailAction('used')">标记已用</button>
            <button class="btn danger" @click="runMailAction('failed')">标记失败</button>
            <button class="btn" @click="runMailAction('release')">释放租约</button>
          </div>
        </section>
      </div>
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

h3 {
  margin: 0;
}
</style>
