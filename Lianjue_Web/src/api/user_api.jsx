import { USE_MOCK_API, apiPost } from './client';
import { saveAuth } from './session';

function parseUserMutationResponse(response) {
  return {
    success: Boolean(response?.success),
    user: response?.user ?? null,
    errorMessage: response?.error_message ?? '',
    errorCode: response?.error_code ?? '',
  };
}

export async function loginUser(payload = {}) {
  if (USE_MOCK_API) {
    const user = {
      user_id: 7,
      user_name: payload.userName ?? payload.user_name ?? 'demo',
      email: 'demo@example.com',
    };
    saveAuth(user);
    return {
      success: true,
      user,
      errorMessage: '',
      errorCode: '',
    };
  }

  const parsed = parseUserMutationResponse(await apiPost('/api/user_login', {
    user_name: payload.userName ?? payload.user_name,
    password: payload.password,
  }));
  if (parsed.success && parsed.user) {
    saveAuth(parsed.user);
  }
  return parsed;
}

export async function registerUser(payload = {}) {
  if (USE_MOCK_API) {
    const user = {
      user_id: 7,
      user_name: payload.userName ?? payload.user_name ?? 'demo',
      email: payload.email ?? 'demo@example.com',
    };
    saveAuth(user);
    return {
      success: true,
      user,
      errorMessage: '',
      errorCode: '',
    };
  }

  const parsed = parseUserMutationResponse(await apiPost('/api/user_register', {
    user_name: payload.userName ?? payload.user_name,
    password: payload.password,
    email: payload.email,
  }));
  if (parsed.success && parsed.user) {
    saveAuth(parsed.user);
  }
  return parsed;
}
