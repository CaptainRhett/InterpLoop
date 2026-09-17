<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { api } from "../api";

const settings = reactive({});
const configured = ref({});
const sources = ref({});
const original = ref({});
const webFields = computed(() => Object.keys(sources.value).filter((key) => sources.value[key] === "web"));
const loading = ref(true);
const saving = ref(false);
const testing = ref("");
const dirty = ref(false);
const error = ref("");
const message = ref("");
const testText = ref("请只回复：连接成功");
const testLang = ref("zh-CN");
const testAudio = ref(null);
const testRecording = ref(false);
const startingTestRecording = ref(false);
const testElapsed = ref(0);
const testRecordingError = ref("");
const results = reactive({ llm: null, asr: null });
const secrets = ["DOUBAO_API_KEY", "ASR_API_KEY", "XUNFEI_API_KEY", "XUNFEI_API_SECRET"];
const targetSampleRate = 16000;
const maxTestRecordingSeconds = 30;
const maxTestPcmBytes = targetSampleRate * 2 * maxTestRecordingSeconds;
let recordingRun = 0;
let testStream = null;
let testAudioContext = null;
let testAudioInput = null;
let testAudioProcessor = null;
let testPcmChunks = [];
let testPcmBytes = 0;
let testTimer = null;

function apply(data) {
  Object.assign(settings, data.settings);
  original.value = { ...data.settings };
  sources.value = data.sources || {};
  for (const key of secrets) settings[key] = "";
  configured.value = data.secrets_configured;
  dirty.value = false;
}
async function load() {
  loading.value = true;
  error.value = "";
  try { apply((await api.get("/admin/system/settings")).data); }
  catch (err) { error.value = err.response?.data?.error || "系统配置加载失败"; }
  finally { loading.value = false; }
}
async function save() {
  saving.value = true;
  message.value = "";
  error.value = "";
  try {
    const changes = Object.fromEntries(Object.entries(settings).filter(([key, value]) =>
      secrets.includes(key) ? Boolean(value.trim()) : value !== original.value[key],
    ));
    apply((await api.put("/admin/system/settings", changes)).data);
    results.llm = null;
    results.asr = null;
    message.value = "配置已保存，后续服务调用立即生效。";
  } catch (err) { error.value = err.response?.data?.error || "保存失败"; }
  finally { saving.value = false; }
}
async function restoreEnvironment() {
  saving.value = true;
  error.value = "";
  message.value = "";
  try {
    const resets = Object.fromEntries([...Object.keys(original.value), ...secrets].map((key) => [key, null]));
    apply((await api.put("/admin/system/settings", resets)).data);
    results.llm = null;
    results.asr = null;
    message.value = "已解除全部 Web 覆盖，使用后端启动时读取的环境配置。";
  } catch (err) { error.value = err.response?.data?.error || "恢复环境配置失败"; }
  finally { saving.value = false; }
}
async function test(service) {
  if (dirty.value || saving.value || testing.value || testRecording.value || startingTestRecording.value) return;
  if (service === "asr" && !testAudio.value) return;
  testing.value = service;
  results[service] = null;
  try {
    let body = { text: testText.value };
    if (service === "asr") {
      body = new FormData();
      body.append("audio", testAudio.value, "test-recording.pcm");
      body.append("lang", testLang.value);
    }
    results[service] = (await api.post(`/admin/system/test/${service}`, body, { timeout: 90000 })).data;
  } catch (err) {
    results[service] = err.response?.data || { ok: false, error: "连接失败或测试超时，请稍后重试" };
  } finally { testing.value = ""; }
}
async function startTestRecording() {
  if (dirty.value || saving.value || testing.value || testRecording.value || startingTestRecording.value) return;
  testRecordingError.value = "";
  if (window.isSecureContext === false) {
    testRecordingError.value = "录音需要通过 localhost 或 HTTPS 安全地址访问。";
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    testRecordingError.value = "当前浏览器无法使用麦克风，请换用最新版 Chrome 或 Edge。";
    return;
  }
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) {
    testRecordingError.value = "当前浏览器不支持音频采集，请换用最新版 Chrome 或 Edge。";
    return;
  }

  startingTestRecording.value = true;
  const run = ++recordingRun;
  testPcmChunks = [];
  testPcmBytes = 0;
  testElapsed.value = 0;
  try {
    const acquiredStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    if (run !== recordingRun) {
      acquiredStream.getTracks().forEach((track) => track.stop());
      return;
    }
    testStream = acquiredStream;
    testAudioContext = new AudioContextClass();
    if (testAudioContext.state === "suspended") await testAudioContext.resume();
    if (run !== recordingRun) {
      stopTestAudioCapture();
      return;
    }
    testAudioInput = testAudioContext.createMediaStreamSource(testStream);
    testAudioProcessor = testAudioContext.createScriptProcessor(4096, 1, 1);
    const inputSampleRate = testAudioContext.sampleRate;
    testAudioProcessor.onaudioprocess = (event) => {
      const input = event.inputBuffer.getChannelData(0);
      event.outputBuffer.getChannelData(0).fill(0);
      const encoded = encodePcm16(input, inputSampleRate, targetSampleRate);
      const remaining = maxTestPcmBytes - testPcmBytes;
      if (remaining <= 0) {
        void stopTestRecording();
        return;
      }
      const chunk = encoded.byteLength > remaining ? encoded.slice(0, remaining) : encoded;
      testPcmChunks.push(chunk);
      testPcmBytes += chunk.byteLength;
      if (testPcmBytes >= maxTestPcmBytes) void stopTestRecording();
    };
    results.asr = null;
    testAudio.value = null;
    testAudioInput.connect(testAudioProcessor);
    testAudioProcessor.connect(testAudioContext.destination);
    testRecording.value = true;
    testTimer = window.setInterval(() => {
      testElapsed.value += 1;
      if (testElapsed.value >= maxTestRecordingSeconds) void stopTestRecording();
    }, 1000);
  } catch (err) {
    stopTestAudioCapture();
    testRecordingError.value = microphoneErrorMessage(err);
  } finally {
    startingTestRecording.value = false;
  }
}
async function stopTestRecording() {
  if (!testRecording.value) return;
  testRecording.value = false;
  stopTestAudioCapture();
  const audio = new Blob(testPcmChunks, { type: "application/octet-stream" });
  testPcmChunks = [];
  testPcmBytes = 0;
  if (!audio.size) {
    testRecordingError.value = "没有采集到录音，请重新录制。";
    return;
  }
  testAudio.value = audio;
  await test("asr");
}
function stopTestAudioCapture() {
  if (testTimer) {
    window.clearInterval(testTimer);
    testTimer = null;
  }
  if (testAudioProcessor) testAudioProcessor.onaudioprocess = null;
  testAudioProcessor?.disconnect();
  testAudioProcessor = null;
  testAudioInput?.disconnect();
  testAudioInput = null;
  testStream?.getTracks().forEach((track) => track.stop());
  testStream = null;
  if (testAudioContext && testAudioContext.state !== "closed") {
    const closing = testAudioContext.close();
    closing?.catch?.(() => {});
  }
  testAudioContext = null;
}
function microphoneErrorMessage(err) {
  if (err?.name === "NotAllowedError") return "麦克风权限被拒绝，请在浏览器地址栏允许麦克风后重试。";
  if (err?.name === "NotFoundError") return "没有检测到可用麦克风，请连接麦克风后重试。";
  if (err?.name === "NotReadableError") return "麦克风正被其他程序占用，请关闭占用后重试。";
  return `录音启动失败：${err?.message || "请检查浏览器和麦克风权限"}`;
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
function secretPlaceholder(key) {
  return configured.value[key] ? "已配置，留空保留；输入新值替换" : "尚未配置，请填写";
}
onMounted(load);
onBeforeUnmount(() => {
  recordingRun += 1;
  testRecording.value = false;
  stopTestAudioCapture();
});
</script>

<template>
  <section class="panel space-y-4">
    <div>
      <h2 class="text-lg font-semibold text-brand">系统配置 · 第三方服务</h2>
      <p class="mt-1 text-sm text-slate-500">配置模型和语音识别服务，供 AI 对话、口译评价和录音识别使用。</p>
    </div>
    <p v-if="loading" class="text-sm text-slate-500">正在加载配置…</p>
    <p v-if="error" class="rounded bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
    <button v-if="!loading && !settings.LLM_PROVIDER" class="btn-secondary" @click="load">重新加载</button>
    <template v-if="!loading && settings.LLM_PROVIDER">
      <div class="rounded bg-slate-50 p-3 text-sm text-slate-600">
        <p>优先级：Web 配置 → .env / 环境变量 → 默认值。保存只覆盖修改过的字段；密钥留空保留。</p>
        <p class="mt-1">{{ webFields.length ? `Web 覆盖字段：${webFields.join('、')}` : '当前全部使用环境配置或默认值' }}</p>
        <p class="mt-1">修改 .env 后请重启后端；已有 Web 覆盖的字段需先恢复环境配置。</p>
      </div>
      <form class="space-y-4" @submit.prevent="save" @input="dirty = true" @change="dirty = true">
        <fieldset :disabled="saving || !!testing || testRecording || startingTestRecording" class="space-y-4">
          <label class="flex items-center gap-2 text-sm"><input v-model="settings.USE_MOCK_SERVICES" type="checkbox" />业务使用模拟服务（关闭后使用以下真实配置）</label>
          <div class="grid gap-5 lg:grid-cols-2">
            <div class="space-y-3 rounded border border-slate-200 p-4">
              <h3 class="font-semibold text-brand">大语言模型</h3>
              <label class="block text-sm">服务类型
                <select v-model="settings.LLM_PROVIDER" class="input mt-1">
                  <option value="doubao">豆包 / 火山方舟</option><option value="openai_compatible">兼容 OpenAI Chat Completions</option>
                </select>
              </label>
              <label class="block text-sm">API 基础地址<input v-model.trim="settings.DOUBAO_BASE_URL" class="input mt-1" required placeholder="https://服务域名/v1" /></label>
              <label class="block text-sm">模型 ID / 推理接入点<input v-model.trim="settings.DOUBAO_MODEL" class="input mt-1" placeholder="填写服务商提供的模型 ID" /></label>
              <label class="block text-sm">API Key<input v-model.trim="settings.DOUBAO_API_KEY" class="input mt-1" type="password" autocomplete="new-password" :placeholder="secretPlaceholder('DOUBAO_API_KEY')" /></label>
              <label class="block text-sm">请求超时（秒）<input v-model.number="settings.LLM_TIMEOUT_SECONDS" class="input mt-1" type="number" min="5" max="120" required /></label>
            </div>
            <div class="space-y-3 rounded border border-slate-200 p-4">
              <h3 class="font-semibold text-brand">语音识别</h3>
              <label class="block text-sm">服务类型
                <select v-model="settings.ASR_PROVIDER" class="input mt-1"><option value="xunfei">讯飞语音听写</option><option value="openai_compatible">兼容 OpenAI 音频转写</option></select>
              </label>
              <template v-if="settings.ASR_PROVIDER === 'xunfei'">
                <label class="block text-sm">讯飞 App ID<input v-model.trim="settings.XUNFEI_APP_ID" class="input mt-1" /></label>
                <label class="block text-sm">API Key<input v-model.trim="settings.XUNFEI_API_KEY" class="input mt-1" type="password" autocomplete="new-password" :placeholder="secretPlaceholder('XUNFEI_API_KEY')" /></label>
                <label class="block text-sm">API Secret<input v-model.trim="settings.XUNFEI_API_SECRET" class="input mt-1" type="password" autocomplete="new-password" :placeholder="secretPlaceholder('XUNFEI_API_SECRET')" /></label>
                <label class="block text-sm">识别主机<input v-model.trim="settings.XUNFEI_IAT_HOST" class="input mt-1" placeholder="iat-api.xfyun.cn" /></label>
                <label class="block text-sm">识别领域 / 模型类别<input v-model.trim="settings.XUNFEI_IAT_DOMAIN" class="input mt-1" placeholder="iat" /></label>
                <p class="text-xs text-slate-500">使用讯飞 v2 听写协议。讯飞凭据也用于现有原文语音合成。</p>
              </template>
              <template v-else>
                <label class="block text-sm">API 基础地址<input v-model.trim="settings.ASR_BASE_URL" class="input mt-1" placeholder="https://服务域名/v1" /></label>
                <label class="block text-sm">识别模型 ID<input v-model.trim="settings.ASR_MODEL" class="input mt-1" placeholder="whisper-1 或服务商提供的模型 ID" /></label>
                <label class="block text-sm">API Key<input v-model.trim="settings.ASR_API_KEY" class="input mt-1" type="password" autocomplete="new-password" :placeholder="secretPlaceholder('ASR_API_KEY')" /></label>
              </template>
            </div>
          </div>
          <div class="flex flex-wrap gap-2">
            <button class="btn-primary" type="submit">{{ saving ? "保存中…" : "保存系统配置" }}</button>
            <button class="btn-secondary" type="button" :disabled="!webFields.length && !dirty" @click="restoreEnvironment">全部恢复环境配置</button>
          </div>
        </fieldset>
      </form>
      <p v-if="message" class="text-sm text-emerald-700">{{ message }}</p>
      <div class="border-t border-slate-200 pt-4">
        <h3 class="font-semibold text-brand">接口测试</h3>
        <p class="mt-1 text-sm text-slate-500">测试已保存的配置，始终调用真实服务，可能产生服务商用量费用。</p>
        <p v-if="dirty" class="mt-2 text-sm text-amber-700">配置已修改，请先保存后测试。</p>
        <div class="mt-3 grid gap-4 lg:grid-cols-2">
          <div class="space-y-3">
            <label class="block text-sm">模型测试文本<textarea v-model="testText" class="input mt-1" maxlength="2000"></textarea></label>
            <button class="btn-secondary" :disabled="dirty || saving || !!testing || testRecording || startingTestRecording || !testText.trim()" @click="test('llm')">{{ testing === 'llm' ? '调用中…' : '测试模型接口' }}</button>
            <div v-if="results.llm" class="rounded bg-slate-50 p-3 text-sm">
              <p>{{ results.llm.ok ? '调用成功' : '调用失败' }}<span v-if="results.llm.elapsed_ms != null"> · {{ results.llm.elapsed_ms }} ms</span></p>
              <p class="mt-2 whitespace-pre-wrap break-words">{{ results.llm.result?.message || results.llm.error }}</p>
            </div>
          </div>
          <div class="space-y-3">
            <label class="block text-sm">录音语种<select v-model="testLang" class="input mt-1" :disabled="testRecording || startingTestRecording || !!testing"><option value="zh-CN">中文</option><option value="ja-JP">日语</option><option value="en-US">英语</option></select></label>
            <p class="text-xs text-slate-500">选择语种后现场录音，系统会生成 16kHz、16bit、单声道 PCM；最长 30 秒，到时自动停止并识别。</p>
            <div class="flex flex-wrap gap-2">
              <button v-if="!testRecording" class="btn-secondary" type="button" :disabled="dirty || saving || !!testing || startingTestRecording" @click="startTestRecording">{{ startingTestRecording ? '正在打开麦克风…' : '开始现场录音' }}</button>
              <button v-else class="btn-danger" type="button" @click="stopTestRecording">停止录音并识别</button>
              <button v-if="testAudio && !testRecording" class="btn-secondary" type="button" :disabled="dirty || saving || !!testing || startingTestRecording" @click="test('asr')">{{ testing === 'asr' ? '识别中…' : '重新识别本次录音' }}</button>
            </div>
            <p v-if="testRecording" class="rounded bg-red-50 px-3 py-2 text-sm text-red-700" aria-live="polite">正在录音：{{ testElapsed }} / {{ maxTestRecordingSeconds }} 秒</p>
            <p v-if="testRecordingError" class="rounded bg-red-50 px-3 py-2 text-sm text-red-700">{{ testRecordingError }}</p>
            <div v-if="results.asr" class="rounded bg-slate-50 p-3 text-sm">
              <p>{{ results.asr.ok ? '调用成功' : '调用失败' }}<span v-if="results.asr.elapsed_ms != null"> · {{ results.asr.elapsed_ms }} ms</span></p>
              <p class="mt-2 whitespace-pre-wrap break-words">{{ results.asr.result?.transcript || results.asr.error || '服务已返回，未识别到文字' }}</p>
            </div>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>
