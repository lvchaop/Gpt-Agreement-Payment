import { createRouter, createWebHistory } from "vue-router";

import AccountsView from "../views/AccountsView.vue";
import BatchDetailView from "../views/BatchDetailView.vue";
import CodexCredentialsView from "../views/CodexCredentialsView.vue";
import DashboardView from "../views/DashboardView.vue";
import DownstreamView from "../views/DownstreamView.vue";
import JobsView from "../views/JobsView.vue";
import JobTraceView from "../views/JobTraceView.vue";
import JoinBatchesView from "../views/JoinBatchesView.vue";
import MailView from "../views/MailView.vue";
import MembershipsView from "../views/MembershipsView.vue";
import ProxyView from "../views/ProxyView.vue";
import TeamWorkspacesView from "../views/TeamWorkspacesView.vue";

export const router = createRouter({
  history: createWebHistory("/ops/"),
  routes: [
    { path: "/", component: DashboardView, name: "dashboard" },
    { path: "/jobs", component: JobsView, name: "jobs" },
    { path: "/jobs/:jobId", component: JobTraceView, name: "job-trace" },
    { path: "/accounts", component: AccountsView, name: "accounts" },
    { path: "/team-workspaces", component: TeamWorkspacesView, name: "team-workspaces" },
    { path: "/memberships", component: MembershipsView, name: "memberships" },
    { path: "/join-batches", component: JoinBatchesView, name: "join-batches" },
    { path: "/join-batches/:batchId", component: BatchDetailView, name: "batch-detail" },
    { path: "/codex-credentials", component: CodexCredentialsView, name: "codex-credentials" },
    { path: "/proxy", component: ProxyView, name: "proxy" },
    { path: "/mail", component: MailView, name: "mail" },
    { path: "/downstream", component: DownstreamView, name: "downstream" },
  ],
});
