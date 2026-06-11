import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import { configureAuthSession, ensureValidAccessToken, handleSessionExpired } from '../lib/authSession';
import { api } from '../lib/api';

interface User {
  id: string;
  email: string;
  display_name: string;
  role?: string;
  status?: string;
  created_at?: string;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  tokenExpiresAt: string | null;
  isAuthenticated: boolean;
  hasHydrated: boolean;
  setTokens: (accessToken: string, refreshToken: string, expiresAt?: string | null) => void;
  setUser: (user: User) => void;
  markHydrated: () => void;
  logout: () => void;
  fetchUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      tokenExpiresAt: null,
      isAuthenticated: false,
      hasHydrated: false,

      setTokens: (accessToken, refreshToken, expiresAt = null) => {
        set({ accessToken, refreshToken, tokenExpiresAt: expiresAt, isAuthenticated: true });
      },

      setUser: (user) => {
        set({ user });
      },

      markHydrated: () => {
        set((state) => ({ hasHydrated: true, isAuthenticated: Boolean(state.accessToken) }));
      },

      logout: () => {
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          tokenExpiresAt: null,
          isAuthenticated: false,
        });
      },

      fetchUser: async () => {
        try {
          const token = await ensureValidAccessToken();
          if (!token) {
            handleSessionExpired();
            return;
          }

          const res = await api.get('/me');
          set({ user: res.data.user, isAuthenticated: true });
        } catch (error) {
          console.error("Failed to fetch user", error);
          handleSessionExpired();
        }
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        tokenExpiresAt: state.tokenExpiresAt,
        isAuthenticated: Boolean(state.accessToken),
      }),
      onRehydrateStorage: () => (state) => {
        state?.markHydrated();
      },
    }
  )
);

configureAuthSession({
  getAccessToken: () => useAuthStore.getState().accessToken,
  getRefreshToken: () => useAuthStore.getState().refreshToken,
  getTokenExpiresAt: () => useAuthStore.getState().tokenExpiresAt,
  setTokens: (accessToken, refreshToken, expiresAt = null) => {
    useAuthStore.getState().setTokens(accessToken, refreshToken, expiresAt);
  },
  logout: () => {
    useAuthStore.getState().logout();
  },
});
