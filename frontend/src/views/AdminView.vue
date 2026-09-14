<script setup>
import SystemSettings from "../components/SystemSettings.vue";
import { Download, RefreshCcw, RotateCcw, Upload, UserPlus } from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";
import { api } from "../api";

const overview = ref({ users: [], terms: [], classes: [], courses: [], enrollments: [], assignments: [] });
const audits = ref([]);
const importResults = ref([]);
const importErrors = ref([]);
const file = ref(null);
const loading = ref(false);
const message = ref("");
const error = ref("");

const userForm = reactive({ login_id: "", name: "", student_no: "", role: "teacher", password: "" });
const assignmentForm = reactive({ teacher_id: "", class_id: "", course_id: "" });

const teachers = computed(() => overview.value.users.filter((user) => user.role === "teacher"));
const selectedCourse = computed(() => overview.value.courses.find((item) => item.id === Number(assignmentForm.course_id)));
const assignmentClasses = computed(() => {
  if (!selectedCourse.value) return overview.value.classes;
  return overview.value.classes.filter((item) => item.term_id === selectedCourse.value.term_id);
});

function roleLabel(role) {
  return { student: "学生", teacher: "教师", admin: "管理员" }[role] || role;
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const [{ data }, { data: auditData }] = await Promise.all([
      api.get("/admin/overview"),
      api.get("/admin/audit-logs"),
    ]);
    overview.value = data;
    audits.value = auditData.audit_logs;
  } catch (err) {
    error.value = err.response?.data?.error || "管理数据加载失败";
  } finally {
    loading.value = false;
  }
}

async function createUser() {
  error.value = "";
  message.value = "";
  try {
    const { data } = await api.post("/admin/users", userForm);
    message.value = `账号 ${data.user.login_id} 已创建，初始密码：${data.initial_password}`;
    Object.assign(userForm, { login_id: "", name: "", student_no: "", role: "teacher", password: "" });
    await load();
  } catch (err) {
    error.value = err.response?.data?.error || "账号创建失败";
  }
}

async function toggleAccount(user) {
  error.value = "";
  try {
    await api.patch(`/admin/users/${user.id}`, { is_active: !user.is_active });
    await load();
  } catch (err) {
    error.value = err.response?.data?.error || "账号状态更新失败";
  }
}

async function resetPassword(user) {
  error.value = "";
  try {
    const { data } = await api.post(`/admin/users/${user.id}/reset-password`, {});
    message.value = `${user.name} 的临时密码：${data.initial_password}`;
    await load();
  } catch (err) {
    error.value = err.response?.data?.error || "密码重置失败";
  }
}

async function importStudents() {
  if (!file.value) return;
  const form = new FormData();
  form.append("file", file.value);
  loading.value = true;
  error.value = "";
  try {
    const { data } = await api.post("/admin/students/import", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    importResults.value = data.imported;
    importErrors.value = data.errors;
    message.value = `成功处理 ${data.count} 条学生记录`;
    await load();
  } catch (err) {
    error.value = err.response?.data?.error || "名单导入失败";
  } finally {
    loading.value = false;
  }
}

async function saveAssignment() {
  const course = selectedCourse.value;
  if (!course) return;
  error.value = "";
  try {
    await api.post("/admin/teaching-assignments", {
      teacher_id: Number(assignmentForm.teacher_id),
      class_id: Number(assignmentForm.class_id),
      course_id: Number(assignmentForm.course_id),
      term_id: course.term_id,
    });
    message.value = "教师授课范围已保存";
    Object.assign(assignmentForm, { teacher_id: "", class_id: "", course_id: "" });
    await load();
  } catch (err) {
    error.value = err.response?.data?.error || "授课范围保存失败";
  }
}

async function toggleAssignment(item) {
  error.value = "";
  try {
    await api.patch(`/admin/teaching-assignments/${item.id}`, {
      is_active: !item.is_active,
    });
    await load();
  } catch (err) {
    error.value = err.response?.data?.error || "授课范围更新失败";
  }
}

function downloadCredentials() {
  const rows = [["学号", "姓名", "班级", "课程", "学期", "初始密码"]];
  importResults.value.forEach((item) => {
    rows.push([item.student_no, item.name, item.class_name, item.course_name, item.term_name, item.initial_password]);
  });
  const csv = rows.map((row) => row.map((cell) => `"${String(cell || "").replaceAll('"', '""')}"`).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "student-initial-passwords.csv";
  link.click();
  URL.revokeObjectURL(url);
}

onMounted(load);
</script>

<template>
  <div class="space-y-5">
    <SystemSettings />
    <section class="panel">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div><h2 class="text-lg font-semibold text-brand">账号与教学组织管理</h2><p class="mt-1 text-sm text-slate-500">导入学生、创建教师账号并配置班级课程权限。</p></div>
        <button class="btn-secondary" :disabled="loading" @click="load"><RefreshCcw class="h-4 w-4" />刷新</button>
      </div>
      <p v-if="message" class="mt-4 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{{ message }}</p>
      <p v-if="error" class="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{{ error }}</p>
    </section>

    <div class="grid gap-5 xl:grid-cols-2">
      <section class="panel space-y-4">
        <div><h3 class="font-semibold text-brand">导入学生名单</h3><p class="mt-1 text-sm text-slate-500">支持 XLSX/CSV。表头需包含：学号、姓名、班级、课程、学期。</p></div>
        <input class="input" type="file" accept=".xlsx,.csv" @change="file = $event.target.files[0]" />
        <div class="flex gap-2"><button class="btn-primary" :disabled="!file || loading" @click="importStudents"><Upload class="h-4 w-4" />上传并生成账号</button><button v-if="importResults.length" class="btn-secondary" @click="downloadCredentials"><Download class="h-4 w-4" />下载初始密码</button></div>
        <div v-if="importResults.length" class="max-h-56 overflow-auto rounded border border-slate-200 text-sm">
          <div v-for="item in importResults" :key="`${item.student_no}-${item.course_name}`" class="border-b px-3 py-2 last:border-0">{{ item.student_no }} · {{ item.name }} · {{ item.class_name }} · {{ item.course_name }}<span v-if="item.initial_password" class="ml-2 text-amber-700">新账号</span></div>
        </div>
        <div v-if="importErrors.length" class="rounded bg-red-50 p-3 text-sm text-red-700"><div v-for="item in importErrors" :key="item.row">第 {{ item.row }} 行：{{ item.error }}</div></div>
      </section>

      <section class="panel space-y-4">
        <h3 class="font-semibold text-brand">创建账号</h3>
        <div class="grid gap-3 sm:grid-cols-2"><div><label class="field-label">登录账号</label><input v-model.trim="userForm.login_id" class="input" /></div><div><label class="field-label">姓名</label><input v-model.trim="userForm.name" class="input" /></div><div><label class="field-label">人员编号</label><input v-model.trim="userForm.student_no" class="input" /></div><div><label class="field-label">角色</label><select v-model="userForm.role" class="input"><option value="teacher">教师</option><option value="student">学生</option><option value="admin">管理员</option></select></div></div>
        <div><label class="field-label">初始密码（留空自动生成）</label><input v-model="userForm.password" class="input" type="password" /></div>
        <button class="btn-primary" :disabled="!userForm.login_id || !userForm.name" @click="createUser"><UserPlus class="h-4 w-4" />创建账号</button>
      </section>
    </div>

    <section class="panel space-y-4">
      <h3 class="font-semibold text-brand">教师授课范围</h3>
      <div class="grid gap-3 md:grid-cols-4"><select v-model="assignmentForm.teacher_id" class="input"><option value="">选择教师</option><option v-for="item in teachers" :key="item.id" :value="item.id">{{ item.name }}（{{ item.login_id }}）</option></select><select v-model="assignmentForm.course_id" class="input"><option value="">选择课程</option><option v-for="item in overview.courses" :key="item.id" :value="item.id">{{ item.term.name }} · {{ item.name }}</option></select><select v-model="assignmentForm.class_id" class="input"><option value="">选择班级</option><option v-for="item in assignmentClasses" :key="item.id" :value="item.id">{{ item.name }}</option></select><button class="btn-success" :disabled="!assignmentForm.teacher_id || !assignmentForm.class_id || !assignmentForm.course_id" @click="saveAssignment">保存授课权限</button></div>
      <div class="grid gap-2 md:grid-cols-2"><div v-for="item in overview.assignments" :key="item.id" class="flex items-center justify-between gap-3 rounded bg-slate-50 p-3 text-sm"><span>{{ item.teacher.name }} · {{ item.class_group.name }} · {{ item.course.name }}</span><button class="hover:underline" :class="item.is_active ? 'text-red-600' : 'text-emerald-700'" @click="toggleAssignment(item)">{{ item.is_active ? "停用" : "启用" }}</button></div></div>
    </section>

    <section class="panel">
      <h3 class="mb-4 font-semibold text-brand">账号列表</h3>
      <div class="overflow-x-auto"><table class="min-w-full text-left text-sm"><thead class="bg-slate-50"><tr><th class="px-3 py-2">账号</th><th class="px-3 py-2">姓名</th><th class="px-3 py-2">角色</th><th class="px-3 py-2">状态</th><th class="px-3 py-2">操作</th></tr></thead><tbody><tr v-for="user in overview.users" :key="user.id" class="border-t"><td class="px-3 py-2">{{ user.login_id }}</td><td class="px-3 py-2">{{ user.name }}</td><td class="px-3 py-2">{{ roleLabel(user.role) }}</td><td class="px-3 py-2">{{ user.is_active ? "启用" : "禁用" }}</td><td class="px-3 py-2"><div class="flex gap-2"><button class="text-brand hover:underline" @click="resetPassword(user)"><RotateCcw class="inline h-3.5 w-3.5" />重置密码</button><button class="hover:underline" :class="user.is_active ? 'text-red-600' : 'text-emerald-700'" @click="toggleAccount(user)">{{ user.is_active ? "禁用" : "启用" }}</button></div></td></tr></tbody></table></div>
    </section>

    <section class="panel">
      <h3 class="mb-4 font-semibold text-brand">最近审计记录</h3>
      <div class="max-h-80 overflow-auto"><div v-for="item in audits" :key="item.id" class="grid gap-1 border-b py-2 text-sm md:grid-cols-[170px_180px_1fr]"><span class="text-slate-500">{{ item.created_at?.slice(0, 19).replace("T", " ") }}</span><span>{{ item.actor?.name || "系统" }}</span><span>{{ item.action }} · {{ item.target_type }} #{{ item.target_id }}</span></div></div>
    </section>
  </div>
</template>
