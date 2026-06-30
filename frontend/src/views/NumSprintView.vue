<script setup>
import { Pause, Play, RotateCcw } from "@lucide/vue";
import { computed, onBeforeUnmount, reactive, ref } from "vue";

const state = reactive({
  difficulty: "初级",
  mode: "视觉闪现",
  interval: 5,
  customText: "123　45　利用　結果　6789　注意",
});

const running = ref(false);
const display = ref("准备就绪");
const index = ref(0);
let timer = null;

const tokens = computed(() => {
  if (state.customText.trim()) {
    return state.customText
      .split(/[　\s]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
});

function generateSample() {
  const pools = {
    初级: ["23", "108", "4600", "2026", "98%", "三十七"],
    中级: ["2億5,000万円", "前年比12.8%", "第14次五年规划", "3万6千人"],
    高级: ["2026年6月30日", "1兆2,460億円", "0.037个百分点", "第3四半期同比增长18.6%"],
  };
  state.customText = pools[state.difficulty].join("　");
}

function tick() {
  if (index.value >= tokens.value.length) {
    display.value = "练习结束";
    stop(false);
    return;
  }
  display.value = tokens.value[index.value];
  index.value += 1;
  timer = window.setTimeout(tick, state.interval * 1000);
}

function start() {
  if (!tokens.value.length) return;
  running.value = true;
  index.value = 0;
  tick();
}

function stop(showStopped = true) {
  running.value = false;
  if (timer) window.clearTimeout(timer);
  timer = null;
  if (showStopped) display.value = "练习已停止";
}

function reset() {
  stop(false);
  index.value = 0;
  display.value = "准备就绪";
}

onBeforeUnmount(() => stop(false));
</script>

<template>
  <div class="grid gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
    <section class="panel space-y-4">
      <div>
        <h2 class="text-lg font-semibold text-brand">NumSprint 数字专项训练</h2>
        <p class="mt-1 text-sm text-slate-500">课前热身与数字、术语、短词快速反应训练。</p>
      </div>

      <div>
        <label class="field-label">难度</label>
        <select v-model="state.difficulty" class="input">
          <option>初级</option>
          <option>中级</option>
          <option>高级</option>
        </select>
      </div>
      <div>
        <label class="field-label">模式</label>
        <select v-model="state.mode" class="input">
          <option>视觉闪现</option>
          <option>音频模式</option>
          <option>混合模式</option>
        </select>
      </div>
      <div>
        <label class="field-label">间隔：{{ state.interval }} 秒</label>
        <input v-model.number="state.interval" class="w-full" min="3" max="15" type="range" />
      </div>
      <div>
        <label class="field-label">练习内容（全角空格或空格分隔）</label>
        <textarea v-model="state.customText" class="input min-h-32 resize-y"></textarea>
      </div>
      <div class="flex flex-wrap gap-2">
        <button class="btn-primary" :disabled="running || !tokens.length" @click="start"><Play class="h-4 w-4" />开始</button>
        <button class="btn-danger" :disabled="!running" @click="stop()"><Pause class="h-4 w-4" />停止</button>
        <button class="btn-secondary" @click="reset"><RotateCcw class="h-4 w-4" />重置</button>
        <button class="btn-secondary" @click="generateSample">生成样例</button>
      </div>
    </section>

    <section class="panel flex min-h-[420px] flex-col items-center justify-center">
      <div class="mb-5 text-sm text-slate-500">当前显示</div>
      <div class="flex min-h-36 w-full max-w-3xl items-center justify-center rounded-lg border-2 border-brand bg-slate-50 px-6 text-center font-mono text-5xl font-bold text-brand">
        {{ display }}
      </div>
      <div class="mt-5 text-sm text-slate-500">进度：{{ Math.min(index, tokens.length) }} / {{ tokens.length }}</div>
    </section>
  </div>
</template>
