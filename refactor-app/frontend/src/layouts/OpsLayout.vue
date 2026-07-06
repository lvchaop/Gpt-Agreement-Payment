<script setup lang="ts">
import { RouterLink, RouterView } from "vue-router";

import ToastHost from "../components/ToastHost.vue";
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();

const nav = [
  { to: "/", label: "总览" },
  { to: "/jobs", label: "任务" },
  { to: "/automation-scheduler", label: "自动化调度" },
  { to: "/automation-monitor", label: "自动化监控" },
  { to: "/accounts", label: "账号" },
  { to: "/spaces", label: "空间" },
  { to: "/memberships", label: "空间成员" },
  { to: "/space-credentials", label: "空间凭证" },
  { to: "/proxy", label: "代理" },
  { to: "/mail", label: "邮箱" },
  { to: "/downstream-channels", label: "下游渠道" },
];
</script>

<template>
  <div class="ops-shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark">R</span>
        <div>
          <strong>重构运维</strong>
          <small>控制台</small>
        </div>
      </div>
      <nav>
        <RouterLink v-for="item in nav" :key="item.to" :to="item.to">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="main">
      <header class="topbar">
        <div>
          <strong>重构运维控制台</strong>
          <span>数据库正常</span>
          <span>接口正常</span>
          <span>Worker 手动</span>
        </div>
        <small>最近刷新：{{ store.lastRefresh || "未刷新" }}</small>
      </header>
      <section class="content">
        <RouterView />
      </section>
    </main>
    <ToastHost />
  </div>
</template>

<style scoped>
.ops-shell {
  display: grid;
  grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
  min-height: 100vh;
  overflow-x: hidden;
}

.sidebar {
  background: rgba(15, 23, 42, 0.92);
  border-right: 1px solid var(--border);
  min-height: 100vh;
  padding: 18px 14px;
  position: sticky;
  top: 0;
}

.brand {
  align-items: center;
  display: flex;
  gap: 12px;
  margin-bottom: 22px;
  padding: 6px 8px;
}

.brand-mark {
  align-items: center;
  background: linear-gradient(135deg, var(--accent), var(--purple));
  border-radius: 12px;
  display: grid;
  font-size: 20px;
  font-weight: 900;
  height: 42px;
  place-items: center;
  width: 42px;
}

.brand strong,
.brand small {
  display: block;
}

.brand small {
  color: var(--text-muted);
  font-size: 12px;
}

nav {
  display: grid;
  gap: 5px;
}

nav a {
  border: 1px solid transparent;
  border-radius: 12px;
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 800;
  padding: 11px 12px;
}

nav a:hover,
nav a.router-link-active {
  background: rgba(59, 130, 246, 0.12);
  border-color: rgba(59, 130, 246, 0.24);
  color: var(--text-primary);
}

.main {
  min-width: 0;
  overflow-x: hidden;
}

.topbar {
  align-items: center;
  backdrop-filter: blur(18px);
  background: rgba(11, 16, 32, 0.72);
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  min-height: 64px;
  padding: 0 24px;
  position: sticky;
  top: 0;
  z-index: 10;
}

.topbar div {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.topbar strong {
  margin-right: 10px;
}

.topbar span {
  background: rgba(34, 197, 94, 0.12);
  border: 1px solid rgba(34, 197, 94, 0.28);
  border-radius: 999px;
  color: #86efac;
  font-size: 12px;
  font-weight: 800;
  padding: 5px 8px;
}

.topbar small {
  color: var(--text-muted);
}

.content {
  padding: 24px;
  min-width: 0;
}

@media (max-width: 900px) {
  .ops-shell {
    grid-template-columns: 1fr;
  }

  .sidebar {
    min-height: auto;
    position: static;
  }

  nav {
    display: flex;
    overflow-x: auto;
    padding-bottom: 4px;
  }

  nav a {
    white-space: nowrap;
  }

  .topbar {
    align-items: stretch;
    flex-direction: column;
    gap: 10px;
    min-height: auto;
    padding: 14px 16px;
    position: static;
  }

  .topbar div {
    align-items: flex-start;
    gap: 8px;
  }

  .topbar strong {
    flex-basis: 100%;
    margin-right: 0;
  }

  .content {
    padding: 16px;
  }
}
</style>
