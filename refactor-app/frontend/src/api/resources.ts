import { deleteJson, getJson, patchJson, postJson } from "./client";

export type Row = Record<string, unknown> & { id?: string };
export type JobCreated = { job_id: string; job_status: string };
export type AccountWorkJobResult = JobCreated & {
  work_count: number;
  queued: number;
  running: number;
  succeeded: number;
  failed: number;
  cancelled: number;
};

async function listItems(path: string): Promise<Row[]> {
  const result = await getJson<Row[] | { items: Row[] }>(path);
  return Array.isArray(result) ? result : result.items;
}

export const resourcesApi = {
  accounts: () => getJson<Row[]>("/user-accounts"),
  backfillSessionRt: (body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>("/user-accounts/backfill-session-rt-job", body),
  backfillSession: (body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>("/user-accounts/backfill-session-job", body),
  backfillRt: (body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>("/user-accounts/backfill-rt-job", body),
  patchAccount: (id: string, body: Record<string, unknown>) =>
    patchJson(`/user-accounts/${encodeURIComponent(id)}`, body),
  deleteAccount: (id: string) =>
    deleteJson<{ user_account_id: string; deleted: boolean; deleted_proxy_bindings: number }>(
      `/user-accounts/${encodeURIComponent(id)}`,
    ),
  importTeamAdminSession: (body: Record<string, unknown>) =>
    postJson<{ team_admin_session_id: string; admin_email: string; space_count: number; spaces: Row[] }>(
      "/team-admin-sessions/import",
      body,
    ),
  teamAdminSessions: () => getJson<Row[]>("/team-admin-sessions"),
  deleteTeamAdminSession: (id: string) =>
    deleteJson<Row>(`/team-admin-sessions/${encodeURIComponent(id)}`),
  spaces: () => listItems("/spaces"),
  syncRemoteSpaceMemberships: (id: string, body: Record<string, unknown> = {}) =>
    postJson<Row>(`/spaces/${encodeURIComponent(id)}/memberships/sync-remote`, body),
  createBusinessAccessTokenCredentials: (body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>(
      "/space-credentials/business-access-token-job",
      body,
    ),
  memberships: (params: Record<string, string> = {}) => {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, value]) => value.trim() !== ""),
    ).toString();
    return getJson<Row[]>(`/memberships${query ? `?${query}` : ""}`);
  },
  credentials: () => listItems("/space-credentials"),
  buildBusinessAccessTokenCredentials: (body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>("/space-credentials/business-access-token-job", body),
  pushCredentials: (body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>("/space-credentials/push-job", body),
  pushPendingCredentials: (body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>("/space-credentials/push-pending-job", body),
  proxies: () => getJson<Row[]>("/proxies"),
  refreshProxies: (body: Record<string, unknown>) =>
    postJson<JobCreated>("/proxies/refresh-webshare-job", body),
  bindProxy: (body: Record<string, unknown>) => postJson<JobCreated>("/proxies/bind-account-job", body),
  healthcheckProxy: (id: string) =>
    postJson<JobCreated & { alive: boolean; released_bind_count: number }>(
      `/proxies/${encodeURIComponent(id)}/healthcheck-job`,
      {},
    ),
  mailLeases: () => getJson<Row[]>("/mail-leases"),
  allocateMail: (body: Record<string, unknown>) => postJson<JobCreated>("/mail/allocate-job", body),
  pollOtp: (body: Record<string, unknown>) => postJson<JobCreated>("/mail/poll-otp-job", body),
  markMailUsed: (body: Record<string, unknown>) => postJson<JobCreated>("/mail/mark-used-job", body),
  markMailFailed: (body: Record<string, unknown>) => postJson<JobCreated>("/mail/mark-failed-job", body),
  releaseMail: (body: Record<string, unknown>) => postJson<JobCreated>("/mail/release-job", body),
  downstreamChannels: () => getJson<Row[]>("/downstream-channels"),
  createDownstreamChannel: (body: Record<string, unknown>) =>
    postJson<Row>("/downstream-channels", body),
  patchDownstreamChannel: (id: string, body: Record<string, unknown>) =>
    patchJson<Row>(`/downstream-channels/${encodeURIComponent(id)}`, body),
  addDownstreamChannelBalance: (id: string, body: Record<string, unknown>) =>
    postJson<Row>(
      `/downstream-channels/${encodeURIComponent(id)}/credential-type-balances/${encodeURIComponent(String(body.credential_type || ""))}/add-balance`,
      body,
    ),
  patchDownstreamChannelCredentialTypeBalance: (
    id: string,
    credentialType: string,
    body: Record<string, unknown>,
  ) =>
    patchJson<Row>(
      `/downstream-channels/${encodeURIComponent(id)}/credential-type-balances/${encodeURIComponent(credentialType)}`,
      body,
    ),
  deleteDownstreamChannel: (id: string) =>
    deleteJson<Row>(`/downstream-channels/${encodeURIComponent(id)}`),
  spaceRecycleSweep: (body: Record<string, unknown>) =>
    postJson<Row>("/spaces/recycle-sweep-job", body),
  automationSchedules: () => getJson<Row[]>("/automation/schedules"),
  patchAutomationSchedule: (id: string, body: Record<string, unknown>) =>
    patchJson<Row>(`/automation/schedules/${encodeURIComponent(id)}`, body),
  runAutomationScheduleNow: (id: string) =>
    postJson<Row>(`/automation/schedules/${encodeURIComponent(id)}/run-now`, {}),
  automationMonitorJobs: () => getJson<{ items: Row[] }>("/automation/monitor/jobs"),
  automationMonitorJobRuns: (params: Record<string, string | number> = {}) => {
    const query = new URLSearchParams(
      Object.entries(params)
        .filter(([, value]) => String(value).trim() !== "")
        .map(([key, value]) => [key, String(value)]),
    ).toString();
    return getJson<{ items: Row[]; limit: number }>(
      `/automation/monitor/job-runs${query ? `?${query}` : ""}`,
    );
  },
  automationMonitorConsole: (params: Record<string, string | number> = {}) => {
    const query = new URLSearchParams(
      Object.entries(params)
        .filter(([, value]) => String(value).trim() !== "")
        .map(([key, value]) => [key, String(value)]),
    ).toString();
    return getJson<{ items: Row[]; truncated: boolean; returned_count: number; returned_bytes: number; max_bytes: number }>(
      `/automation/monitor/job-console${query ? `?${query}` : ""}`,
    );
  },
};
