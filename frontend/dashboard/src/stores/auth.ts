import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { apiClient } from "@/api/client";
import type { UserPublic } from "@/types/api";

const TOKEN_KEY = "dsm_jwt_token";
const USER_KEY = "dsm_user_info";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY));
  const rawUser = localStorage.getItem(USER_KEY);
  const user = ref<UserPublic | null>(rawUser ? (JSON.parse(rawUser) as UserPublic) : null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  const isAuthenticated = computed(() => Boolean(token.value));

  async function login(username: string, password: string): Promise<boolean> {
    loading.value = true;
    error.value = null;
    try {
      const resp = await apiClient.login(username, password);
      token.value = resp.access_token;
      user.value = resp.user;
      localStorage.setItem(TOKEN_KEY, resp.access_token);
      localStorage.setItem(USER_KEY, JSON.stringify(resp.user));
      return true;
    } catch (err) {
      error.value = err instanceof Error ? err.message : "Error de autenticación";
      return false;
    } finally {
      loading.value = false;
    }
  }

  function logout(): void {
    token.value = null;
    user.value = null;
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  return { token, user, loading, error, isAuthenticated, login, logout };
});
