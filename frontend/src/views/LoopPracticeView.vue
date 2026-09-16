<script setup>
import { CheckCircle2, Eye, EyeOff, Mic, Pause, Play, Save, Square, Wand2 } from "@lucide/vue";
import { computed, onBeforeUnmount, reactive, ref } from "vue";
import { api } from "../api";
import { createCuePlayer, splitSentences } from "../utils/interpCue";
import { LANGUAGE_DIRECTIONS, languagePairForDirection } from "../languages";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();

const state = reactive({
  step: 1,
  sourceText:
    "本日は、皆様の御参集を賜り、日中双方が連携して準備を進めてまいりました第一回中日企業経営交流商談会のオープニングイベントを開催できますことを誠にうれしく思います。",
  direction: "日→中",
  contextId: auth.contexts.length === 1 ? auth.contexts[0].enrollment_id : "",
  interval: 20,
  hideSource: true,
  segments: [],
  segmentIndex: 0,
  modelName: "doubao",
  role: "严格口译教师",
  strictness: 4,
  dimensions: ["信息完整度", "敬语、语域与正式语体", "术语和机构名称", "句子自然度", "优先改进问题"],
  practice: null,
  asrText: "",
  evaluation: null,
  evaluationVersion: null,
  archive: null,
  status: "准备就绪",
});

const allDimensions = ["信息完整度", "敬语、语域与正式语体", "术语和机构名称", "语法与用词", "句子自然度", "优先改进问题", "参考译法"];
const recording = ref(false);
const startingRecording = ref(false);
const creating = ref(false);
const sourcePlaying = ref(false);
const sourcePaused = ref(false);
const sourcePausable = ref(false);
const sourcePlayed = ref(false);
let lifecycle = 0;
const sourceSentences = computed(() => splitSentences(state.sourceText));
const currentSegment = computed(() => state.segments[state.segmentIndex]);
const player = createCuePlayer({
  synthesize: async (payload, signal) => (await api.post("/tts", payload, { signal })).data,
  onIndex: () => {},
  onStatus: (status) => { state.status = status; },
  onPlaying: (value) => { sourcePlaying.value = value; },
  onPaused: (value) => { sourcePaused.value = value; },
  onPausable: (value) => { sourcePausable.value = value; },
});
const evaluating = ref(false);
const archiving = ref(false);
const uploading = ref(false);
const elapsed = ref(0);
let stream = null;
let audioContext = null;
let audioInput = null;
let audioProcessor = null;
let pcmChunks = [];
let tickTimer = null;
const targetSampleRate = 16000;

const languagePair = computed(() => languagePairForDirection(state.direction));
const sourceLang = computed(() => languagePair.value.sourceLang);
const targetLang = computed(() => languagePair.value.targetLang);
const selectedContext = computed(() =>
  auth.contexts.find((item) => item.enrollment_id === Number(state.contextId)),
);

function stepClass(step) {
  if (state.step > step) return "bg-accent text-white";
  if (state.step === step) return "bg-brand text-white";
  return "bg-slate-200 text-slate-500";
}

function toggleDimension(item) {
  if (state.dimensions.includes(item)) {
    state.dimensions = state.dimensions.filter((value) => value !== item);
  } else {
    state.dimensions.push(item);
  }
}

async function playSource() {
  if (!currentSegment.value || recording.value || startingRecording.value || uploading.value) return;
  sourcePlayed.value = false;
  const completed = await player.play({
    sentences: [currentSegment.value.source], single: true, lang: sourceLang.value, voice: "",
  });
  if (completed) {
    sourcePlayed.value = true;
    state.status = `第 ${state.segmentIndex + 1} 句播放完毕，请开始录制口译`;
  }
}

function nextSegment() {
  if (recording.value || startingRecording.value || uploading.value || sourcePlaying.value) return;
  if (!currentSegment.value?.recorded || !currentSegment.value.transcript.trim()) return;
  if (state.segmentIndex < state.segments.length - 1) {
    state.hideSource = true;
    state.segmentIndex += 1;
    playSource();
  } else {
    state.asrText = state.segments.map((part) => part.transcript.trim()).join("\n");
    state.step = 4;
    state.status = "全部句子识别完成，请核对全文后生成评价";
  }
}

async function createPractice() {
  const { data } = await api.post("/practices", {
    source_text: state.sourceText,
    direction: state.direction,
    interval_seconds: state.interval,
    model_name: state.modelName,
    prompt_params: {
      role: state.role,
      strictness: state.strictness,
      dimensions: state.dimensions,
      source_segments: state.segments.map((part) => part.source),
    },
    class_id: selectedContext.value?.class_group.id,
    course_id: selectedContext.value?.course.id,
  });
  state.practice = data.practice;
}

async function goRecording() {
  if (creating.value) return;
  if (!state.sourceText.trim()) {
    state.status = "请先输入源语文本";
    return;
  }
  if (auth.user?.login_id && !selectedContext.value) {
    state.status = auth.contexts.length ? "请选择本次练习所属的班级和课程" : "账号尚未分配班级课程，请联系管理员";
    return;
  }
  creating.value = true;
  const run = lifecycle;
  try {
    state.segments = sourceSentences.value.map((source) => ({ source, transcript: "", recorded: false }));
    state.segmentIndex = 0;
    if (!state.practice) await createPractice();
    if (run !== lifecycle) return;
    state.hideSource = true;
    state.step = 3;
    await playSource();
  } catch (error) {
    state.status = `练习创建失败：${apiErrorMessage(error)}`;
  } finally {
    creating.value = false;
  }
}

async function startRecording() {
  if (recording.value || startingRecording.value || uploading.value || sourcePlaying.value || !sourcePlayed.value) return;
  if (window.isSecureContext === false) {
    state.status = "录音需要安全访问地址：请用 http://localhost:5173、http://127.0.0.1:5173 或 HTTPS 打开，不要用普通 http 的局域网 IP。";
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    state.status = "当前访问环境无法使用麦克风，请换用最新版 Chrome/Edge，并通过 localhost 或 HTTPS 打开。";
    return;
  }
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) {
    state.status = "当前浏览器不支持音频采集，请换用最新版 Chrome/Edge";
    return;
  }
  player.stop();
  startingRecording.value = true;
  const run = lifecycle;
  pcmChunks = [];
  elapsed.value = 0;
  try {
    const acquiredStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    if (run !== lifecycle) {
      acquiredStream.getTracks().forEach((track) => track.stop());
      return;
    }
    stream = acquiredStream;
    audioContext = new AudioContextClass();
    if (audioContext.state === "suspended") await audioContext.resume();
    if (run !== lifecycle) return;
    audioInput = audioContext.createMediaStreamSource(stream);
    audioProcessor = audioContext.createScriptProcessor(4096, 1, 1);
    audioProcessor.onaudioprocess = (event) => {
      const input = event.inputBuffer.getChannelData(0);
      const output = event.outputBuffer.getChannelData(0);
      output.fill(0);
      pcmChunks.push(encodePcm16(input, audioContext.sampleRate, targetSampleRate));
    };
    audioInput.connect(audioProcessor);
    audioProcessor.connect(audioContext.destination);
    recording.value = true;
    state.status = "正在录音";
    tickTimer = window.setInterval(() => {
      elapsed.value += 1;
    }, 1000);
  } catch (error) {
    stopAudioCapture();
    state.status = recordingErrorMessage(error);
  } finally {
    startingRecording.value = false;
  }
}

async function stopAndUpload() {
  if (!recording.value || uploading.value) return;
  const run = lifecycle;
  uploading.value = true;
  state.status = "正在上传音频并识别";
  recording.value = false;
  stopAudioCapture();

  try {
    const blob = new Blob(pcmChunks, { type: "application/octet-stream" });
    if (!blob.size) {
      state.status = "没有采集到录音，请重新录制";
      return;
    }
    const form = new FormData();
    form.append("audio", blob, "practice.pcm");
    form.append("lang", targetLang.value);
    form.append("segment_index", String(state.segmentIndex));
    const { data } = await api.post(`/practices/${state.practice.id}/audio`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    if (run !== lifecycle) return;
    state.practice = data.practice;
    currentSegment.value.transcript = data.asr.transcript || "";
    currentSegment.value.recorded = true;
    state.status = currentSegment.value.transcript.trim()
      ? "本句识别完成，可校对文字、重新录制或继续下一句"
      : "本句未识别到文字，请重新录制或填写本句口译文字";
  } catch (error) {
    state.status = `识别失败：${apiErrorMessage(error)}`;
  } finally {
    uploading.value = false;
    pcmChunks = [];
  }
}

function encodePcm16(input, inputSampleRate, outputSampleRate) {
  const samples = resample(input, inputSampleRate, outputSampleRate);
  const buffer = new ArrayBuffer(samples.length * 2);
  const view = new DataView(buffer);
  samples.forEach((sample, index) => {
    const value = Math.max(-1, Math.min(1, sample));
    view.setInt16(index * 2, value < 0 ? value * 0x8000 : value * 0x7fff, true);
  });
  return buffer;
}

function resample(input, inputSampleRate, outputSampleRate) {
  if (inputSampleRate === outputSampleRate) return Array.from(input);
  const ratio = inputSampleRate / outputSampleRate;
  const length = Math.floor(input.length / ratio);
  return Array.from({ length }, (_, index) => {
    const position = index * ratio;
    const left = Math.floor(position);
    const right = Math.min(left + 1, input.length - 1);
    const weight = position - left;
    return input[left] * (1 - weight) + input[right] * weight;
  });
}

function stopAudioCapture() {
  if (tickTimer) {
    window.clearInterval(tickTimer);
    tickTimer = null;
  }
  audioProcessor?.disconnect();
  audioProcessor = null;
  audioInput?.disconnect();
  audioInput = null;
  stream?.getTracks().forEach((track) => track.stop());
  stream = null;
  if (audioContext && audioContext.state !== "closed") audioContext.close();
  audioContext = null;
}

function recordingErrorMessage(error) {
  if (error?.name === "NotAllowedError") return "麦克风权限被拒绝，请在浏览器地址栏允许麦克风后重试";
  if (error?.name === "NotFoundError") return "没有检测到可用麦克风，请连接麦克风后重试";
  if (error?.name === "NotReadableError") return "麦克风正被其他程序占用，请关闭占用后重试";
  return `录音启动失败：${error?.message || "请检查浏览器和麦克风权限"}`;
}

function apiErrorMessage(error) {
  return error?.response?.data?.error || error?.message || "请稍后重试";
}

async function evaluate() {
  if (!state.asrText.trim()) {
    state.status = "请先确认 ASR 识别文本";
    return;
  }
  evaluating.value = true;
  state.status = "正在调用大模型评价";
  try {
    const { data } = await api.post(`/practices/${state.practice.id}/evaluate`, {
      asr_text: state.asrText,
    });
    state.practice = data.practice;
    state.evaluation = data.evaluation;
    state.evaluationVersion = data.evaluation_version;
    state.archive = data.archive;
    state.status = `评价完成，已保存为第 ${data.evaluation_version.version_number} 版`;
  } catch (error) {
    state.status = `评价失败：${apiErrorMessage(error)}`;
  } finally {
    evaluating.value = false;
  }
}

async function archive() {
  if (!state.evaluationVersion) {
    state.status = "请先生成 AI 评价";
    return;
  }
  archiving.value = true;
  state.status = "正在保存完整练习档案";
  try {
    const { data } = await api.post(`/practices/${state.practice.id}/archive`, {
      asr_text: state.asrText,
      evaluation_version_id: state.evaluationVersion.id,
    });
    state.practice = data.practice;
    state.archive = data.archive;
    state.status = "练习档案保存完成";
    state.step = 5;
  } catch (error) {
    state.status = `归档失败：${apiErrorMessage(error)}`;
  } finally {
    archiving.value = false;
  }
}

function newPractice() {
  lifecycle += 1;
  player.stop();
  stopAudioCapture();
  state.segments = [];
  state.segmentIndex = 0;
  state.hideSource = true;
  sourcePlayed.value = false;
  state.step = 1;
  state.practice = null;
  state.asrText = "";
  state.evaluation = null;
  state.evaluationVersion = null;
  state.archive = null;
  state.status = "准备就绪";
}

function printPage() {
  window.print();
}

onBeforeUnmount(() => {
  lifecycle += 1;
  player.stop();
  stopAudioCapture();
});
</script>

<template>
  <div class="space-y-5">
    <div class="grid grid-cols-5 overflow-hidden rounded-lg text-center text-sm font-medium">
      <div v-for="step in 5" :key="step" class="px-2 py-3" :class="stepClass(step)">
        {{ ["输入语料", "设置参数", "口译录音", "AI评价", "归档打印"][step - 1] }}
      </div>
    </div>

    <section v-if="state.step === 1" class="panel space-y-4">
      <h2 class="text-lg font-semibold text-brand">输入口译语料</h2>
      <textarea v-model="state.sourceText" class="input min-h-48 resize-y" placeholder="粘贴中文、日文或英文源语文本"></textarea>
      <div class="grid gap-4 md:grid-cols-3">
        <div>
          <label class="field-label">语言方向</label>
          <select v-model="state.direction" class="input">
            <option v-for="item in LANGUAGE_DIRECTIONS" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </div>
        <div>
          <label class="field-label">班级与课程</label>
          <select v-model="state.contextId" class="input" :disabled="!auth.contexts.length">
            <option value="">{{ auth.contexts.length ? "请选择" : "尚未分配" }}</option>
            <option v-for="item in auth.contexts" :key="item.enrollment_id" :value="item.enrollment_id">
              {{ item.term.name }} · {{ item.class_group.name }} · {{ item.course.name }}
            </option>
          </select>
        </div>
        <div>
          <label class="field-label">断句识别</label>
          <p class="text-sm text-slate-600">共 {{ sourceSentences.length }} 句，按“听一句 → 录一句”完成练习。</p>
        </div>
      </div>
      <button class="btn-primary" @click="state.step = 2">下一步</button>
    </section>

    <section v-if="state.step === 2" class="panel space-y-4">
      <h2 class="text-lg font-semibold text-brand">反馈参数设置</h2>
      <div class="grid gap-4 md:grid-cols-3">
        <div>
          <label class="field-label">评审员角色</label>
          <select v-model="state.role" class="input">
            <option>严格口译教师</option>
            <option>商务口译专家</option>
            <option>通用语言教师</option>
            <option>外交口译顾问</option>
          </select>
        </div>
        <div>
          <label class="field-label">大模型</label>
          <select v-model="state.modelName" class="input">
            <option value="doubao">豆包 / 火山方舟</option>
            <option value="deepseek">DeepSeek（预留）</option>
            <option value="qwen">通义千问（预留）</option>
          </select>
        </div>
        <div>
          <label class="field-label">严格程度：{{ state.strictness }}/5</label>
          <input v-model.number="state.strictness" class="w-full" min="1" max="5" type="range" />
        </div>
      </div>
      <div>
        <label class="field-label">评价维度</label>
        <div class="flex flex-wrap gap-2">
          <button v-for="item in allDimensions" :key="item" class="chip" :class="{ 'chip-active': state.dimensions.includes(item) }" @click="toggleDimension(item)">
            {{ item }}
          </button>
        </div>
      </div>
      <div class="flex gap-2">
        <button class="btn-secondary" :disabled="creating" @click="state.step = 1">上一步</button>
        <button class="btn-primary" :disabled="creating" @click="goRecording"><Play class="h-4 w-4" />播放源语并进入录音</button>
      </div>
      <p class="text-sm text-amber-800">{{ state.status }}</p>
    </section>

    <section v-if="state.step === 3" class="panel space-y-4">
      <h2 class="text-lg font-semibold text-brand">逐句口译 · 第 {{ state.segmentIndex + 1 }} / {{ state.segments.length }} 句</h2>
      <div class="rounded-lg border border-slate-200 bg-slate-50 p-4">
        <div class="flex items-center justify-between gap-2">
          <div class="text-sm font-medium text-slate-500">本句原文</div>
          <button
            type="button"
            class="flex h-9 w-9 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            :aria-label="state.hideSource ? '显示原文' : '隐藏原文'"
            :title="state.hideSource ? '显示原文' : '隐藏原文'"
            :aria-expanded="!state.hideSource"
            aria-controls="current-source"
            @click="state.hideSource = !state.hideSource"
          >
            <Eye v-if="state.hideSource" class="h-5 w-5" aria-hidden="true" />
            <EyeOff v-else class="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
        <div id="current-source">
          <p v-if="!state.hideSource" class="mt-2 text-lg leading-8 text-ink">{{ currentSegment?.source }}</p>
          <p v-else class="mt-2 text-lg leading-8 text-slate-500">原文已隐藏，点击小眼睛查看</p>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <button class="btn-primary" :disabled="recording || startingRecording || uploading || sourcePlaying" @click="playSource"><Play class="h-4 w-4" />重播本句</button>
        <button class="btn-secondary" :disabled="!sourcePausable" @click="player.togglePause()"><Pause class="h-4 w-4" />{{ sourcePaused ? "继续播放" : "暂停原文" }}</button>
        <button class="btn-success" :disabled="recording || startingRecording || uploading || sourcePlaying || !sourcePlayed" @click="startRecording"><Mic class="h-4 w-4" />{{ startingRecording ? "正在打开麦克风…" : "开始本句录音" }}</button>
        <button class="btn-danger" :disabled="!recording || uploading" @click="stopAndUpload"><Square class="h-4 w-4" />完成本句并识别</button>
      </div>
      <div v-if="currentSegment?.recorded && !recording && !startingRecording" class="space-y-3">
        <label class="field-label">本句识别文字（可校对）</label>
        <textarea v-model="currentSegment.transcript" class="input min-h-24" :disabled="uploading"></textarea>
        <button class="btn-primary" :disabled="uploading || sourcePlaying || !currentSegment.transcript.trim()" @click="nextSegment">
          {{ state.segmentIndex + 1 < state.segments.length ? "确认并播放下一句" : "完成全部录音，进入评价" }}
        </button>
      </div>
      <div class="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" v-if="recording">正在录音：{{ elapsed }} 秒</div>
      <div class="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">{{ state.status }}</div>
    </section>

    <section v-if="state.step === 4" class="space-y-4">
      <div class="grid gap-4 xl:grid-cols-3">
        <div class="panel border-t-4 border-t-blue-500">
          <h3 class="mb-3 font-semibold text-brand">源语原文</h3>
          <p class="leading-8">{{ state.sourceText }}</p>
        </div>
        <div class="panel border-t-4 border-t-orange-500">
          <h3 class="mb-3 font-semibold text-brand">ASR识别文本</h3>
          <textarea v-model="state.asrText" class="input min-h-56 resize-y"></textarea>
        </div>
        <div class="panel border-t-4 border-t-accent">
          <h3 class="mb-3 font-semibold text-brand">AI评价与建议</h3>
          <pre class="min-h-56 whitespace-pre-wrap text-sm leading-7">{{ state.evaluation?.feedback_text || "尚未生成评价" }}</pre>
          <div v-if="state.evaluation?.reference_translation" class="mt-4 border-t border-slate-200 pt-4">
            <h4 class="mb-2 text-sm font-semibold text-brand">参考译法</h4>
            <p class="whitespace-pre-wrap text-sm leading-7">{{ state.evaluation.reference_translation }}</p>
          </div>
        </div>
      </div>
      <div class="flex flex-wrap gap-2">
        <button class="btn-primary" :disabled="evaluating" @click="evaluate"><Wand2 class="h-4 w-4" />{{ evaluating ? "评价中..." : "生成评价" }}</button>
        <button class="btn-success" :disabled="!state.evaluationVersion || archiving" @click="archive"><Save class="h-4 w-4" />{{ archiving ? "归档中..." : "确认并归档" }}</button>
      </div>
      <div class="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">{{ state.status }}</div>
    </section>

    <section v-if="state.step === 5" class="panel space-y-4">
      <div class="flex items-center gap-3 text-accent">
        <CheckCircle2 class="h-8 w-8" />
        <h2 class="text-lg font-semibold">练习记录已归档</h2>
      </div>
      <div class="grid gap-3 rounded-lg border border-emerald-100 bg-emerald-50 p-4 text-sm text-emerald-900 md:grid-cols-2">
        <div>学号：{{ auth.user?.student_no || "-" }}</div>
        <div>姓名：{{ auth.user?.name || "-" }}</div>
        <div>方向：{{ state.direction }}</div>
        <div>评分：{{ state.evaluation?.score || "-" }}/10</div>
        <div>课程：{{ selectedContext?.course.name || "-" }}</div>
        <div>评价版本：第 {{ state.archive?.version_number || "-" }} 版</div>
        <div>归档时间：{{ state.archive?.archived_at?.slice(0, 19).replace("T", " ") || "-" }}</div>
      </div>
      <div class="flex flex-wrap gap-2">
        <button class="btn-primary" @click="newPractice">开始新练习</button>
        <RouterLink v-if="state.practice" class="btn-success" :to="`/practices/${state.practice.id}`">查看练习档案</RouterLink>
        <button class="btn-secondary" @click="printPage">打印记录</button>
      </div>
    </section>
  </div>
</template>
