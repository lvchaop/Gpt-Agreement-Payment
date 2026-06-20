<script setup lang="ts">
import { useRouter } from "vue-router";

import ResourcePage from "../components/ResourcePage.vue";
import { resourcesApi } from "../api/resources";

const router = useRouter();

const columns = [
  { key: "id", label: "批次 ID", mono: true },
  { key: "team_workspace_id", label: "团队空间", mono: true },
  { key: "batch_status", label: "批次状态", badge: true },
  { key: "activation_status", label: "生效状态", badge: true },
  { key: "total_count", label: "总数" },
  { key: "success_count", label: "成功数" },
  { key: "failed_count", label: "失败数" },
];
</script>

<template>
  <ResourcePage
    title="加入批次"
    description="批次只从已生成的 Codex 授权创建；请到“Codex 授权”页选择授权后创建批次。"
    :columns="columns"
    :loader="resourcesApi.batches"
    empty-text="暂无加入批次。"
    @row-click="(row) => row.id && router.push(`/join-batches/${row.id}`)"
  />
</template>
