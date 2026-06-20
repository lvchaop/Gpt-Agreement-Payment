import { deleteJson, getJson, patchJson, postJson } from "./client";

export type Row = Record<string, unknown> & { id?: string };
export type JobCreated = { job_id: string; job_status: string };
export type AccountWorkJobResult = JobCreated & {
  work_count: number;
  concurrency: number;
  queued: number;
  running: number;
  succeeded: number;
  failed: number;
  cancelled: number;
};

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
    postJson<{ team_admin_session_id: string; admin_email: string; workspace_count: number; workspaces: Row[] }>(
      "/team-admin-sessions/import",
      body,
    ),
  teamAdminSessions: () => getJson<Row[]>("/team-admin-sessions"),
  workspaces: () => getJson<Row[]>("/team-workspaces"),
  importWorkspace: (body: Record<string, unknown>) =>
    postJson<{ team_workspace_id: string }>("/team-workspaces/import", body),
  memberships: (params: Record<string, string> = {}) => {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, value]) => value.trim() !== ""),
    ).toString();
    return getJson<Row[]>(`/memberships${query ? `?${query}` : ""}`);
  },
  membershipProbe: (body: Record<string, unknown>) =>
    postJson<JobCreated>("/memberships/probe-job", body),
  membershipInvite: (body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>("/memberships/invite-member-job", body),
  membershipAcceptInvite: (body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>("/memberships/accept-invite-job", body),
  batches: () => getJson<Row[]>("/workspace-join-batches"),
  batch: (id: string) => getJson<Row>(`/workspace-join-batches/${encodeURIComponent(id)}`),
  batchItems: (id: string) =>
    getJson<Row[]>(`/workspace-join-batches/${encodeURIComponent(id)}/items`),
  createBatch: (body: Record<string, unknown>) =>
    postJson<JobCreated>("/workspace-join-batches", body),
  createBatchFromCredentials: (body: Record<string, unknown>) =>
    postJson<{ batch_id: string }>("/workspace-join-batches/from-credentials", body),
  activateBatch: (id: string) =>
    postJson<JobCreated>(`/workspace-join-batches/${encodeURIComponent(id)}/activate`, {}),
  credentials: () => getJson<Row[]>("/codex-credentials"),
  buildCredentials: (body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>("/codex-credentials/build-job", body),
  heartbeatCredential: (id: string) =>
    postJson<JobCreated>(`/codex-credentials/${encodeURIComponent(id)}/heartbeat-job`, {}),
  heartbeatCredentials: (body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>("/codex-credentials/heartbeat-job", body),
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
  downstream: () => getJson<Row[]>("/downstream-push-records"),
};
