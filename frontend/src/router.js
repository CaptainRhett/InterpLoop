import { createRouter, createWebHistory } from "vue-router";

import ShellLayout from "./components/ShellLayout.vue";
import AccountView from "./views/AccountView.vue";
import AdminView from "./views/AdminView.vue";
import FeedbackLogView from "./views/FeedbackLogView.vue";
import InterpCueView from "./views/InterpCueView.vue";
import LoginView from "./views/LoginView.vue";
import LoopPracticeView from "./views/LoopPracticeView.vue";
import NumSprintView from "./views/NumSprintView.vue";
import PracticeDetailView from "./views/PracticeDetailView.vue";
import PromptForgeView from "./views/PromptForgeView.vue";
import StatsView from "./views/StatsView.vue";
import { useAuthStore } from "./stores/auth";
import ChatAgent from "./views/ChatAgent.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", name: "login", component: LoginView },
    {
      path: "/",
      component: ShellLayout,
      children: [
        { path: "", redirect: "/stats" },
        { path: "loop", name: "loop", component: LoopPracticeView },
        { path: "numsprint", name: "numsprint", component: NumSprintView },
        { path: "interpcue", name: "interpcue", component: InterpCueView },
        { path: "promptforge", name: "promptforge", component: PromptForgeView },
        { path: "feedbacklog", name: "feedbacklog", component: FeedbackLogView },
        { path: "stats", name: "stats", component: StatsView },
        { path: "practices/:id", name: "practice-detail", component: PracticeDetailView },
        { path: "account", name: "account", component: AccountView },
        { path: "admin", name: "admin", component: AdminView, meta: { requiresAdmin: true } },
        { path: "chat", name: "chat", component: ChatAgent },
      ],
    },
  ],
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (!auth.loaded) {
    try {
      await auth.loadMe();
    } catch {
      auth.loaded = true;
    }
  }
  if (to.name !== "login" && !auth.user) return "/login";
  if (to.name === "login" && auth.user) {
    if (auth.user.must_change_password) return "/account";
    if (auth.isAdmin) return "/admin";
    return ["student", "guest"].includes(auth.user.role) ? "/loop" : "/stats";
  }
  if (auth.user?.must_change_password && to.name !== "account") return "/account";
  if (to.meta.requiresAdmin && !auth.isAdmin) return "/stats";
  if (to.name === "account" && auth.isGuest) return "/loop";
  if (to.name === "loop" && !["student", "guest"].includes(auth.user?.role)) return "/stats";
  return true;
});

export default router;
