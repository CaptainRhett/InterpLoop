<script setup>
import { Archive, ArrowLeft, History, RefreshCcw } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { api } from "../api";
import ExportButton from "../components/ExportButton.vue";
import { useAuthStore } from "../stores/auth";

const route = useRoute();
const auth = useAuthStore();
const practice = ref(null);
const archiveSnapshot = ref(null);
const versions = ref([]);
const latestVersion = ref(null);
const selectedVersion = ref(null);
const asrText = ref("");
const loading = ref(false);
const evaluating = ref(false);
const archiving = ref(false);
const message = ref("");
const error = ref("");

const asrChanged = computed(() => {
  if (!latestVersion.value) return Boolean(asrText.value.trim());
  return asrText.value.trim() !== latestVersion.value.asr_text.trim();
});

const archiveIsLatest = computed(
  () =>
    archiveSnapshot.value &&
    latestVersion.value &&
    archiveSnapshot.value.evaluation_version_id === latestVersion.value.id,
);

function formatTime(value) {
  return value ? value.slice(0, 19).replace("T", " ") : "-";
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

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const { data } = await api.get(`/practices/${route.params.id}`);
    practice.value = data.practice;
    archiveSnapshot.value = data.archive;
    versions.value = data.evaluation_versions;
    latestVersion.value = data.latest_evaluation;
    selectedVersion.value = data.latest_evaluation || data.evaluation_versions[0] || null;
    asrText.value = data.latest_evaluation?.asr_text || data.practice.result?.asr_text || "";
  } catch (err) {
    error.value = err.response?.data?.error || "练习档案加载失败";
  } finally {
    loading.value = false;
  }
}

async function reevaluate() {
  if (!asrText.value.trim()) {
    error.value = "ASR 文本不能为空";
    return;
  }
  evaluating.value = true;
  error.value = "";
  message.value = "正在重新评价并保存新版本";
  try {
    const { data } = await api.post(`/practices/${route.params.id}/evaluate`, {
      asr_text: asrText.value,
    });
    message.value = `第 ${data.evaluation_version.version_number} 版评价已保存，请确认后重新归档`;
    await load();
  } catch (err) {
    error.value = err.response?.data?.error || "重新评价失败";
    message.value = "";
  } finally {
    evaluating.value = false;
  }
}

async function archiveLatest() {
  if (!latestVersion.value) {
    error.value = "请先生成 AI 评价";
    return;
  }
  archiving.value = true;
  error.value = "";
  message.value = "正在保存归档快照";
  try {
    await api.post(`/practices/${route.params.id}/archive`, {
      asr_text: asrText.value,
      evaluation_version_id: latestVersion.value.id,
    });
    await load();
    message.value = `第 ${latestVersion.value.version_number} 版已正式归档并同步到 FeedbackLog`;
  } catch (err) {
    error.value = err.response?.data?.error || "归档失败";
    message.value = "";
  } finally {
    archiving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="space-y-5">
    <section class="panel">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <RouterLink class="mb-3 inline-flex items-center gap-1 text-sm text-brand hover:underline" to="/stats">
            <ArrowLeft class="h-4 w-4" />返回练习档案
          </RouterLink>
          <h2 class="text-xl font-semibold text-brand">练习档案 #{{ practice?.id }}</h2>
          <p class="mt-1 text-sm text-slate-500">查看完整结果、修改 ASR 文本、重新评价并追踪历史版本。</p>
        </div>
        <div class="flex flex-wrap items-start gap-2">
          <ExportButton
            v-if="practice && !auth.isGuest"
            :path="`/practices/${practice.id}/export`"
            :filename="`interploop-practice-${practice.id}`"
            label="导出本次记录"
            :disabled="loading || evaluating || archiving"
          />
          <button class="btn-secondary" :disabled="loading" @click="load"><RefreshCcw class="h-4 w-4" />刷新</button>
        </div>
      </div>

      <div v-if="practice" class="mt-5 grid gap-3 rounded-lg bg-slate-50 p-4 text-sm md:grid-cols-3">
        <div><span class="text-slate-500">学生：</span>{{ practice.user?.student_no }} · {{ practice.user?.name }}</div>
        <div><span class="text-slate-500">方向：</span>{{ practice.direction }}</div>
        <div><span class="text-slate-500">状态：</span>{{ statusLabel(practice.status) }}</div>
        <div><span class="text-slate-500">练习时间：</span>{{ formatTime(practice.created_at) }}</div>
        <div><span class="text-slate-500">评价版本：</span>{{ versions.length }} 个</div>
        <div><span class="text-slate-500">当前评分：</span>{{ latestVersion?.score || "-" }}</div>
      </div>
    </section>

    <p v-if="message" class="rounded-md bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{{ message }}</p>
    <p v-if="error" class="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</p>

    <section v-if="practice" class="grid gap-4 xl:grid-cols-3">
      <div class="panel border-t-4 border-t-blue-500">
        <h3 class="mb-3 font-semibold text-brand">源语原文</h3>
        <p class="whitespace-pre-wrap leading-8">{{ practice.source_text }}</p>
      </div>
      <div class="panel border-t-4 border-t-orange-500">
        <h3 class="mb-3 font-semibold text-brand">ASR 识别文本</h3>
        <textarea v-model="asrText" class="input min-h-64 resize-y"></textarea>
        <p v-if="asrChanged" class="mt-2 text-xs text-amber-700">文本已修改，需要重新评价后才能归档。</p>
      </div>
      <div class="panel border-t-4 border-t-accent">
        <h3 class="mb-3 font-semibold text-brand">当前 AI 评价</h3>
        <pre class="min-h-48 whitespace-pre-wrap text-sm leading-7">{{ latestVersion?.feedback_text || "尚无评价" }}</pre>
        <div v-if="latestVersion?.reference_translation" class="mt-4 border-t border-slate-200 pt-4">
          <h4 class="mb-2 text-sm font-semibold text-brand">参考译法</h4>
          <p class="whitespace-pre-wrap text-sm leading-7">{{ latestVersion.reference_translation }}</p>
        </div>
      </div>
    </section>

    <section v-if="practice" class="panel">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 class="font-semibold text-brand">评价与归档操作</h3>
          <p class="mt-1 text-sm text-slate-500">重新评价会创建新版本；归档会保存当前版本快照并同步反馈记录。</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button class="btn-primary" :disabled="evaluating || !asrText.trim()" @click="reevaluate">
            <RefreshCcw class="h-4 w-4" />{{ evaluating ? "评价中..." : latestVersion ? "重新评价" : "生成评价" }}
          </button>
          <button class="btn-success" :disabled="archiving || !latestVersion || asrChanged || archiveIsLatest" @click="archiveLatest">
            <Archive class="h-4 w-4" />{{ archiveIsLatest ? "当前版本已归档" : archiving ? "归档中..." : "归档当前版本" }}
          </button>
        </div>
      </div>
      <div v-if="archiveSnapshot" class="mt-4 rounded-lg border border-emerald-100 bg-emerald-50 p-4 text-sm text-emerald-900">
        正式归档：第 {{ archiveSnapshot.version_number }} 版 · {{ formatTime(archiveSnapshot.archived_at) }} ·
        FeedbackLog #{{ archiveSnapshot.feedback_log_id }}
        <span v-if="!archiveIsLatest" class="ml-2 font-medium text-amber-700">当前已有更新评价，等待重新归档</span>
      </div>
    </section>

    <section v-if="versions.length" class="panel">
      <div class="mb-4 flex items-center gap-2">
        <History class="h-5 w-5 text-brand" />
        <h3 class="font-semibold text-brand">评价历史版本</h3>
      </div>
      <div class="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
        <div class="space-y-2">
          <button
            v-for="version in versions"
            :key="version.id"
            class="w-full rounded-md border px-3 py-3 text-left text-sm transition"
            :class="selectedVersion?.id === version.id ? 'border-brand bg-blue-50 text-brand' : 'border-slate-200 hover:bg-slate-50'"
            @click="selectedVersion = version"
          >
            <span class="font-semibold">第 {{ version.version_number }} 版 · {{ version.score || "-" }}</span>
            <span class="mt-1 block text-xs text-slate-500">{{ formatTime(version.created_at) }}</span>
            <span class="mt-1 block text-xs text-slate-500">评价人：{{ version.created_by?.name || "系统" }}</span>
            <span v-if="archiveSnapshot?.evaluation_version_id === version.id" class="mt-2 inline-block rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700">正式归档版本</span>
          </button>
        </div>
        <div v-if="selectedVersion" class="space-y-4 rounded-lg bg-slate-50 p-4">
          <div>
            <h4 class="mb-2 text-sm font-semibold text-orange-700">该版本 ASR 文本</h4>
            <p class="whitespace-pre-wrap text-sm leading-7">{{ selectedVersion.asr_text }}</p>
          </div>
          <div class="border-t border-slate-200 pt-4">
            <h4 class="mb-2 text-sm font-semibold text-brand">该版本 AI 评价</h4>
            <pre class="whitespace-pre-wrap text-sm leading-7">{{ selectedVersion.feedback_text }}</pre>
          </div>
          <div v-if="selectedVersion.reference_translation" class="border-t border-slate-200 pt-4">
            <h4 class="mb-2 text-sm font-semibold text-emerald-700">参考译法</h4>
            <p class="whitespace-pre-wrap text-sm leading-7">{{ selectedVersion.reference_translation }}</p>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
