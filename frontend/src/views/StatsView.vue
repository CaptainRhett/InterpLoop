<script setup>
import { Download, RefreshCcw } from "@lucide/vue";
import { onMounted, ref } from "vue";
import { api, downloadBlob } from "../api";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const summary = ref(null);
const loading = ref(false);

async function load() {
  loading.value = true;
  const { data } = await api.get("/stats/summary");
  summary.value = data;
  loading.value = false;
}

async function exportPractices() {
  await downloadBlob("/practices/export.csv", "interploop-practices.csv");
}

onMounted(load);
</script>

<template>
  <div class="space-y-5">
    <section class="panel">
      <div class="mb-5 flex items-center justify-between">
        <div>
          <h2 class="text-lg font-semibold text-brand">学习数据统计</h2>
          <p class="mt-1 text-sm text-slate-500">来自后端 SQLite 的真实练习数据。</p>
        </div>
        <div class="flex gap-2">
          <button class="btn-secondary" :disabled="loading" @click="load"><RefreshCcw class="h-4 w-4" />刷新</button>
          <button v-if="auth.isTeacher" class="btn-secondary" @click="exportPractices"><Download class="h-4 w-4" />导出练习 CSV</button>
        </div>
      </div>
      <div class="grid gap-4 md:grid-cols-4">
        <div class="rounded-lg bg-blue-50 p-5 text-center">
          <div class="text-3xl font-bold text-brand">{{ summary?.total_practices ?? 0 }}</div>
          <div class="mt-1 text-sm text-slate-600">总练习次数</div>
        </div>
        <div class="rounded-lg bg-emerald-50 p-5 text-center">
          <div class="text-3xl font-bold text-accent">{{ summary?.completed_practices ?? 0 }}</div>
          <div class="mt-1 text-sm text-slate-600">已完成闭环</div>
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
      <h2 class="mb-4 text-lg font-semibold text-brand">最近练习</h2>
      <div class="overflow-x-auto">
        <table class="min-w-full text-left text-sm">
          <thead class="bg-slate-50 text-slate-600">
            <tr>
              <th class="px-3 py-2">时间</th>
              <th class="px-3 py-2">学生</th>
              <th class="px-3 py-2">方向</th>
              <th class="px-3 py-2">状态</th>
              <th class="px-3 py-2">评分</th>
              <th class="px-3 py-2">源语摘要</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in summary?.recent || []" :key="item.id" class="border-t border-slate-100">
              <td class="px-3 py-2">{{ item.created_at?.slice(0, 19).replace("T", " ") }}</td>
              <td class="px-3 py-2">{{ item.user?.name }}</td>
              <td class="px-3 py-2">{{ item.direction }}</td>
              <td class="px-3 py-2">{{ item.status }}</td>
              <td class="px-3 py-2">{{ item.result?.score || "-" }}</td>
              <td class="max-w-xl truncate px-3 py-2">{{ item.source_text }}</td>
            </tr>
            <tr v-if="!(summary?.recent || []).length">
              <td class="px-3 py-8 text-center text-slate-500" colspan="6">尚无练习记录</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
