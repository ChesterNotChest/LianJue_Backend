const DEFAULT_BACKEND_URL = 'http://localhost:5000';

const rawBackendUrl = import.meta.env.VITE_BACKEND_URL || DEFAULT_BACKEND_URL;

export const BACKEND_URL = rawBackendUrl.replace(/\/+$/, '');
export const USE_MOCK_API = String(import.meta.env.VITE_USE_MOCK_API || '').toLowerCase() === 'true';

export function buildUrl(path, query = {}) {
  const url = new URL(`${BACKEND_URL}${path.startsWith('/') ? path : `/${path}`}`);
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, value);
    }
  });
  return url.toString();
}

export async function apiRequest(path, options = {}) {
  const { method = 'GET', body, query } = options;
  const response = await fetch(buildUrl(path, query), {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  const text = await response.text();
  let payload = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = {
        success: false,
        error_message: text || response.statusText,
        error_code: 'invalid_json_response',
      };
    }
  }

  if (!response.ok && payload && typeof payload === 'object') {
    return payload;
  }

  return payload;
}

export function apiGet(path, query = {}) {
  return apiRequest(path, { method: 'GET', query });
}

export function apiPost(path, body = {}) {
  return apiRequest(path, { method: 'POST', body });
}

export async function fileToUploadPayload(file, extra = {}) {
  const bytes = await file.arrayBuffer();
  let binary = '';
  const chunkSize = 0x8000;
  const view = new Uint8Array(bytes);

  for (let index = 0; index < view.length; index += chunkSize) {
    binary += String.fromCharCode(...view.subarray(index, index + chunkSize));
  }

  return {
    file_name: file.name,
    file_bytes: btoa(binary),
    upload_time: extra.uploadTime ?? extra.upload_time ?? new Date().toISOString(),
    file_type: extra.fileType ?? extra.file_type ?? file.name.split('.').pop() ?? '',
  };
}
