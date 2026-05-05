import { RAW_LIST_ALL_JOBS_RESPONSE_BY_GRAPH_ID } from './mock_payloads';
import { USE_MOCK_API, apiGet, apiPost } from './client';

function cloneData(value) {
  return JSON.parse(JSON.stringify(value));
}

function parseJobListResponse(response) {
  const jobs = Array.isArray(response?.jobs) ? response.jobs : [];

  return jobs.map((job) => ({
    jobId: job.job_id,
    fileId: job.file_id,
    graphId: job.graph_id,
    graphName: job.graph_name,
    filePath: job.file_path,
    status: job.status,
    stage: job.stage,
    progressIndex: job.progress_index,
    endStage: job.end_stage,
  }));
}

function getJobTone(status) {
  if (status === 'failed') {
    return 'danger';
  }
  if (status === 'completed') {
    return 'success';
  }
  if (status === 'in_progress') {
    return 'warning';
  }
  return 'neutral';
}

function getJobLabel(job) {
  if (!job) {
    return '';
  }
  if (job.status === 'completed') {
    return 'completed';
  }
  if (job.status === 'failed') {
    return 'failed';
  }
  if (job.status === 'paused') {
    return 'paused';
  }
  if (job.status === 'pending') {
    return `pending · ${job.stage}`;
  }
  return `in_progress · ${job.stage} · ${job.progressIndex}`;
}

export async function listJobsRaw(graphId) {
  if (!USE_MOCK_API) {
    return apiGet('/api/job_list', { graph_id: graphId });
  }

  return cloneData(
    RAW_LIST_ALL_JOBS_RESPONSE_BY_GRAPH_ID[graphId] ?? {
      success: true,
      jobs: [],
      error_message: '',
      error_code: '',
    },
  );
}

export async function createJobRaw(payload = {}) {
  if (!USE_MOCK_API) {
    return apiPost('/api/job_create', {
      graph_id: payload.graphId ?? payload.graph_id,
      file_id: payload.fileId ?? payload.file_id,
      end_stage: payload.endStage ?? payload.end_stage,
    });
  }

  return {
    success: true,
    job: { job_id: Date.now() },
    request: payload,
    error_message: '',
    error_code: '',
  };
}

export async function createJob(payload = {}) {
  const response = await createJobRaw(payload);
  return {
    success: Boolean(response?.success),
    jobId: response?.job?.job_id ?? null,
    errorMessage: response?.error_message ?? '',
    errorCode: response?.error_code ?? '',
  };
}

export async function listJobs(graphId) {
  return parseJobListResponse(await listJobsRaw(graphId));
}

export { getJobLabel, getJobTone, parseJobListResponse };
