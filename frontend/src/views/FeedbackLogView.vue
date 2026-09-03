<script setup>
import { Download, ExternalLink, Save, Search, Trash2 } from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";
import { api, downloadBlob } from "../api";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const error = ref("");
const message = ref("");
const records = ref([]);
const managedContexts = ref([]);

const form = reactive({
  student_no: "",
  student_name: "",
  task_id: "",
  feedback_type: "AI反馈（豆包）",
  raw_text: "",
  pros: "",
  cons: "",
  suggestions: "",
  overall: "",
  context_id: "",
});

const availableContexts = computed(() => {
  if (auth.isTeacher) return managedContexts.value;
  return auth.contexts.map((item) => ({ ...item, student: auth.user }));
});

const selectedContext = computed(() =>
  availableContexts.value.find((item) => item.enrollment_id === Number(form.context_id)),
);

function syncContext() {
  const item = selectedContext.value;
  if (!item) return;
  form.student_no = item.student?.student_no || "";
  form.student_name = item.student?.name || "";
}

function sample() {
  form.raw_text = `一、整体评价
1. 优点
- 核心政治术语基本正确，句意完整可懂。
- 句式结构符合日语表达习惯。
2. 主要问题
- 「～しか～ない」句式误用。
- 活动名称译法前后不够统一。
二、改进建议
- 系统整理高频政治术语固定译法。
- 练习长句切分，先保留主干信息。`;
}

async function parse() {
  error.value = "";
  message.value = "";
  try {
    const { data } = await api.post("/feedback/parse", { raw_text: form.raw_text });
    Object.assign(form, {
      pros: data.pros,
      cons: data.cons,
      suggestions: data.suggestions,
      overall: data.overall,
    });
    message.value = `已拆分：优点 ${data.counts.pros}，问题 ${data.counts.cons}，建议 ${data.counts.suggestions}`;
  } catch (err) {
    error.value = err.response?.data?.error || "拆分失败";
  }
}

async function save() {
  error.value = "";
  message.value = "";
  try {
    if (auth.user?.login_id && !selectedContext.value) {
      error.value = "请选择反馈所属的学生、班级和课程";
      return;
    }
    await api.post("/feedback-logs", {
      ...form,
      user_id: selectedContext.value?.student.id,
      class_id: selectedContext.value?.class_group.id,
      course_id: selectedContext.value?.course.id,
    });
    message.value = "已保存反馈记录";
    await loadRecords();
  } catch (err) {
    error.value = err.response?.data?.error || "保存失败";
  }
}

function clear() {
  Object.assign(form, {
    student_no: "",
    student_name: "",
    task_id: "",
    feedback_type: "AI反馈（豆包）",
    raw_text: "",
    pros: "",
    cons: "",
    suggestions: "",
    overall: "",
  });
}

async function loadRecords() {
  const { data } = await api.get("/feedback-logs");
  records.value = data.feedback_logs;
}

async function loadManagedContexts() {
  if (auth.isTeacher) {
    const { data } = await api.get("/auth/me/students");
    managedContexts.value = data.student_contexts;
  }
  if (availableContexts.value.length === 1) {
    form.context_id = availableContexts.value[0].enrollment_id;
    syncContext();
  }
}

async function exportCsv() {
  await downloadBlob("/feedback-logs/export.csv", "interploop-feedback.csv");
}

function linkedPracticeId(record) {
  return record.task_id?.match(/^LP-(\d+)-V\d+$/)?.[1] || null;
}

onMounted(async () => {
  await Promise.all([loadRecords(), loadManagedContexts()]);
});
</script>

<template>
  <div class="grid gap-5 xl:grid-cols-[minmax(0,1fr)_460px]">
    <section class="panel space-y-4">
      <div>
        <h2 class="text-lg font-semibold text-brand">FeedbackLog 反馈归档</h2>
        <p class="mt-1 text-sm text-slate-500">粘贴豆包或教师反馈，拆分为优点、问题、建议、总评字段。</p>
      </div>

      <div class="grid gap-3 md:grid-cols-4">
        <div class="md:col-span-4">
          <label class="field-label">学生、班级与课程</label>
          <select v-model="form.context_id" class="input" :disabled="!availableContexts.length" @change="syncContext">
            <option value="">{{ availableContexts.length ? "请选择" : "暂无可管理的学生课程" }}</option>
            <option v-for="item in availableContexts" :key="item.enrollment_id" :value="item.enrollment_id">
              {{ item.student?.student_no }} · {{ item.student?.name }} · {{ item.term.name }} · {{ item.class_group.name }} · {{ item.course.name }}
            </option>
          </select>
        </div>
        <div>
          <label class="field-label">学生编号</label>
          <input v-model.trim="form.student_no" class="input" :readonly="Boolean(auth.user?.login_id)" />
        </div>
        <div>
          <label class="field-label">学生姓名</label>
          <input v-model.trim="form.student_name" class="input" :readonly="Boolean(auth.user?.login_id)" />
        </div>
        <div>
          <label class="field-label">任务编号</label>
          <input v-model.trim="form.task_id" class="input" placeholder="W5-T2" />
        </div>
        <div>
          <label class="field-label">反馈类型</label>
          <select v-model="form.feedback_type" class="input">
            <option>AI反馈（豆包）</option>
            <option>教师反馈</option>
            <option>同伴反馈</option>
          </select>
        </div>
      </div>

      <textarea v-model="form.raw_text" class="input min-h-72 resize-y" placeholder="粘贴反馈原文"></textarea>
      <div class="flex flex-wrap gap-2">
        <button class="btn-primary" @click="parse"><Search class="h-4 w-4" />自动拆分</button>
        <button class="btn-secondary" @click="sample">载入示例</button>
        <button class="btn-secondary" @click="clear"><Trash2 class="h-4 w-4" />清空</button>
      </div>
      <p v-if="message" class="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{{ message }}</p>
      <p v-if="error" class="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{{ error }}</p>
    </section>

    <section class="panel space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-lg font-semibold text-brand">结构化字段</h2>
        <button class="btn-success" @click="save"><Save class="h-4 w-4" />保存</button>
      </div>
      <div>
        <label class="field-label text-emerald-700">优点</label>
        <textarea v-model="form.pros" class="input min-h-24 resize-y"></textarea>
      </div>
      <div>
        <label class="field-label text-red-700">主要问题</label>
        <textarea v-model="form.cons" class="input min-h-24 resize-y"></textarea>
      </div>
      <div>
        <label class="field-label text-blue-700">改进建议</label>
        <textarea v-model="form.suggestions" class="input min-h-24 resize-y"></textarea>
      </div>
      <div>
        <label class="field-label">综合评语</label>
        <textarea v-model="form.overall" class="input min-h-20 resize-y"></textarea>
      </div>
    </section>

    <section class="panel xl:col-span-2">
      <div class="mb-4 flex items-center justify-between">
        <h2 class="text-lg font-semibold text-brand">已保存记录</h2>
        <button v-if="auth.isTeacher" class="btn-secondary" @click="exportCsv"><Download class="h-4 w-4" />导出 CSV</button>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full text-left text-sm">
          <thead class="bg-slate-50 text-slate-600">
            <tr>
              <th class="px-3 py-2">时间</th>
              <th class="px-3 py-2">学号</th>
              <th class="px-3 py-2">姓名</th>
              <th class="px-3 py-2">任务</th>
              <th class="px-3 py-2">类型</th>
              <th class="px-3 py-2">建议摘要</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="record in records" :key="record.id" class="border-t border-slate-100">
              <td class="px-3 py-2">{{ record.created_at?.slice(0, 19).replace("T", " ") }}</td>
              <td class="px-3 py-2">{{ record.student_no }}</td>
              <td class="px-3 py-2">{{ record.student_name }}</td>
              <td class="px-3 py-2">
                <RouterLink
                  v-if="linkedPracticeId(record)"
                  class="inline-flex items-center gap-1 font-medium text-brand hover:underline"
                  :to="`/practices/${linkedPracticeId(record)}`"
                >
                  {{ record.task_id }}<ExternalLink class="h-3.5 w-3.5" />
                </RouterLink>
                <span v-else>{{ record.task_id }}</span>
              </td>
              <td class="px-3 py-2">{{ record.feedback_type }}</td>
              <td class="max-w-lg truncate px-3 py-2">{{ record.suggestions || record.overall }}</td>
            </tr>
            <tr v-if="!records.length">
              <td class="px-3 py-8 text-center text-slate-500" colspan="6">尚无记录</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
