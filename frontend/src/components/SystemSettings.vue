<script setup>
import { computed, onMounted, reactive, ref } from "vue";
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
const testFile = ref(null);
const results = reactive({ llm: null, asr: null });
const secrets = ["DOUBAO_API_KEY", "ASR_API_KEY", "XUNFEI_API_KEY", "XUNFEI_API_SECRET"];

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
  if (dirty.value || saving.value || testing.value) return;
  testing.value = service;
  results[service] = null;
  try {
    let body = { text: testText.value };
    if (service === "asr") {
      body = new FormData();
      body.append("audio", testFile.value);
      body.append("lang", testLang.value);
    }
    results[service] = (await api.post(`/admin/system/test/${service}`, body, { timeout: 90000 })).data;
  } catch (err) {
    results[service] = err.response?.data || { ok: false, error: "连接失败或测试超时，请稍后重试" };
  } finally { testing.value = ""; }
}
function secretPlaceholder(key) {
  return configured.value[key] ? "已配置，留空保留；输入新值替换" : "尚未配置，请填写";
}
onMounted(load);
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
        <fieldset :disabled="saving || !!testing" class="space-y-4">
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
            <button class="btn-secondary" :disabled="dirty || saving || !!testing || !testText.trim()" @click="test('llm')">{{ testing === 'llm' ? '调用中…' : '测试模型接口' }}</button>
            <div v-if="results.llm" class="rounded bg-slate-50 p-3 text-sm">
              <p>{{ results.llm.ok ? '调用成功' : '调用失败' }}<span v-if="results.llm.elapsed_ms != null"> · {{ results.llm.elapsed_ms }} ms</span></p>
              <p class="mt-2 whitespace-pre-wrap break-words">{{ results.llm.result?.message || results.llm.error }}</p>
            </div>
          </div>
          <div class="space-y-3">
            <label class="block text-sm">录音语种<select v-model="testLang" class="input mt-1"><option value="zh-CN">中文</option><option value="ja-JP">日语</option><option value="en-US">英语</option></select></label>
            <label class="block text-sm">测试录音<input type="file" class="mt-1 block w-full" accept=".pcm,.wav,.mp3,.m4a,.webm,.ogg,.flac,.mp4" @change="testFile = $event.target.files[0] || null" /></label>
            <p class="text-xs text-slate-500">文件不超过 1 MB。讯飞仅支持不超过 30 秒的 16kHz、16bit、单声道 PCM/WAV。</p>
            <button class="btn-secondary" :disabled="dirty || saving || !!testing || !testFile" @click="test('asr')">{{ testing === 'asr' ? '识别中…' : '测试识别接口' }}</button>
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
