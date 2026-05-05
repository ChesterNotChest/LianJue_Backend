const AUTH_STORAGE_KEY = 'lianjue_auth';

function dispatchNavigation(pathname) {
  if (window.location.pathname === pathname) {
    return;
  }
  window.history.pushState({}, '', pathname);
  window.dispatchEvent(new Event('lianjue:navigate'));
}

export function getStoredAuth() {
  try {
    const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

export function getCurrentUserId() {
  const auth = getStoredAuth();
  const userId = auth?.user_id ?? auth?.userId ?? null;
  return userId == null || userId === '' ? null : Number(userId);
}

export function saveAuth(user) {
  if (!user || typeof user !== 'object') {
    return;
  }
  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({
    user_id: user.user_id ?? user.userId ?? null,
    user_name: user.user_name ?? user.userName ?? '',
    email: user.email ?? '',
  }));
}

export function clearAuth() {
  window.localStorage.removeItem(AUTH_STORAGE_KEY);
}

export function redirectToLogin() {
  dispatchNavigation('/login');
}

export function requireUserId(options = {}) {
  const candidate = options.userId ?? options.user_id ?? null;
  if (candidate != null && candidate !== '') {
    return Number(candidate);
  }

  const storedUserId = getCurrentUserId();
  if (storedUserId != null) {
    return storedUserId;
  }

  if (options.allowMockFallback) {
    return 7;
  }

  redirectToLogin();
  throw new Error('missing auth session');
}
