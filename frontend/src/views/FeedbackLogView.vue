<script setup>
import { Download, Save, Search, Trash2 } from "@lucide/vue";
import { onMounted, reactive, ref } from "vue";
import { api, downloadBlob } from "../api";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const error = ref("");
const message = ref("");
const records = ref([]);

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
});

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
    await api.post("/feedback-logs", form);
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

async function exportCsv() {
  await downloadBlob("/feedback-logs/export.csv", "interploop-feedback.csv");
}

onMounted(loadRecords);
</script>

<template>
  <div class="grid gap-5 xl:grid-cols-[minmax(0,1fr)_460px]">
    <section class="panel space-y-4">
      <div>
        <h2 class="text-lg font-semibold text-brand">FeedbackLog 反馈归档</h2>
        <p class="mt-1 text-sm text-slate-500">粘贴豆包或教师反馈，拆分为优点、问题、建议、总评字段。</p>
      </div>

      <div class="grid gap-3 md:grid-cols-4">
        <div>
          <label class="field-label">学生编号</label>
          <input v-model.trim="form.student_no" class="input" :placeholder="auth.user?.student_no || '1120230120'" />
        </div>
        <div>
          <label class="field-label">学生姓名</label>
          <input v-model.trim="form.student_name" class="input" :placeholder="auth.user?.name || '姓名'" />
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
              <td class="px-3 py-2">{{ record.task_id }}</td>
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
