<script setup>
import {
  BarChart3,
  ClipboardList,
  LogOut,
  Megaphone,
  MicVocal,
  Settings2,
  Sigma,
  ShieldCheck,
  UserRoundCog,
} from "@lucide/vue";
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const navItems = computed(() => {
  const items = [];
  if (auth.user?.role === "student") items.push({ to: "/loop", label: "闭环练习", icon: MicVocal });
  items.push(
    { to: "/numsprint", label: "数字专项", icon: Sigma },
    { to: "/interpcue", label: "语料播放", icon: Megaphone },
    { to: "/promptforge", label: "提示词设置", icon: Settings2 },
    { to: "/feedbacklog", label: "反馈记录", icon: ClipboardList },
    { to: "/stats", label: "学习统计", icon: BarChart3 },
    { to: "/chat", label: "AI 学习助手", icon: Sparkles },
  );
  if (auth.isAdmin) items.push({ to: "/admin", label: "账号与权限", icon: ShieldCheck });
  items.push({ to: "/account", label: "我的账号", icon: UserRoundCog });
  return items;
});

const title = computed(() => {
  if (route.name === "practice-detail") return "练习档案详情";
  return navItems.value.find((item) => route.path === item.to)?.label || "InterpLoop";
});

async function logout() {
  await auth.logout();
  router.push("/login");
}
</script>

<template>
  <div class="min-h-screen bg-slate-100">
    <aside class="fixed inset-y-0 left-0 z-40 flex w-60 flex-col bg-[#183a56] text-white">
      <div class="border-b border-white/10 px-5 py-5">
        <div class="text-xl font-bold">InterpLoop</div>
        <div class="mt-1 text-xs text-white/55">自主口译实训与反馈平台</div>
      </div>

      <div class="border-b border-white/10 px-5 py-4 text-sm">
        <div class="font-semibold">{{ auth.user?.name || "未登录" }}</div>
        <div class="mt-1 text-xs text-white/55">
          {{ auth.user?.role === "teacher" ? "教师端" : `学号：${auth.user?.student_no || "-"}` }}
        </div>
      </div>

      <nav class="flex-1 overflow-y-auto py-3">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="mx-2 mb-1 flex items-center gap-3 rounded-md px-3 py-3 text-sm text-white/72 transition hover:bg-white/10 hover:text-white"
          :class="{ 'bg-white/15 text-white shadow-inner': route.path === item.to }"
        >
          <component :is="item.icon" class="h-5 w-5" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <button class="flex items-center gap-3 border-t border-white/10 px-5 py-4 text-sm text-white/70 hover:text-white" @click="logout">
        <LogOut class="h-4 w-4" />
        退出登录
      </button>
    </aside>

    <main class="ml-60 min-h-screen min-w-0 pt-14">
      <header class="fixed left-60 right-0 top-0 z-30 flex h-14 items-center justify-between border-b border-slate-200 bg-white px-7 shadow-sm">
        <h1 class="text-base font-semibold text-brand">{{ title }}</h1>
        <div class="flex items-center gap-3">
          <div class="hidden text-xs text-slate-500 sm:block">{{ auth.user?.name || "未登录" }}</div>
          <button class="btn-secondary px-3 py-2 text-xs" @click="logout">
            <LogOut class="h-4 w-4" />退出登录
          </button>
        </div>
      </header>
      <section class="p-6">
        <RouterView />
      </section>
    </main>
  </div>
</template>
