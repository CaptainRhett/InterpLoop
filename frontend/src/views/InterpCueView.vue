<script setup>
import { Pause, Play, SkipForward, Trash2 } from "@lucide/vue";
import { computed, onBeforeUnmount, reactive, ref } from "vue";
import { api } from "../api";
import { SPOKEN_LANGUAGES } from "../languages";
import { createCuePlayer, splitSentences } from "../utils/interpCue";

const state = reactive({
  text: "本日は、皆様の御参集を賜り、誠にありがとうございます。第一回中日企業経営交流商談会を開催できますことを大変うれしく思います。",
  lang: "ja-JP",
  interval: 8,
  voice: "",
});

const currentIndex = ref(-1);
const playing = ref(false);
const status = ref("准备就绪");
const sentences = computed(() => splitSentences(state.text));
const player = createCuePlayer({
  synthesize: async (payload, signal) => (await api.post("/tts", payload, { signal })).data,
  onIndex: (index) => { currentIndex.value = index; },
  onStatus: (value) => { status.value = value; },
  onPlaying: (value) => { playing.value = value; },
});

function play(single = false) {
  return player.play({
    sentences: [...sentences.value],
    index: single ? Math.max(0, Math.min(currentIndex.value, sentences.value.length - 1)) : 0,
    single,
    lang: state.lang,
    voice: state.voice,
    getInterval: () => state.interval,
  });
}

function playAll() {
  return play();
}

function playCurrent() {
  return play(true);
}

function stop() {
  player.stop();
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
      <p class="mt-1 text-sm text-slate-500">粘贴中文、日文或英文材料，逐句或整段朗读。</p>
      <textarea v-model="state.text" :disabled="playing" class="input mt-5 min-h-64 resize-y" placeholder="粘贴语料文本"></textarea>
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
        <select v-model="state.lang" :disabled="playing" class="input">
          <option v-for="item in SPOKEN_LANGUAGES" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
      </div>
      <div>
        <label class="field-label">句间停顿：{{ state.interval }} 秒</label>
        <input v-model.number="state.interval" class="w-full" min="3" max="30" type="range" />
        <p class="mt-1 text-xs text-slate-500">每句朗读结束后，再等待设定时长播放下一句。</p>
      </div>
      <div>
        <label class="field-label">语音名称（选填）</label>
        <input v-model.trim="state.voice" class="input" placeholder="填写讯飞控制台已授权的发音人" />
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
