<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";

import ResourcePage from "../components/ResourcePage.vue";
import type { Row } from "../api/resources";
import { resourcesApi } from "../api/resources";
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();
const router = useRouter();
const pageRef = ref<InstanceType<typeof ResourcePage> | null>(null);
const selectedRows = ref<Row[]>([]);
const selectedCount = ref(0);
const adminEmail = ref("");
const externalWorkspaceId = ref("");
const acceptConcurrency = ref(50);

const columns = [
  { key: "id", label: "成员关系 ID", mono: true, summary: 28 },
  { key: "user_email", label: "账号邮箱", summary: 30 },
  { key: "admin_email", label: "管理员邮箱", summary: 30 },
  { key: "external_workspace_id", label: "外部空间 ID", mono: true, summary: 28 },
  { key: "workspace_name", label: "空间名称" },
  { key: "workspace_plan_type", label: "空间订阅类型", summary: 24 },
  { key: "membership_status", label: "成员状态", badge: true },
  { key: "failure_code", label: "失败码", summary: 24 },
  { key: "failure_message", label: "失败信息", summary: 36 },
];

async function loadMemberships() {
  return resourcesApi.memberships({
    admin_email: adminEmail.value,
    external_workspace_id: externalWorkspaceId.value,
  });
}

function updateSelection(rows: Record<string, unknown>[]) {
  selectedRows.value = rows as Row[];
  selectedCount.value = rows.length;
}

async function reload() {
  await pageRef.value?.load();
}

async function acceptMemberships(rows: Row[]) {
  const ids = rows.map((row) => String(row.id || "")).filter(Boolean);
  if (!ids.length) {
    store.toast("未选择成员", "请先勾选要接受邀请的成员关系。", "warning");
    return;
  }
  const result = await resourcesApi.membershipAcceptInvite({
    membership_ids: ids,
    created_by: "ops-ui",
    concurrency: acceptConcurrency.value,
  });
  store.toast(
    "接受邀请执行完成",
    `work=${result.work_count} 并发=${result.concurrency} 成功=${result.succeeded} 失败=${result.failed}`,
    result.failed > 0 ? "warning" : "success",
  );
  await router.push({ name: "job-trace", params: { jobId: result.job_id } });
}

async function acceptOne(row: Row) {
  await acceptMemberships([row]);
}
</script>

<template>
  <ResourcePage
    ref="pageRef"
    title="空间成员"
    description="账号与 Team Workspace 的当前关系、邀请状态和接受邀请动作。"
    :columns="columns"
    :loader="loadMemberships"
    empty-text="暂无成员关系。"
    selectable
    @selection-change="updateSelection"
  >
    <template #actions>
      <div class="membership-toolbar">
        <label class="field">
          <span>管理员邮箱</span>
          <input v-model="adminEmail" class="input" placeholder="按管理员邮箱筛选" @keyup.enter="reload" />
        </label>
        <label class="field">
          <span>外部空间 ID</span>
          <input
            v-model="externalWorkspaceId"
            class="input"
            placeholder="按 external_workspace_id 筛选"
            @keyup.enter="reload"
          />
        </label>
        <label class="field compact-field">
          <span>并发 work</span>
          <input v-model.number="acceptConcurrency" class="input" type="number" min="1" max="500" />
        </label>
        <div class="filter-actions">
          <button class="btn" @click="reload">筛选</button>
          <button class="btn primary" :disabled="selectedCount === 0" @click="acceptMemberships(selectedRows)">
            接受选中邀请（{{ selectedCount }}）
          </button>
        </div>
      </div>
    </template>
    <template #rowActions="{ row }">
      <button class="btn small" @click="acceptOne(row)">接受邀请</button>
    </template>
  </ResourcePage>
</template>

<style scoped>
.membership-toolbar {
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(220px, 1fr) minmax(260px, 1fr) 120px auto;
  width: 100%;
}

.compact-field .input {
  min-width: 0;
}

.small {
  padding: 8px 10px;
  white-space: nowrap;
}

@media (max-width: 980px) {
  .membership-toolbar {
    grid-template-columns: 1fr;
  }

  .filter-actions {
    justify-content: stretch;
  }
}
</style>
