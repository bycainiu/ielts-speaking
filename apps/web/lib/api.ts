import axios from 'axios';
import { useAuthStore } from '../store/authStore';

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

const redirectToLogin = () => {
  if (typeof window === 'undefined') return;
  if (window.location.pathname === '/login' || window.location.pathname === '/register') return;
  window.location.href = '/login';
};

// Request interceptor to add the bearer token
api.interceptors.request.use(
  (config) => {
    const token = useAuthStore.getState().accessToken;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

agentApi.interceptors.request.use(
  (config) => {
    const token = useAuthStore.getState().accessToken;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

agentApi.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && originalRequest && !originalRequest._retry && !isAuthEndpoint(originalRequest.url)) {
      originalRequest._retry = true;
      try {
        const refreshToken = useAuthStore.getState().refreshToken;
        if (!refreshToken) {
          throw new Error('No refresh token available');
        }

        const res = await axios.post('/api/auth/refresh', { refresh_token: refreshToken });
        const { access_token, refresh_token } = res.data;

        useAuthStore.getState().setTokens(access_token, refresh_token);
        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        return agentApi(originalRequest);
      } catch (refreshError) {
        useAuthStore.getState().logout();
        redirectToLogin();
        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  }
);

// Response interceptor to handle 401s and token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && originalRequest && !originalRequest._retry && !isAuthEndpoint(originalRequest.url)) {
      originalRequest._retry = true;
      try {
        const refreshToken = useAuthStore.getState().refreshToken;
        if (!refreshToken) {
          throw new Error('No refresh token available');
        }

        const res = await axios.post('/api/auth/refresh', { refresh_token: refreshToken });
        const { access_token, refresh_token } = res.data;

        useAuthStore.getState().setTokens(access_token, refresh_token);

        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        return api(originalRequest);
      } catch (refreshError) {
        useAuthStore.getState().logout();
        redirectToLogin();
        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  }
);
