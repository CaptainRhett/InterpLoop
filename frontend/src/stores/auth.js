import { defineStore } from "pinia";
import { api } from "../api";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    user: null,
    contexts: [],
    loaded: false,
    renewingGuest: false,
    guestRenewalError: "",
  }),
  getters: {
    isGuest: (state) => state.user?.role === "guest",
    isTeacher: (state) => ["teacher", "admin"].includes(state.user?.role),
    isAdmin: (state) => state.user?.role === "admin",
  },
  actions: {
    clearSession() {
      this.user = null;
      this.contexts = [];
      this.loaded = true;
      this.guestRenewalError = "";
    },
    async enterGuest() {
      const { data } = await api.post("/auth/guest");
      this.user = data.user;
      this.contexts = [];
      this.loaded = true;
    },
    async renewGuest() {
      if (!this.isGuest || this.renewingGuest) return;
      const key = this.user.guest_session_id;
      this.renewingGuest = true;
      this.guestRenewalError = "";
      try {
        const { data } = await api.post("/auth/guest/renew", {}, { timeout: 10000 });
        if (this.isGuest && this.user.guest_session_id === key && data.user?.guest_session_id === key) {
          this.updateGuestExpiry(data.user.guest_expires_at);
        }
      } catch (err) {
        if (this.isGuest && this.user.guest_session_id === key) {
          this.guestRenewalError = err.response?.data?.error || "续期失败，请检查网络后重试";
        }
        throw err;
      } finally {
        this.renewingGuest = false;
      }
    },
    updateGuestExpiry(expiresAt) {
      if (this.isGuest && Date.parse(expiresAt) > Date.parse(this.user.guest_expires_at)) {
        this.user.guest_expires_at = expiresAt;
      }
    },
    async loadMe() {
      const { data } = await api.get("/auth/me");
      this.user = data.user;
      this.contexts = data.contexts || [];
      this.loaded = true;
    },
    async login(payload) {
      const { data } = await api.post("/auth/login", payload);
      this.user = data.user;
      this.contexts = data.contexts || [];
      this.loaded = true;
    },
    async changePassword(payload) {
      const { data } = await api.post("/auth/change-password", payload);
      this.user = data.user;
    },
    async logout() {
      await api.post("/auth/logout");
      this.clearSession();
    },
  },
});
