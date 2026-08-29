<script setup>
import { BookOpenCheck } from "@lucide/vue";
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();
const mode = ref("account");
const legacyEnabled = ref(false);
const error = ref("");
const loading = ref(false);
const form = reactive({
  login_id: "",
  password: "",
  student_no: "",
  name: "",
  teacher_code: "",
});

async function submit() {
  error.value = "";
  loading.value = true;
  try {
    if (mode.value === "account") {
      await auth.login({ login_id: form.login_id, password: form.password });
    } else if (mode.value === "student") {
      await auth.studentLogin({ student_no: form.student_no, name: form.name });
    } else {
      await auth.teacherLogin({ teacher_code: form.teacher_code });
    }
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

onMounted(async () => {
  try {
    const { data } = await api.get("/auth/login-config");
    legacyEnabled.value = data.legacy_login_enabled;
  } catch {
    legacyEnabled.value = false;
  }
});
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

      <div v-if="legacyEnabled" class="mb-5 grid grid-cols-3 rounded-md bg-slate-100 p-1 text-sm">
        <button class="rounded px-2 py-2" :class="mode === 'account' ? 'bg-white font-semibold text-brand shadow-sm' : 'text-slate-500'" @click="mode = 'account'">账号登录</button>
        <button class="rounded px-2 py-2" :class="mode === 'student' ? 'bg-white font-semibold text-brand shadow-sm' : 'text-slate-500'" @click="mode = 'student'">演示学生</button>
        <button class="rounded px-2 py-2" :class="mode === 'teacher' ? 'bg-white font-semibold text-brand shadow-sm' : 'text-slate-500'" @click="mode = 'teacher'">演示教师</button>
      </div>

      <form class="space-y-4" @submit.prevent="submit">
        <template v-if="mode === 'account'">
          <div>
            <label class="field-label">账号</label>
            <input v-model.trim="form.login_id" class="input" autocomplete="username" required />
          </div>
          <div>
            <label class="field-label">密码</label>
            <input v-model="form.password" class="input" type="password" autocomplete="current-password" required />
          </div>
        </template>
        <template v-else-if="mode === 'student'">
          <div>
            <label class="field-label">学号</label>
            <input v-model.trim="form.student_no" class="input" required />
          </div>
          <div>
            <label class="field-label">姓名</label>
            <input v-model.trim="form.name" class="input" required />
          </div>
        </template>
        <div v-else>
          <label class="field-label">教师码</label>
          <input v-model.trim="form.teacher_code" class="input" type="password" required />
        </div>

        <p v-if="mode === 'account'" class="text-xs leading-5 text-slate-500">首次使用初始密码登录后，系统会要求立即修改密码。</p>
        <p v-if="error" class="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{{ error }}</p>
        <button class="btn-primary w-full" :disabled="loading">{{ loading ? "登录中..." : "登录平台" }}</button>
      </form>
    </div>
  </div>
</template>
