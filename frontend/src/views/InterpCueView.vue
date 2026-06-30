<script setup>
import { Pause, Play, SkipForward, Trash2 } from "@lucide/vue";
import { computed, onBeforeUnmount, reactive, ref } from "vue";
import { api } from "../api";

const state = reactive({
  text: "本日は、皆様の御参集を賜り、誠にありがとうございます。第一回中日企業経営交流商談会を開催できますことを大変うれしく思います。",
  lang: "ja-JP",
  interval: 8,
  voice: "",
});

const currentIndex = ref(-1);
const playing = ref(false);
const status = ref("准备就绪");
let timer = null;

const sentences = computed(() =>
  state.text
    .split(/(?<=[。！？!?])|\n+/)
    .map((item) => item.trim())
    .filter(Boolean),
);

function speakBrowser(text) {
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = state.lang;
  utterance.rate = 0.9;
  window.speechSynthesis.speak(utterance);
}

async function speak(text) {
  try {
    const { data } = await api.post("/tts", { text, lang: state.lang, voice: state.voice });
    if (data.audio_base64) {
      const audio = new Audio(`data:${data.mime_type};base64,${data.audio_base64}`);
      audio.play();
    } else {
      speakBrowser(text);
    }
  } catch {
    speakBrowser(text);
  }
}

async function playNext() {
  if (currentIndex.value + 1 >= sentences.value.length) {
    status.value = "播放完成";
    playing.value = false;
    return;
  }
  currentIndex.value += 1;
  status.value = `正在播放第 ${currentIndex.value + 1} 句`;
  await speak(sentences.value[currentIndex.value]);
  timer = window.setTimeout(playNext, state.interval * 1000);
}

function playAll() {
  if (!sentences.value.length) return;
  playing.value = true;
  currentIndex.value = -1;
  playNext();
}

async function playCurrent() {
  if (!sentences.value.length) return;
  currentIndex.value = Math.max(currentIndex.value, 0);
  status.value = `正在播放第 ${currentIndex.value + 1} 句`;
  await speak(sentences.value[currentIndex.value]);
}

function stop() {
  playing.value = false;
  if (timer) window.clearTimeout(timer);
  timer = null;
  window.speechSynthesis?.cancel();
  status.value = "已停止";
}

function clearText() {
  stop();
  state.text = "";
  currentIndex.value = -1;
}

onBeforeUnmount(stop);
</script>

<template>
  <div class="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
    <section class="panel">
      <h2 class="text-lg font-semibold text-brand">InterpCue 语料播放</h2>
      <p class="mt-1 text-sm text-slate-500">粘贴中文或日文材料，逐句或整段朗读。</p>
      <textarea v-model="state.text" class="input mt-5 min-h-64 resize-y" placeholder="粘贴语料文本"></textarea>
      <div class="mt-4 rounded-md border border-slate-200 bg-slate-50 p-4">
        <div class="text-sm font-medium text-slate-600">当前句子</div>
        <p class="mt-2 min-h-16 text-lg leading-8 text-ink">
          {{ currentIndex >= 0 ? sentences[currentIndex] : "等待播放..." }}
        </p>
      </div>
    </section>

    <section class="panel space-y-4">
      <div>
        <label class="field-label">语种</label>
        <select v-model="state.lang" class="input">
          <option value="ja-JP">日语</option>
          <option value="zh-CN">中文</option>
        </select>
      </div>
      <div>
        <label class="field-label">句间停顿：{{ state.interval }} 秒</label>
        <input v-model.number="state.interval" class="w-full" min="3" max="30" type="range" />
      </div>
      <div>
        <label class="field-label">语音名称（选填）</label>
        <input v-model.trim="state.voice" class="input" placeholder="如 xiaoyan / x2_yumi" />
      </div>
      <div class="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">{{ status }}</div>
      <div class="grid grid-cols-2 gap-2">
        <button class="btn-primary" :disabled="playing || !sentences.length" @click="playAll"><Play class="h-4 w-4" />逐句播放</button>
        <button class="btn-secondary" :disabled="!sentences.length" @click="playCurrent"><SkipForward class="h-4 w-4" />播放当前</button>
        <button class="btn-danger" :disabled="!playing" @click="stop"><Pause class="h-4 w-4" />停止</button>
        <button class="btn-secondary" @click="clearText"><Trash2 class="h-4 w-4" />清空</button>
      </div>
      <div class="text-sm text-slate-500">共识别 {{ sentences.length }} 句。</div>
    </section>
  </div>
</template>
