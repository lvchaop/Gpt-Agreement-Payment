import { createRouter, createWebHistory } from "vue-router";

import AccountsView from "../views/AccountsView.vue";
import AutomationMonitorView from "../views/AutomationMonitorView.vue";
import AutomationSchedulerView from "../views/AutomationSchedulerView.vue";
import DashboardView from "../views/DashboardView.vue";
import DownstreamChannelsView from "../views/DownstreamChannelsView.vue";
import JobsView from "../views/JobsView.vue";
import JobTraceView from "../views/JobTraceView.vue";
import MailView from "../views/MailView.vue";
import MembershipsView from "../views/MembershipsView.vue";
import ProxyView from "../views/ProxyView.vue";
import ProtocolRegistrationView from "../views/ProtocolRegistrationView.vue";
import SpaceCredentialsView from "../views/SpaceCredentialsView.vue";
import SpacePushRecordsView from "../views/SpacePushRecordsView.vue";
import SpacesView from "../views/SpacesView.vue";

export const router = createRouter({
  history: createWebHistory("/ops/"),
  routes: [
    { path: "/", component: DashboardView, name: "dashboard" },
    { path: "/jobs", component: JobsView, name: "jobs" },
    { path: "/jobs/:jobId", component: JobTraceView, name: "job-trace" },
    { path: "/automation-scheduler", component: AutomationSchedulerView, name: "automation-scheduler" },
    { path: "/automation-monitor", component: AutomationMonitorView, name: "automation-monitor" },
    { path: "/protocol-registration", component: ProtocolRegistrationView, name: "protocol-registration" },
    { path: "/accounts", component: AccountsView, name: "accounts" },
    { path: "/spaces", component: SpacesView, name: "spaces" },
    { path: "/memberships", component: MembershipsView, name: "memberships" },
    { path: "/space-credentials", component: SpaceCredentialsView, name: "space-credentials" },
    { path: "/space-push-records", component: SpacePushRecordsView, name: "space-push-records" },
    { path: "/proxy", component: ProxyView, name: "proxy" },
    { path: "/mail", component: MailView, name: "mail" },
    { path: "/downstream-channels", component: DownstreamChannelsView, name: "downstream-channels" },
  ],
});
