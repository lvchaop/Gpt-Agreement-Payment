<script setup lang="ts">
const props = defineProps<{
  value?: unknown;
}>();

function normalized(value: unknown) {
  return String(value ?? "unknown").trim() || "unknown";
}

function tone(value: string) {
  if (["succeeded", "success", "active", "ok", "pushed", "available", "used"].includes(value)) {
    return "success";
  }
  if (["running", "refreshing", "queued", "pending", "token_generated"].includes(value)) {
    return "info";
  }
  if (["partial_success", "warning", "allocated", "cooldown", "activating"].includes(value)) {
    return "warning";
  }
  if (["failed", "invalid", "error", "dead", "revoked", "banned"].includes(value)) {
    return "danger";
  }
  if (["superseded", "accepted", "joined"].includes(value)) {
    return "purple";
  }
  return "neutral";
}

function displayText(value: string) {
  const labels: Record<string, string> = {
    unknown: "未知",
    active: "有效",
    invalid: "无效",
    disabled: "禁用",
    expired: "已过期",
    error: "错误",
    queued: "排队中",
    running: "运行中",
    succeeded: "成功",
    success: "成功",
    failed: "失败",
    pending: "待处理",
    refreshing: "刷新中",
    revoked: "已吊销",
    dead: "不可用",
    ok: "正常",
    pushed: "已推送",
    available: "可用",
    used: "已使用",
    token_generated: "已生成 token",
    partial_success: "部分成功",
    warning: "警告",
    allocated: "已分配",
    cooldown: "冷却中",
    activating: "激活中",
    superseded: "已被替代",
    accepted: "已接受",
    joined: "已加入",
    banned: "封禁",
    invited: "已邀请",
    left: "已离开",
    skipped: "已跳过",
  };
  return labels[value] ?? value;
}
</script>

<template>
  <span class="badge" :class="tone(normalized(props.value))" :title="normalized(props.value)">
    {{ displayText(normalized(props.value)) }}
  </span>
</template>

<style scoped>
.badge {
  align-items: center;
  border: 1px solid transparent;
  border-radius: 999px;
  display: inline-flex;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.01em;
  line-height: 1;
  min-height: 24px;
  padding: 0 9px;
  white-space: nowrap;
}

.success {
  background: rgba(34, 197, 94, 0.13);
  border-color: rgba(34, 197, 94, 0.28);
  color: #86efac;
}

.info {
  background: rgba(59, 130, 246, 0.14);
  border-color: rgba(59, 130, 246, 0.3);
  color: #93c5fd;
}

.warning {
  background: rgba(245, 158, 11, 0.14);
  border-color: rgba(245, 158, 11, 0.3);
  color: #fcd34d;
}

.danger {
  background: rgba(239, 68, 68, 0.14);
  border-color: rgba(239, 68, 68, 0.32);
  color: #fca5a5;
}

.purple {
  background: rgba(168, 85, 247, 0.14);
  border-color: rgba(168, 85, 247, 0.3);
  color: #d8b4fe;
}

.neutral {
  background: rgba(148, 163, 184, 0.11);
  border-color: rgba(148, 163, 184, 0.22);
  color: #cbd5e1;
}
</style>
