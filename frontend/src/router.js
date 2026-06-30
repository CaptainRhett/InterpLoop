import { createRouter, createWebHistory } from "vue-router";

import ShellLayout from "./components/ShellLayout.vue";
import FeedbackLogView from "./views/FeedbackLogView.vue";
import InterpCueView from "./views/InterpCueView.vue";
import LoginView from "./views/LoginView.vue";
import LoopPracticeView from "./views/LoopPracticeView.vue";
import NumSprintView from "./views/NumSprintView.vue";
import PromptForgeView from "./views/PromptForgeView.vue";
import StatsView from "./views/StatsView.vue";
import { useAuthStore } from "./stores/auth";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", name: "login", component: LoginView },
    {
      path: "/",
      component: ShellLayout,
      children: [
        { path: "", redirect: "/loop" },
        { path: "loop", name: "loop", component: LoopPracticeView },
        { path: "numsprint", name: "numsprint", component: NumSprintView },
        { path: "interpcue", name: "interpcue", component: InterpCueView },
        { path: "promptforge", name: "promptforge", component: PromptForgeView },
        { path: "feedbacklog", name: "feedbacklog", component: FeedbackLogView },
        { path: "stats", name: "stats", component: StatsView },
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
  if (to.name === "login" && auth.user) return "/loop";
  return true;
});

export default router;
