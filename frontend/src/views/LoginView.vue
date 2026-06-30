<script setup>
import { BookOpenCheck } from "@lucide/vue";
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();
const mode = ref("student");
const error = ref("");
const loading = ref(false);
const form = reactive({
  student_no: "",
  name: "",
  teacher_code: "",
});

async function submit() {
  error.value = "";
  loading.value = true;
  try {
    if (mode.value === "student") {
      await auth.studentLogin({ student_no: form.student_no, name: form.name });
    } else {
      await auth.teacherLogin({ teacher_code: form.teacher_code });
    }
    router.push("/loop");
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

      <div class="mb-5 grid grid-cols-2 rounded-md bg-slate-100 p-1 text-sm">
        <button class="rounded px-3 py-2" :class="mode === 'student' ? 'bg-white shadow-sm text-brand font-semibold' : 'text-slate-500'" @click="mode = 'student'">
          学生登录
        </button>
        <button class="rounded px-3 py-2" :class="mode === 'teacher' ? 'bg-white shadow-sm text-brand font-semibold' : 'text-slate-500'" @click="mode = 'teacher'">
          教师入口
        </button>
      </div>

      <form class="space-y-4" @submit.prevent="submit">
        <template v-if="mode === 'student'">
          <div>
            <label class="field-label">学号</label>
            <input v-model.trim="form.student_no" class="input" autocomplete="username" required />
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

        <p v-if="error" class="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{{ error }}</p>
        <button class="btn-primary w-full" :disabled="loading">
          {{ loading ? "登录中..." : "进入平台" }}
        </button>
      </form>
    </div>
  </div>
</template>
