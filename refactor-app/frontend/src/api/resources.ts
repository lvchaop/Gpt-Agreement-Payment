import { deleteJson, getJson, patchJson, postDownload, postJson } from "./client";
import type { OptionItem, PagedResult, PageQuery, Row } from "./types";
import { withQuery } from "./types";

export type { Row } from "./types";
export type JobCreated = { job_id: string; job_status: string };
export type AccountWorkJobResult = JobCreated & {
  work_count: number;
  selected_count: number;
  queued: number;
  running: number;
  succeeded: number;
  failed: number;
  cancelled: number;
};
export type PersonalCodexAuthorizationJobResult = AccountWorkJobResult & {
  requested_count: number;
  selection_skipped_count: number;
  selection_skipped: Array<{ space_membership_id: string; reason: string }>;
};

export const resourcesApi = {
  overview: () => getJson<{ generated_at: string; metrics: Record<string, number>; recent_failed_jobs: Row[] }>("/ops/overview"),
  accountOptions: (q = "") => getJson<{ items: OptionItem[] }>(withQuery("/ops/options/accounts", { q })),
  spaceOptions: (q = "", spaceType = "", credentialType = "") =>
    getJson<{ items: OptionItem[] }>(withQuery("/ops/options/spaces", {
      q,
      space_type: spaceType,
      credential_type: credentialType,
    })),
  channelOptions: (q = "") => getJson<{ items: OptionItem[] }>(withQuery("/ops/options/channels", { q })),
  accounts: (params: PageQuery = {}) => getJson<PagedResult<Row>>(withQuery("/user-accounts", params)),
  accountAccessToken: (id: string) =>
    getJson<{ user_account_id: string; access_token: string }>(
      `/user-accounts/${encodeURIComponent(id)}/access-token`,
    ),
  backfillSessionRt: (body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>("/user-accounts/backfill-session-rt-job", body),
  backfillSession: (body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>("/user-accounts/backfill-session-job", body),
  backfillRt: (body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>("/user-accounts/backfill-rt-job", body),
  createProtocolRegistrationJob: (body: Record<string, unknown>) =>
    postJson<JobCreated>("/account-protocol-registration/jobs", body),
  createAccountEmailChangeJob: (body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>("/account-email-change/jobs", body),
  patchAccount: (id: string, body: Record<string, unknown>) =>
    patchJson(`/user-accounts/${encodeURIComponent(id)}`, body),
  deleteAccount: (id: string) =>
    deleteJson<{ user_account_id: string; deleted: boolean; deleted_proxy_bindings: number }>(
      `/user-accounts/${encodeURIComponent(id)}`,
    ),
  deleteAccounts: (ids: string[]) =>
    postJson<{
      requested_count: number;
      deleted_count: number;
      missing_count: number;
      deleted_proxy_bindings: number;
    }>("/user-accounts/delete-selected", { user_account_ids: ids }),
  importTeamAdminSession: (body: Record<string, unknown>) =>
    postJson<{ team_admin_session_id: string; admin_email: string; space_count: number; spaces: Row[] }>(
      "/team-admin-sessions/import",
      body,
    ),
  teamAdminSessions: () => getJson<Row[]>("/team-admin-sessions"),
  deleteTeamAdminSession: (id: string) =>
    deleteJson<Row>(`/team-admin-sessions/${encodeURIComponent(id)}`),
  spaces: (params: PageQuery = {}) => getJson<PagedResult<Row>>(withQuery("/spaces", params)),
  patchSpace: (id: string, body: Record<string, unknown>) =>
    patchJson<Row>(`/spaces/${encodeURIComponent(id)}`, body),
  syncRemoteSpaceMemberships: (id: string, body: Record<string, unknown> = {}) =>
    postJson<Row>(`/spaces/${encodeURIComponent(id)}/memberships/sync-remote`, body),
  expandSpaceSeats: (id: string, body: Record<string, unknown> = {}) =>
    postJson<AccountWorkJobResult>(`/spaces/${encodeURIComponent(id)}/seat-expansion-job`, body),
  spaceSessionOtpSummary: (id: string) =>
    getJson<Row>(`/spaces/${encodeURIComponent(id)}/session-otp/summary`),
  prepareSpaceSessionOtp: (id: string, body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>(
      `/spaces/${encodeURIComponent(id)}/session-otp/prepare-job`,
      body,
    ),
  submitSpaceSessionOtp: (id: string, body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>(
      `/spaces/${encodeURIComponent(id)}/session-otp/submit-job`,
      body,
    ),
  createBusinessAccessTokenCredentials: (body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>(
      "/space-credentials/business-access-token-job",
      body,
    ),
  memberships: (params: PageQuery = {}) => getJson<PagedResult<Row>>(withQuery("/memberships", params)),
  authorizePersonalCodexMemberships: (body: Record<string, unknown>) =>
    postJson<PersonalCodexAuthorizationJobResult>(
      "/memberships/personal-codex-authorize-job",
      body,
    ),
  credentials: (params: PageQuery = {}) => getJson<PagedResult<Row>>(withQuery("/space-credentials", params)),
  spacePushRecords: (params: PageQuery = {}) => getJson<PagedResult<Row>>(withQuery("/space-push-records", params)),
  manualSettleSpacePushRecords: (body: Record<string, unknown>) =>
    postJson<Row>("/space-push-records/manual-settle", body),
  exportUnpushedSpaceCredentials: (body: Record<string, unknown>) =>
    postDownload("/space-push-records/export-unpushed-sub2api", body),
  redownloadSpaceCredentials: (body: Record<string, unknown>) =>
    postDownload("/space-push-records/redownload-sub2api", body),
  buildBusinessAccessTokenCredentials: (body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>("/space-credentials/business-access-token-job", body),
  pushCredentials: (body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>("/space-credentials/push-job", body),
  pushPendingCredentials: (body: Record<string, unknown>) =>
    postJson<AccountWorkJobResult>("/space-credentials/push-pending-job", body),
  proxies: (params: PageQuery = {}) => getJson<PagedResult<Row>>(withQuery("/proxies", params)),
  refreshProxies: (body: Record<string, unknown>) =>
    postJson<JobCreated>("/proxies/refresh-webshare-job", body),
  bindProxy: (body: Record<string, unknown>) => postJson<JobCreated>("/proxies/bind-account-job", body),
  healthcheckProxy: (id: string) =>
    postJson<JobCreated>(`/proxies/${encodeURIComponent(id)}/healthcheck-job`, {}),
  mailLeases: (params: PageQuery = {}) => getJson<PagedResult<Row>>(withQuery("/mail-leases", params)),
  allocateMail: (body: Record<string, unknown>) => postJson<JobCreated>("/mail/allocate-job", body),
  pollOtp: (body: Record<string, unknown>) => postJson<JobCreated>("/mail/poll-otp-job", body),
  markMailUsed: (body: Record<string, unknown>) => postJson<JobCreated>("/mail/mark-used-job", body),
  markMailFailed: (body: Record<string, unknown>) => postJson<JobCreated>("/mail/mark-failed-job", body),
  releaseMail: (body: Record<string, unknown>) => postJson<JobCreated>("/mail/release-job", body),
  downstreamChannels: (params: PageQuery = {}) => getJson<PagedResult<Row>>(withQuery("/downstream-channels", params)),
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
  residentJobs: () => getJson<{ items: Row[] }>("/automation/monitor/jobs"),
  patchResidentJobSchedule: (id: string, body: Record<string, unknown>) =>
    patchJson<Row>(`/automation/schedules/${encodeURIComponent(id)}`, body),
  runResidentJobNow: (id: string, body: Record<string, unknown>) =>
    postJson<Row>(`/automation/schedules/${encodeURIComponent(id)}/run-now`, body),
};
