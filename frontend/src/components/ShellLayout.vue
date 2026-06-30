<script setup>
import {
  BarChart3,
  ClipboardList,
  LogOut,
  Megaphone,
  MicVocal,
  Settings2,
  Sigma,
} from "@lucide/vue";
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const navItems = [
  { to: "/loop", label: "闭环练习", icon: MicVocal },
  { to: "/numsprint", label: "数字专项", icon: Sigma },
  { to: "/interpcue", label: "语料播放", icon: Megaphone },
  { to: "/promptforge", label: "提示词设置", icon: Settings2 },
  { to: "/feedbacklog", label: "反馈记录", icon: ClipboardList },
  { to: "/stats", label: "学习统计", icon: BarChart3 },
];

const title = computed(() => navItems.find((item) => route.path === item.to)?.label || "InterpLoop");

async function logout() {
  await auth.logout();
  router.push("/login");
}
</script>

<template>
  <div class="flex min-h-screen bg-slate-100">
    <aside class="flex w-60 shrink-0 flex-col bg-[#183a56] text-white">
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

    <main class="flex min-w-0 flex-1 flex-col">
      <header class="flex h-14 items-center justify-between border-b border-slate-200 bg-white px-7 shadow-sm">
        <h1 class="text-base font-semibold text-brand">{{ title }}</h1>
        <div class="text-xs text-slate-500">Vue3 + Flask + SQLite</div>
      </header>
      <section class="flex-1 overflow-y-auto p-6">
        <RouterView />
      </section>
    </main>
  </div>
</template>
