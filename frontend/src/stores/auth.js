import { defineStore } from "pinia";
import { api } from "../api";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    user: null,
    loaded: false,
  }),
  getters: {
    isTeacher: (state) => state.user?.role === "teacher",
  },
  actions: {
    async loadMe() {
      const { data } = await api.get("/auth/me");
      this.user = data.user;
      this.loaded = true;
    },
    async studentLogin(payload) {
      const { data } = await api.post("/auth/student-login", payload);
      this.user = data.user;
      this.loaded = true;
    },
    async teacherLogin(payload) {
      const { data } = await api.post("/auth/teacher-login", payload);
      this.user = data.user;
      this.loaded = true;
    },
    async logout() {
      await api.post("/auth/logout");
      this.user = null;
    },
  },
});
