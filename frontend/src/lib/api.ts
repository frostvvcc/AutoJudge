const API_BASE = '/api/v1';

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const AUTH_PATHS = ['/auth/login', '/auth/register', '/auth/refresh'];

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('access_token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401 && !AUTH_PATHS.some((p) => path.startsWith(p))) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      headers['Authorization'] = `Bearer ${localStorage.getItem('access_token')}`;
      const retry = await fetch(`${API_BASE}${path}`, { ...options, headers });
      if (!retry.ok) {
        const err = await retry.json().catch(() => ({ detail: '请求失败' }));
        throw new ApiError(retry.status, err.detail || '请求失败');
      }
      return retry.json();
    }
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    window.location.href = '/login';
    throw new ApiError(401, '登录已过期');
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '请求失败' }));
    throw new ApiError(res.status, err.detail || '请求失败');
  }

  return res.json();
}

async function tryRefreshToken(): Promise<boolean> {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) return false;

  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

// ---------- Auth ----------

export interface UserInfo {
  uid: string;
  username: string;
  email: string;
  avatar_url: string | null;
  created_at: string;
  debate_count: number;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  user: UserInfo;
}

export async function register(
  username: string,
  email: string,
  password: string,
): Promise<TokenResponse> {
  return request<TokenResponse>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, email, password }),
  });
}

export async function login(loginStr: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ login: loginStr, password }),
  });
}

export async function getProfile(): Promise<UserInfo> {
  return request<UserInfo>('/auth/me');
}

export async function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  await request('/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  });
}

export async function updateProfile(username: string): Promise<void> {
  await request('/auth/me', {
    method: 'PUT',
    body: JSON.stringify({ username }),
  });
}

// ---------- History ----------

export interface SessionBrief {
  sid: string;
  task: string;
  language: string;
  status: string;
  converged: boolean;
  confidence: number;
  total_rounds: number;
  total_tokens: number;
  cost_usd: number;
  created_at: string;
  finished_at: string | null;
}

export interface PaginatedHistory {
  items: SessionBrief[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface SessionMessage {
  agent: string;
  content: string;
  round: number;
  code: string | null;
  structured_json: Record<string, unknown> | null;
}

export interface SessionDetail {
  sid: string;
  task: string;
  language: string;
  framework: string | null;
  config_json: Record<string, unknown>;
  status: string;
  result_code: string | null;
  confidence: number;
  converged: boolean;
  convergence_reason: string | null;
  summary_json: Record<string, unknown> | null;
  risk_json: Record<string, unknown> | null;
  metrics_json: Record<string, unknown> | null;
  quality_report_json: Record<string, unknown> | null;
  total_rounds: number;
  total_tokens: number;
  total_latency_ms: number;
  cost_usd: number;
  created_at: string;
  finished_at: string | null;
  messages: SessionMessage[];
}

export interface StatsOut {
  total_sessions: number;
  total_tokens: number;
  total_cost_usd: number;
  languages: Record<string, number>;
  avg_confidence: number;
  converge_rate: number;
}

export async function listHistory(params?: {
  page?: number;
  page_size?: number;
  language?: string;
  search?: string;
}): Promise<PaginatedHistory> {
  const qs = new URLSearchParams();
  if (params?.page) qs.set('page', String(params.page));
  if (params?.page_size) qs.set('page_size', String(params.page_size));
  if (params?.language) qs.set('language', params.language);
  if (params?.search) qs.set('search', params.search);
  const query = qs.toString();
  return request<PaginatedHistory>(`/history${query ? '?' + query : ''}`);
}

export async function getSessionDetail(sid: string): Promise<SessionDetail> {
  return request<SessionDetail>(`/history/${sid}`);
}

export async function deleteSession(sid: string): Promise<void> {
  await request(`/history/${sid}`, { method: 'DELETE' });
}

export async function getStats(): Promise<StatsOut> {
  return request<StatsOut>('/history/stats');
}
