import { defineStore } from "pinia";
import { api } from "../api";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    user: null,
    contexts: [],
    loaded: false,
  }),
  getters: {
    isTeacher: (state) => ["teacher", "admin"].includes(state.user?.role),
    isAdmin: (state) => state.user?.role === "admin",
  },
  actions: {
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
      this.user = null;
      this.contexts = [];
    },
  },
});
