import { apiGet, apiPost } from './client';
import { createJob, listJobs, parseJobListResponse } from './job_api';

function parseJobResponse(response) {
  const job = response?.job;
  if (!job) {
    return null;
  }

  return {
    jobId: job.job_id,
    fileId: job.file_id,
    graphId: job.graph_id,
    graphName: job.graph_name,
    filePath: job.file_path,
    status: job.status,
    stage: job.stage,
    progressIndex: job.progress_index,
    endStage: job.end_stage,
    errorMessage: job.error_message ?? '',
  };
}

function toMutationResult(response) {
  return {
    success: Boolean(response?.success),
    jobId: response?.job?.job_id ?? null,
    errorMessage: response?.error_message ?? '',
    errorCode: response?.error_code ?? '',
  };
}

export async function triggerKnowledgeBuild(payload = {}) {
  return createJob(payload);
}

export async function getJobDetailRaw(jobId) {
  return apiPost('/api/job_detail', { job_id: jobId });
}

export async function getJobDetail(jobId) {
  return parseJobResponse(await getJobDetailRaw(jobId));
}

export async function listKnowledgeBuildJobs(graphId) {
  return listJobs(graphId);
}

export async function listKnowledgeBuildJobsRaw(graphId) {
  return apiGet('/api/job_list', { graph_id: graphId });
}

export async function pauseJob(jobId) {
  return toMutationResult(await apiPost('/api/job_pause', { job_id: jobId }));
}

export async function resumeJob(jobId) {
  return toMutationResult(await apiPost('/api/job_resume', { job_id: jobId }));
}

export async function endJob(jobId) {
  return toMutationResult(await apiPost('/api/job_end', { job_id: jobId }));
}

export { parseJobListResponse, parseJobResponse };
