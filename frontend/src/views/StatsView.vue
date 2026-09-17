<script setup>
import { Eye, RefreshCcw, Search } from "@lucide/vue";
import { onMounted, ref } from "vue";
import { api } from "../api";
import ExportButton from "../components/ExportButton.vue";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const summary = ref(null);
const records = ref([]);
const studentNo = ref("");
const loading = ref(false);

async function load() {
  loading.value = true;
  try {
    const [{ data: summaryData }, { data: practiceData }] = await Promise.all([
      api.get("/stats/summary"),
      api.get("/practices", {
        params: auth.isTeacher && studentNo.value.trim() ? { student_no: studentNo.value.trim() } : {},
      }),
    ]);
    summary.value = summaryData;
    records.value = practiceData.practices;
  } finally {
    loading.value = false;
  }
}

function statusLabel(status) {
  return {
    created: "已创建",
    transcribed: "已识别",
    evaluated: "已评价，待归档",
    completed: "旧版已完成",
    archived: "已归档",
  }[status] || status;
}

onMounted(load);
</script>

<template>
  <div class="space-y-5">
    <section class="panel">
      <div class="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-lg font-semibold text-brand">学习数据统计</h2>
          <p class="mt-1 text-sm text-slate-500">管理学习统计数据</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button class="btn-secondary" :disabled="loading" @click="load"><RefreshCcw class="h-4 w-4" />刷新</button>
          <ExportButton v-if="!auth.isGuest" path="/practices/export" filename="interploop-practices" label="导出练习" />
        </div>
      </div>
      <div class="grid gap-4 md:grid-cols-4">
        <div class="rounded-lg bg-blue-50 p-5 text-center">
          <div class="text-3xl font-bold text-brand">{{ summary?.total_practices ?? 0 }}</div>
          <div class="mt-1 text-sm text-slate-600">总练习次数</div>
        </div>
        <div class="rounded-lg bg-emerald-50 p-5 text-center">
          <div class="text-3xl font-bold text-accent">{{ summary?.archived_practices ?? 0 }}</div>
          <div class="mt-1 text-sm text-slate-600">正式归档</div>
        </div>
        <div class="rounded-lg bg-orange-50 p-5 text-center">
          <div class="text-3xl font-bold text-orange-600">{{ summary?.average_score?.label ?? "-" }}</div>
          <div class="mt-1 text-sm text-slate-600">平均评价</div>
        </div>
        <div class="rounded-lg bg-violet-50 p-5 text-center">
          <div class="text-3xl font-bold text-violet-700">{{ summary?.estimated_minutes ?? 0 }}</div>
          <div class="mt-1 text-sm text-slate-600">估算分钟</div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 class="text-lg font-semibold text-brand">练习档案</h2>
          <p class="mt-1 text-sm text-slate-500">点击详情可查看完整结果、归档快照和历史评价版本。</p>
        </div>
        <div v-if="auth.isTeacher" class="flex items-end gap-2">
          <div>
            <label class="field-label">按学号筛选</label>
            <input v-model.trim="studentNo" class="input w-52" placeholder="输入完整学号" @keyup.enter="load" />
          </div>
          <button class="btn-secondary" :disabled="loading" @click="load"><Search class="h-4 w-4" />查询</button>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full text-left text-sm">
          <thead class="bg-slate-50 text-slate-600">
            <tr>
              <th class="px-3 py-2">时间</th>
              <th class="px-3 py-2">学生</th>
              <th class="px-3 py-2">方向</th>
              <th class="px-3 py-2">状态</th>
              <th class="px-3 py-2">评分</th>
              <th class="px-3 py-2">评价版本</th>
              <th class="px-3 py-2">归档时间</th>
              <th class="px-3 py-2">源语摘要</th>
              <th class="px-3 py-2">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in records" :key="item.id" class="border-t border-slate-100">
              <td class="px-3 py-2">{{ item.created_at?.slice(0, 19).replace("T", " ") }}</td>
              <td class="px-3 py-2">{{ item.user?.name }}</td>
              <td class="px-3 py-2">{{ item.direction }}</td>
              <td class="px-3 py-2">{{ statusLabel(item.status) }}</td>
              <td class="px-3 py-2">{{ item.result?.score || "-" }}</td>
              <td class="px-3 py-2">{{ item.evaluation_version_count }}</td>
              <td class="px-3 py-2">{{ item.archive?.archived_at?.slice(0, 19).replace("T", " ") || "-" }}</td>
              <td class="max-w-xl truncate px-3 py-2">{{ item.source_text }}</td>
              <td class="px-3 py-2">
                <RouterLink class="inline-flex items-center gap-1 font-medium text-brand hover:underline" :to="`/practices/${item.id}`">
                  <Eye class="h-4 w-4" />详情
                </RouterLink>
              </td>
            </tr>
            <tr v-if="!records.length">
              <td class="px-3 py-8 text-center text-slate-500" colspan="9">尚无练习记录</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
