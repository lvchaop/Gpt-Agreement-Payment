import { getJson, postJson } from "./client";

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

export function listJobs() {
  return getJson<Job[]>("/jobs");
}

export function getJob(jobId: string) {
  return getJson<Job>(`/jobs/${encodeURIComponent(jobId)}`);
}

export function cancelJob(jobId: string) {
  return postJson<Job>(`/jobs/${encodeURIComponent(jobId)}/cancel`, {});
}

export function listRuns(jobId: string) {
  return getJson<JobRun[]>(`/jobs/${encodeURIComponent(jobId)}/runs`);
}

export function listWorkItems(jobId: string) {
  return getJson<WorkItem[]>(`/jobs/${encodeURIComponent(jobId)}/work-items`);
}

export function cancelWorkItem(workItemId: string) {
  return postJson<WorkItem>(`/work-items/${encodeURIComponent(workItemId)}/cancel`, {});
}

export function listSteps(runId: string) {
  return getJson<JobStep[]>(`/runs/${encodeURIComponent(runId)}/steps`);
}

export function listEvents(runId: string) {
  return getJson<JobEvent[]>(`/runs/${encodeURIComponent(runId)}/events`);
}

export function createJob(type: string, inputJson: Record<string, unknown>) {
  return postJson<{ job_id: string; job_status: string }>("/jobs", {
    type,
    input_json: inputJson,
    created_by: "ops-console",
  });
}
