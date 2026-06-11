import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';

import { ensureValidAccessToken, handleUnauthorizedResponse } from './authSession';

export const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
});

export const authApi = axios.create({
  baseURL: '/api',
  timeout: 10000,
});

export const agentApi = axios.create({
  baseURL: '/api/agent-harness',
  timeout: 30000,
});

export const orchestratorApi = axios.create({
  baseURL: '/api/agent-orchestrator',
  timeout: 30000,
});

const AUTH_ENDPOINTS = ['/auth/login', '/auth/register', '/auth/refresh'];

const requestPath = (url?: string) => {
  if (!url) return '';

  try {
    const parsed = new URL(url, typeof window === 'undefined' ? 'http://localhost' : window.location.origin);
    return parsed.pathname.replace(/^\/api/, '');
  } catch {
    return url.replace(/^\/api/, '');
  }
};

const isAuthEndpoint = (url?: string) => {
  const path = requestPath(url);
  return AUTH_ENDPOINTS.some((endpoint) => path === endpoint || path.startsWith(`${endpoint}/`));
};

type RetriableRequestConfig = InternalAxiosRequestConfig & {
  _retry?: boolean;
};

const attachAccessToken = async (config: InternalAxiosRequestConfig) => {
  const token = await ensureValidAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
};

const createUnauthorizedInterceptor = (client: typeof api) => async (error: AxiosError) => {
  const originalRequest = error.config as RetriableRequestConfig | undefined;
  if (
    error.response?.status === 401 &&
    originalRequest &&
    !originalRequest._retry &&
    !isAuthEndpoint(originalRequest.url)
  ) {
    originalRequest._retry = true;
    return handleUnauthorizedResponse(() => client(originalRequest));
  }
  return Promise.reject(error);
};

api.interceptors.request.use(
  async (config) => attachAccessToken(config),
  (error) => Promise.reject(error),
);

agentApi.interceptors.request.use(
  async (config) => attachAccessToken(config),
  (error) => Promise.reject(error),
);

orchestratorApi.interceptors.request.use(
  async (config) => attachAccessToken(config),
  (error) => Promise.reject(error),
);

api.interceptors.response.use(
  (response) => response,
  createUnauthorizedInterceptor(api),
);

agentApi.interceptors.response.use(
  (response) => response,
  createUnauthorizedInterceptor(agentApi),
);

orchestratorApi.interceptors.response.use(
  (response) => response,
  createUnauthorizedInterceptor(orchestratorApi),
);

export const billingApi = {
  listPlans: () => api.get<{ plans: import("./billing").SubscriptionPlan[] }>("/billing/plans"),
  getSubscription: () => api.get<{ subscription: import("./billing").SubscriptionSummary }>("/billing/subscription"),
  listOrders: (limit = 20) => api.get<{ orders: import("./billing").SubscriptionOrder[] }>("/billing/orders", { params: { limit } }),
  createCheckout: (planSlug: string) => api.post<{ order: import("./billing").SubscriptionOrder }>("/billing/checkout", { plan_slug: planSlug }),
  confirmCheckout: (orderId: string, paymentMethod: string) =>
    api.post<{ order: import("./billing").SubscriptionOrder }>(`/billing/checkout/${orderId}/confirm`, { payment_method: paymentMethod }),
  cancelCheckout: (orderId: string) => api.post<{ order: import("./billing").SubscriptionOrder }>(`/billing/checkout/${orderId}/cancel`),
};

export const adminBillingApi = {
  listPlans: () => api.get<{ plans: import("./billing").SubscriptionPlan[] }>("/admin/subscription-plans"),
  createPlan: (body: Record<string, unknown>) => api.post("/admin/subscription-plans", body),
  updatePlan: (id: string, body: Record<string, unknown>) => api.patch(`/admin/subscription-plans/${id}`, body),
  listUsers: (params: Record<string, string | number>) => api.get<{ users: import("./billing").AdminUserRow[] }>("/admin/users", { params }),
  getUser: (id: string) => api.get(`/admin/users/${id}`),
  patchUser: (id: string, body: Record<string, unknown>) => api.patch(`/admin/users/${id}`, body),
  getStats: () => api.get<import("./billing").SubscriptionStats>("/admin/subscription-stats"),
};
