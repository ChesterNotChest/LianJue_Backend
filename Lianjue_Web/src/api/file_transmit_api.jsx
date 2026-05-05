import {
  RAW_LIST_ALL_FILES_BRIEF_INFO_RESPONSE_BY_GRAPH_ID,
  RAW_LIST_ALL_FILES_BRIEF_INFO_RESPONSE_BY_SYLLABUS_ID,
} from './mock_payloads';
import { USE_MOCK_API, apiPost, buildUrl, fileToUploadPayload } from './client';

function cloneData(value) {
  return JSON.parse(JSON.stringify(value));
}

function mergeFileResponses(sourceMap, idList = []) {
  const targetIds = idList.length ? idList : Object.keys(sourceMap).map((key) => Number(key));
  const responses = targetIds
    .map((id) => sourceMap[id])
    .filter(Boolean);

  return {
    success: responses.every((response) => response.success !== false),
    files: responses.flatMap((response) => response.files ?? []),
    error_message: responses.find((response) => response.error_message)?.error_message ?? '',
    error_code: responses.find((response) => response.error_code)?.error_code ?? '',
  };
}

function createMockFileDetailStore() {
  const store = {};
  const pushFiles = (responseMap) => {
    Object.values(responseMap ?? {}).forEach((response) => {
      (response?.files ?? []).forEach((file) => {
        store[file.file_id] = {
          success: true,
          file: {
            file_id: file.file_id,
            filename: file.filename,
            path: file.path,
            upload_time: file.upload_time ?? null,
          },
          error_message: '',
          error_code: '',
        };
      });
    });
  };

  pushFiles(RAW_LIST_ALL_FILES_BRIEF_INFO_RESPONSE_BY_GRAPH_ID);
  pushFiles(RAW_LIST_ALL_FILES_BRIEF_INFO_RESPONSE_BY_SYLLABUS_ID);
  return store;
}

let mockFileDetailResponseById = createMockFileDetailStore();

function parseFileListResponse(response) {
  const files = Array.isArray(response?.files) ? response.files : [];

  return files.map((file) => ({
    fileId: file.file_id,
    title: file.filename,
    path: file.path,
    source: file.source,
    weekIndexList: Array.isArray(file.week_index_list) ? file.week_index_list : [],
  }));
}

function parseFileDetailResponse(response) {
  const file = response?.file ?? null;
  if (!file) {
    return null;
  }

  return {
    fileId: file.file_id,
    title: file.filename,
    path: file.path,
    uploadTime: file.upload_time ?? null,
  };
}

function pickDownloadFilename(headers, fallbackName) {
  const contentDisposition = headers?.get?.('Content-Disposition') ?? '';
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }

  const plainMatch = contentDisposition.match(/filename=\"?([^\";]+)\"?/i);
  if (plainMatch?.[1]) {
    return plainMatch[1];
  }

  return fallbackName || 'download';
}

function triggerBrowserDownload(blob, filename) {
  const downloadUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = downloadUrl;
  anchor.download = filename || 'download';
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  window.setTimeout(() => window.URL.revokeObjectURL(downloadUrl), 0);
}

export async function listGraphFilesRaw(graphIdList = []) {
  if (!USE_MOCK_API) {
    return apiPost('/api/file_list_graph_files', { graph_id_list: graphIdList });
  }
  return cloneData(mergeFileResponses(RAW_LIST_ALL_FILES_BRIEF_INFO_RESPONSE_BY_GRAPH_ID, graphIdList));
}

export async function listSyllabusFilesRaw(syllabusIdList = []) {
  if (!USE_MOCK_API) {
    return apiPost('/api/file_list_syllabus_files', { syllabus_id_list: syllabusIdList });
  }
  return cloneData(mergeFileResponses(RAW_LIST_ALL_FILES_BRIEF_INFO_RESPONSE_BY_SYLLABUS_ID, syllabusIdList));
}

export async function listGraphFiles(graphIdList = []) {
  return parseFileListResponse(await listGraphFilesRaw(graphIdList));
}

export async function listSyllabusFiles(syllabusIdList = []) {
  return parseFileListResponse(await listSyllabusFilesRaw(syllabusIdList));
}

export async function getFileDetailRaw(fileId) {
  if (!USE_MOCK_API) {
    return apiPost('/api/file_detail', { file_id: fileId });
  }
  return cloneData(mockFileDetailResponseById[fileId] ?? {
    success: false,
    file: null,
    error_message: 'not_found',
    error_code: 'not_found',
  });
}

export async function getFileDetail(fileId) {
  return parseFileDetailResponse(await getFileDetailRaw(fileId));
}

export async function downloadFileRaw(fileId) {
  if (USE_MOCK_API) {
    const detail = parseFileDetailResponse(
      mockFileDetailResponseById[fileId] ?? {
        success: false,
        file: null,
        error_message: 'not_found',
        error_code: 'not_found',
      },
    );

    if (!detail) {
      return {
        success: false,
        blob: null,
        filename: null,
        error_message: 'not_found',
        error_code: 'not_found',
      };
    }

    const mockContent = [
      `Mock file download`,
      `file_id=${detail.fileId}`,
      `filename=${detail.title ?? ''}`,
      `path=${detail.path ?? ''}`,
    ].join('\n');

    return {
      success: true,
      blob: new Blob([mockContent], { type: 'text/plain;charset=utf-8' }),
      filename: detail.title || `file_${fileId}.txt`,
      error_message: '',
      error_code: '',
    };
  }

  const response = await fetch(buildUrl('/api/file_download', { file_id: fileId }));
  if (!response.ok) {
    const text = await response.text();
    let payload = {};
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      payload = {
        error_message: text || response.statusText,
        error_code: 'download_failed',
      };
    }

    return {
      success: false,
      blob: null,
      filename: null,
      error_message: payload.error_message ?? 'download_failed',
      error_code: payload.error_code ?? 'download_failed',
    };
  }

  const blob = await response.blob();
  return {
    success: true,
    blob,
    filename: pickDownloadFilename(response.headers, `file_${fileId}`),
    error_message: '',
    error_code: '',
  };
}

export async function downloadFile(fileId, fallbackTitle = '') {
  const result = await downloadFileRaw(fileId);
  if (!result.success || !result.blob) {
    return result;
  }

  triggerBrowserDownload(result.blob, result.filename || fallbackTitle || `file_${fileId}`);
  return result;
}

export async function uploadFile(payload = {}) {
  if (!USE_MOCK_API) {
    const file = payload.file ?? payload.files?.[0] ?? null;
    const request = file
      ? await fileToUploadPayload(file, payload)
      : {
          file_name: payload.fileName ?? payload.file_name,
          file_bytes: payload.fileBytes ?? payload.file_bytes,
          upload_time: payload.uploadTime ?? payload.upload_time,
          file_type: payload.fileType ?? payload.file_type,
        };
    return apiPost('/api/file_upload', request);
  }

  const file = payload.file ?? payload.files?.[0] ?? null;
  const fileId = 900 + Date.now();
  mockFileDetailResponseById[fileId] = {
    success: true,
    file: {
      file_id: fileId,
      filename: file?.name ?? payload.fileName ?? payload.file_name ?? `file_${fileId}`,
      path: file?.name ? `./pdf/${file.name}` : `./pdf/file_${fileId}`,
      upload_time: payload.uploadTime ?? payload.upload_time ?? null,
    },
    error_message: '',
    error_code: '',
  };

  return {
    success: true,
    file: {
      file_id: fileId,
    },
    request: payload,
    error_message: '',
    error_code: '',
  };
}

export { parseFileDetailResponse, parseFileListResponse };
