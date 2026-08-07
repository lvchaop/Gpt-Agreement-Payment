<script setup lang="ts">
import {
  Activity,
  AtSign,
  Boxes,
  Cable,
  ChevronLeft,
  CircleGauge,
  CreditCard,
  DatabaseZap,
  FileClock,
  KeyRound,
  LayoutDashboard,
  Menu,
  Network,
  RefreshCcw,
  ServerCog,
  Users,
  UserRoundPlus,
  Workflow,
  X,
} from "@lucide/vue";
import { onBeforeUnmount, onMounted, ref } from "vue";
import { RouterLink, RouterView } from "vue-router";

import { getJson } from "../api/client";
import DateTimeText from "../components/DateTimeText.vue";
import ToastHost from "../components/ToastHost.vue";
import { useOpsStore } from "../stores/ops";

const store = useOpsStore();
const menuOpen = ref(false);
const collapsed = ref(localStorage.getItem("ops.sidebar.collapsed") === "1");
const apiHealthy = ref<boolean | null>(null);
const healthCheckedAt = ref("");
let healthTimer: number | undefined;

const navGroups = [
  { label: "运营概览", items: [{ to: "/", label: "总览", icon: LayoutDashboard }] },
  {
    label: "账号与空间",
    items: [
      { to: "/protocol-registration", label: "账号注册", icon: UserRoundPlus },
      { to: "/email-change", label: "换绑邮箱", icon: RefreshCcw },
      { to: "/accounts", label: "账号", icon: Users },
      { to: "/spaces", label: "空间", icon: Boxes },
      { to: "/memberships", label: "空间成员", icon: Network },
      { to: "/space-credentials", label: "空间凭证", icon: KeyRound },
    ],
  },
  {
    label: "交付与结算",
    items: [
      { to: "/downstream-channels", label: "下游渠道", icon: Cable },
      { to: "/space-push-records", label: "推送记录", icon: DatabaseZap },
    ],
  },
  {
    label: "任务与资源",
    items: [
      { to: "/job-list", label: "Job 列表", icon: Activity },
      { to: "/jobs", label: "任务日志", icon: FileClock },
      { to: "/proxy", label: "代理池", icon: ServerCog },
      { to: "/mail", label: "邮箱", icon: AtSign },
    ],
  },
  {
    label: "支付资料",
    items: [{ to: "/payment-method-pools", label: "支付资料池", icon: CreditCard }],
  },
];

async function checkHealth() {
  try {
    await getJson<Record<string, unknown>>("/health");
    apiHealthy.value = true;
  } catch {
    apiHealthy.value = false;
  }
  healthCheckedAt.value = new Date().toISOString();
}

function toggleCollapsed() {
  collapsed.value = !collapsed.value;
  localStorage.setItem("ops.sidebar.collapsed", collapsed.value ? "1" : "0");
}

onMounted(() => {
  void checkHealth();
  healthTimer = window.setInterval(checkHealth, 30000);
});
onBeforeUnmount(() => { if (healthTimer) window.clearInterval(healthTimer); });
</script>

<template>
  <div class="ops-shell" :class="{ collapsed }">
    <button class="mobile-menu icon-btn" title="打开导航" @click="menuOpen = true"><Menu :size="18" /></button>
    <div v-if="menuOpen" class="sidebar-scrim" @click="menuOpen = false" />
    <aside class="sidebar" :class="{ 'mobile-open': menuOpen }">
      <div class="brand">
        <span class="brand-mark"><Workflow :size="19" /></span>
        <div class="brand-copy"><strong>运营控制台</strong><small>GAP Operations</small></div>
        <button class="mobile-close icon-btn" title="关闭导航" @click="menuOpen = false"><X :size="17" /></button>
      </div>
      <nav>
        <section v-for="group in navGroups" :key="group.label" class="nav-group">
          <span class="nav-heading">{{ group.label }}</span>
          <RouterLink v-for="item in group.items" :key="item.to" :to="item.to" :title="item.label" @click="menuOpen = false">
            <component :is="item.icon" :size="17" />
            <span>{{ item.label }}</span>
          </RouterLink>
        </section>
      </nav>
      <button class="collapse-button" title="收起或展开导航" @click="toggleCollapsed">
        <ChevronLeft :size="16" />
        <span>收起导航</span>
      </button>
    </aside>
    <main class="main">
      <header class="topbar">
        <div class="topbar-title"><CircleGauge :size="17" /><strong>运营工作台</strong></div>
        <div class="topbar-status">
          <span class="health" :class="{ ok: apiHealthy === true, bad: apiHealthy === false }">
            <i />{{ apiHealthy === null ? "接口检测中" : apiHealthy ? "接口正常" : "接口异常" }}
          </span>
          <DateTimeText v-if="healthCheckedAt" :value="healthCheckedAt" relative />
          <span v-if="store.lastRefresh" class="last-refresh">数据刷新 {{ store.lastRefresh }}</span>
        </div>
      </header>
      <section class="content"><RouterView /></section>
    </main>
    <ToastHost />
  </div>
</template>

<style scoped>
.ops-shell { display: grid; grid-template-columns: var(--sidebar-width) minmax(0, 1fr); min-height: 100vh; }
.sidebar { background: var(--sidebar-bg); border-right: 1px solid var(--border); display: flex; flex-direction: column; height: 100vh; padding: 12px 10px; position: sticky; top: 0; z-index: 30; }
.brand { align-items: center; display: flex; gap: 9px; min-height: 50px; padding: 4px 6px 12px; }
.brand-mark { align-items: center; background: var(--accent-strong); border-radius: 6px; display: flex; height: 32px; justify-content: center; width: 32px; }
.brand-copy { min-width: 0; }
.brand strong, .brand small { display: block; white-space: nowrap; }
.brand strong { font-size: 14px; }
.brand small { color: var(--text-faint); font-size: 10px; margin-top: 2px; }
nav { display: grid; gap: 13px; overflow-y: auto; padding: 5px 0 10px; }
.nav-group { display: grid; gap: 2px; }
.nav-heading { color: var(--text-faint); font-size: 10px; font-weight: 800; padding: 5px 9px; }
nav a { align-items: center; border-left: 2px solid transparent; border-radius: 3px; color: var(--text-muted); display: flex; font-size: 12px; font-weight: 650; gap: 9px; min-height: 34px; padding: 0 9px; }
nav a:hover { background: var(--panel-bg-2); color: var(--text-primary); }
nav a.router-link-active { background: var(--accent-soft); border-left-color: var(--accent); color: #dcecff; }
nav a svg { flex: 0 0 auto; }
.collapse-button { align-items: center; background: transparent; border-top: 1px solid var(--border); color: var(--text-faint); cursor: pointer; display: flex; font-size: 11px; gap: 8px; margin-top: auto; min-height: 42px; padding: 8px 10px 0; }
.main { min-width: 0; }
.topbar { align-items: center; background: rgba(21, 23, 25, 0.94); border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; min-height: 52px; padding: 0 18px; position: sticky; top: 0; z-index: 20; }
.topbar-title, .topbar-status { align-items: center; display: flex; gap: 10px; }
.topbar-title strong { font-size: 13px; }
.health { align-items: center; color: var(--text-muted); display: inline-flex; font-size: 11px; gap: 6px; }
.health i { background: var(--text-faint); border-radius: 50%; height: 7px; width: 7px; }
.health.ok i { background: var(--success); }
.health.bad { color: var(--danger-text); }
.health.bad i { background: var(--danger); }
.last-refresh { color: var(--text-faint); font-size: 11px; }
.content { min-width: 0; padding: 18px; }
.mobile-menu, .mobile-close, .sidebar-scrim { display: none; }

.ops-shell.collapsed { grid-template-columns: 62px minmax(0, 1fr); }
.collapsed .brand-copy, .collapsed .nav-heading, .collapsed nav a span, .collapsed .collapse-button span { display: none; }
.collapsed .brand { justify-content: center; }
.collapsed nav a { justify-content: center; padding: 0; }
.collapsed .collapse-button { justify-content: center; }
.collapsed .collapse-button svg { transform: rotate(180deg); }

@media (max-width: 840px) {
  .ops-shell, .ops-shell.collapsed { display: block; }
  .sidebar { left: 0; position: fixed; transform: translateX(-100%); transition: transform 0.18s ease; width: min(280px, 86vw); }
  .sidebar.mobile-open { transform: translateX(0); }
  .mobile-menu { display: inline-flex; left: 10px; position: fixed; top: 9px; z-index: 22; }
  .mobile-close { display: inline-flex; margin-left: auto; }
  .sidebar-scrim { background: rgba(0, 0, 0, 0.58); display: block; inset: 0; position: fixed; z-index: 29; }
  .topbar { padding-left: 56px; }
  .topbar-title strong, .last-refresh, .topbar-status :deep(.date-time) { display: none; }
  .content { padding: 12px; }
  .collapsed .brand-copy, .collapsed .nav-heading, .collapsed nav a span { display: block; }
  .collapsed .brand { justify-content: flex-start; }
  .collapsed nav a { justify-content: flex-start; padding: 0 9px; }
  .collapse-button { display: none; }
}
</style>
