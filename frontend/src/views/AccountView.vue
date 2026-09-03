<script setup>
import { KeyRound, ShieldCheck } from "@lucide/vue";
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const router = useRouter();
const form = reactive({ current_password: "", new_password: "", confirm_password: "" });
const error = ref("");
const message = ref("");
const saving = ref(false);

async function changePassword() {
  error.value = "";
  message.value = "";
  if (form.new_password !== form.confirm_password) {
    error.value = "两次输入的新密码不一致";
    return;
  }
  saving.value = true;
  try {
    await auth.changePassword({
      current_password: form.current_password,
      new_password: form.new_password,
    });
    Object.assign(form, { current_password: "", new_password: "", confirm_password: "" });
    message.value = "密码修改成功";
    if (auth.user.role === "admin") router.push("/admin");
    else if (auth.user.role === "teacher") router.push("/stats");
    else router.push("/loop");
  } catch (err) {
    error.value = err.response?.data?.error || "密码修改失败";
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="grid gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
    <section class="panel">
      <div class="flex items-center gap-2 text-brand"><ShieldCheck class="h-5 w-5" /><h2 class="font-semibold">账号信息</h2></div>
      <div class="mt-5 space-y-3 text-sm">
        <div><span class="text-slate-500">登录账号：</span>{{ auth.user?.login_id || "兼容登录" }}</div>
        <div><span class="text-slate-500">姓名：</span>{{ auth.user?.name }}</div>
        <div><span class="text-slate-500">角色：</span>{{ { student: "学生", teacher: "教师", admin: "管理员" }[auth.user?.role] }}</div>
      </div>
      <div v-if="auth.contexts.length" class="mt-5 border-t border-slate-200 pt-4">
        <h3 class="mb-2 text-sm font-semibold text-brand">班级与课程</h3>
        <div v-for="item in auth.contexts" :key="item.enrollment_id || item.assignment_id" class="mb-2 rounded bg-slate-50 p-3 text-sm">
          {{ item.term.name }} · {{ item.class_group.name }} · {{ item.course.name }}
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="flex items-center gap-2 text-brand"><KeyRound class="h-5 w-5" /><h2 class="font-semibold">修改密码</h2></div>
      <p v-if="auth.user?.must_change_password" class="mt-4 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">这是初始密码，完成修改后才能使用其他功能。</p>
      <form class="mt-5 max-w-lg space-y-4" @submit.prevent="changePassword">
        <div><label class="field-label">当前密码</label><input v-model="form.current_password" class="input" type="password" required /></div>
        <div><label class="field-label">新密码</label><input v-model="form.new_password" class="input" type="password" minlength="8" required /></div>
        <div><label class="field-label">确认新密码</label><input v-model="form.confirm_password" class="input" type="password" minlength="8" required /></div>
        <p v-if="message" class="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{{ message }}</p>
        <p v-if="error" class="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{{ error }}</p>
        <button class="btn-primary" :disabled="saving || !auth.user?.login_id">{{ saving ? "保存中..." : "保存新密码" }}</button>
      </form>
    </section>
  </div>
</template>
