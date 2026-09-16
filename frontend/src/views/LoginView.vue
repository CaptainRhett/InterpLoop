<script setup>
import { BookOpenCheck, Eye, EyeOff } from "@lucide/vue";
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const error = ref("");
const loading = ref(false);
const showPassword = ref(false);
const guestLoading = ref(false);
const form = reactive({
  login_id: "",
  password: "",
});

async function submit() {
  if (loading.value || guestLoading.value) return;
  error.value = "";
  loading.value = true;
  try {
    await auth.login({ login_id: form.login_id, password: form.password });
    if (auth.user?.must_change_password) router.push("/account");
    else if (auth.user?.role === "admin") router.push("/admin");
    else if (auth.user?.role === "teacher") router.push("/stats");
    else router.push("/loop");
  } catch (err) {
    error.value = err.response?.data?.error || "登录失败";
  } finally {
    loading.value = false;
  }
}

async function enterGuest() {
  if (loading.value || guestLoading.value) return;
  error.value = "";
  guestLoading.value = true;
  try {
    await auth.enterGuest();
    await router.push("/loop");
  } catch (err) {
    error.value = err.response?.data?.error || "暂时无法进入游客试用，请重试";
  } finally {
    guestLoading.value = false;
  }
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-[#183a56] px-4">
    <div class="w-full max-w-md rounded-lg bg-white p-8 shadow-2xl">
      <div class="mb-7 text-center">
        <div class="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-lg bg-brand text-white">
          <BookOpenCheck class="h-8 w-8" />
        </div>
        <h1 class="text-2xl font-bold text-brand">InterpLoop</h1>
        <p class="mt-1 text-sm text-slate-500">口译智环InterpLoop</p>
      </div>

      <p v-if="route.query.guest === 'expired'" class="mb-4 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">游客会话已结束，试用数据已失效。你可以重新试用或登录账号。</p>
      <form class="space-y-4" @submit.prevent="submit">
        <div>
          <label class="field-label">账号</label>
          <input v-model.trim="form.login_id" class="input" autocomplete="username" required />
        </div>
        <div>
          <label for="login-password" class="field-label">密码</label>
          <div class="relative">
            <input id="login-password" v-model="form.password" class="input pr-12" :type="showPassword ? 'text' : 'password'" autocomplete="current-password" required />
            <button
              type="button"
              class="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-md text-slate-500 hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              :aria-label="showPassword ? '隐藏密码' : '显示密码'"
              :title="showPassword ? '隐藏密码' : '显示密码'"
              aria-controls="login-password"
              @click="showPassword = !showPassword"
            >
              <EyeOff v-if="showPassword" class="h-5 w-5" aria-hidden="true" />
              <Eye v-else class="h-5 w-5" aria-hidden="true" />
            </button>
          </div>
        </div>

        <p class="text-xs leading-5 text-slate-500">首次使用初始密码登录后，系统会要求立即修改密码。</p>
        <p v-if="error" class="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{{ error }}</p>
        <button class="btn-primary w-full" :disabled="loading || guestLoading">{{ loading ? "登录中..." : "登录平台" }}</button>
      </form>
      <div class="mt-5 space-y-2 border-t border-slate-200 pt-5 text-center">
        <button type="button" class="btn-secondary w-full" :disabled="loading || guestLoading" @click="enterGuest">{{ guestLoading ? "正在进入…" : "游客试用，无需登录" }}</button>
        <p class="text-xs leading-5 text-slate-500">试用全部学习功能。数据仅在本次会话内保留，退出或到期后清理。</p>
      </div>
    </div>
  </div>
</template>
