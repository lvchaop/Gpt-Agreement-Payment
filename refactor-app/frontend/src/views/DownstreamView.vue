<script setup lang="ts">
import ResourcePage from "../components/ResourcePage.vue";
import { resourcesApi } from "../api/resources";

const columns = [
  { key: "id", label: "推送记录 ID", mono: true },
  { key: "batch_item_id", label: "批次明细", mono: true },
  { key: "downstream_provider", label: "下游平台", badge: true },
  { key: "push_status", label: "推送状态", badge: true },
  { key: "downstream_external_id", label: "下游外部 ID", mono: true },
  { key: "downstream_chatgpt_account_id", label: "下游空间", mono: true },
  { key: "token_chatgpt_account_id", label: "Token 空间", mono: true },
  { key: "error_code", label: "错误码", badge: true },
  { key: "error_message", label: "错误信息" },
];
</script>

<template>
  <ResourcePage
    title="下游推送"
    description="CPA / Sub2API 推送结果。同一批次 item + downstream_provider 只保留一条记录。"
    :columns="columns"
    :loader="resourcesApi.downstream"
    empty-text="暂无下游推送记录。"
  />
</template>
