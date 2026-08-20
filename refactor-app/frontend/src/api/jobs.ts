import { getJson, postJson } from "./client";
import type { PagedResult, PageQuery } from "./types";
import { withQuery } from "./types";

export type Job = Record<string, unknown> & {
  id: string;
  type: string;
  job_status: string;
  created_at?: string;
  updated_at?: string;
};

export type JobRun = Record<string, unknown> & {
  id: string;
  job_id: string;
  run_status: string;
  error_code?: string;
};

export type JobStep = Record<string, unknown> & {
  id: string;
  name: string;
  step_status: string;
  error_code?: string;
};

export type JobEvent = Record<string, unknown> & {
  id: string;
  level: string;
  event_type: string;
  message: string;
};

export type WorkItem = Record<string, unknown> & {
  id: string;
  job_id: string;
  work_type: string;
  work_status: string;
};

export function listJobs(params: PageQuery = {}) {
  return getJson<PagedResult<Job>>(withQuery("/jobs", params));
}

export function getJob(jobId: string) {
  return getJson<Job>(`/jobs/${encodeURIComponent(jobId)}`);
}

export function cancelJob(jobId: string) {
  return postJson<Job>(`/jobs/${encodeURIComponent(jobId)}/cancel`, {});
}

export function retryJob(jobId: string) {
  return postJson<{
    job_id: string;
    job_status: string;
    run_id: string;
    attempt: number;
    retried_work_count: number;
  }>(`/jobs/${encodeURIComponent(jobId)}/retry`, {});
}

export function listRuns(jobId: string) {
  return getJson<JobRun[]>(`/jobs/${encodeURIComponent(jobId)}/runs`);
}

export function listWorkItems(jobId: string, params: PageQuery = {}) {
  return getJson<PagedResult<WorkItem>>(
    withQuery(`/jobs/${encodeURIComponent(jobId)}/work-items`, params),
  );
}

export function cancelWorkItem(workItemId: string) {
  return postJson<WorkItem>(`/work-items/${encodeURIComponent(workItemId)}/cancel`, {});
}

export function listSteps(runId: string) {
  return getJson<JobStep[]>(`/runs/${encodeURIComponent(runId)}/steps`);
}

export function listEvents(runId: string, params: PageQuery = {}) {
  return getJson<PagedResult<JobEvent>>(withQuery(`/runs/${encodeURIComponent(runId)}/events`, params));
}

export function getJobSummary(jobId: string) {
  return getJson<Record<string, unknown>>(`/jobs/${encodeURIComponent(jobId)}/summary`);
}

export function createJob(type: string, inputJson: Record<string, unknown>) {
  return postJson<{ job_id: string; job_status: string }>("/jobs", {
    type,
    input_json: inputJson,
    created_by: "ops-console",
  });
}
