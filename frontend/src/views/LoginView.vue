<script setup>
import { BookOpenCheck } from "@lucide/vue";
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();
const error = ref("");
const loading = ref(false);
const form = reactive({
  login_id: "",
  password: "",
});

async function submit() {
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
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-[#183a56] px-4">
    <div class="w-full max-w-md rounded-lg bg-white p-8 shadow-2xl">
      <div class="mb-7 text-center">
        <div class="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-lg bg-brand text-white">
          <BookOpenCheck class="h-8 w-8" />
        </div>
        <h1 class="text-2xl font-bold text-brand">InterpLoop</h1>
        <p class="mt-1 text-sm text-slate-500">自主口译实训与反馈平台</p>
      </div>

      <form class="space-y-4" @submit.prevent="submit">
        <div>
          <label class="field-label">账号</label>
          <input v-model.trim="form.login_id" class="input" autocomplete="username" required />
        </div>
        <div>
          <label class="field-label">密码</label>
          <input v-model="form.password" class="input" type="password" autocomplete="current-password" required />
        </div>

        <p class="text-xs leading-5 text-slate-500">首次使用初始密码登录后，系统会要求立即修改密码。</p>
        <p v-if="error" class="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{{ error }}</p>
        <button class="btn-primary w-full" :disabled="loading">{{ loading ? "登录中..." : "登录平台" }}</button>
      </form>
    </div>
  </div>
</template>
