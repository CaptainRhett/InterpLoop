<script setup>
import { Copy, RotateCcw } from "@lucide/vue";
import { computed, reactive, ref } from "vue";

const copied = ref(false);
const dimensions = [
  "发音准确性",
  "信息完整性",
  "句式与语法",
  "术语规范性",
  "表达流畅度",
  "语体匹配度",
  "跨文化适配",
  "立场表达精准性",
];

const form = reactive({
  role: "资深口译评估教师（政府外事方向）",
  taskType: "汉译日交替传译",
  material: "政治政论语篇",
  format: "结构化四段式（优点、主要问题、改进建议、参考译文）",
  level: "中级学习者（N2-N1）",
  strictness: 4,
  selected: ["发音准确性", "信息完整性", "句式与语法", "术语规范性", "表达流畅度"],
  extra: "",
});

const presets = {
  political: {
    role: "资深口译评估教师（政府外事方向）",
    taskType: "汉译日交替传译",
    material: "政治政论语篇",
    selected: ["术语规范性", "信息完整性", "句式与语法", "立场表达精准性"],
    extra: "请特别关注政治术语的固定译法，并避免无依据的迎合性赞美。",
  },
  business: {
    role: "日语商务口译专家（商务礼仪方向）",
    taskType: "汉译日交替传译",
    material: "商务研讨会司仪致辞",
    selected: ["句式与语法", "语体匹配度", "表达流畅度", "术语规范性"],
    extra: "请关注商务礼仪、敬语层次和司仪固定句型。",
  },
  englishBusiness: {
    role: "英语商务口译专家（国际商务方向）",
    taskType: "汉译英交替传译",
    material: "国际商务研讨会与企业交流",
    level: "中级学习者（CEFR B1-B2）",
    selected: ["信息完整性", "句式与语法", "语体匹配度", "表达流畅度", "术语规范性", "跨文化适配"],
    extra: "请关注商务英语的语域、术语搭配、冠词与时态，并检查表达是否自然得体。",
  },
  numeric: {
    role: "严格的口译考官（CATTI 标准评分）",
    taskType: "数字口译训练",
    material: "数字、年代、金额、统计数据",
    selected: ["信息完整性", "发音准确性", "表达流畅度"],
    extra: "请逐个数字核对准确性，并指出反应速度问题。",
  },
};

const prompt = computed(() => {
  const lines = [
    "【角色】",
    `你现在是${form.role}。`,
    "",
    "【任务背景】",
    `我是一名${form.level}，正在进行${form.taskType}训练，本次材料类型为：${form.material}。`,
    "",
    "【评估维度】",
    ...form.selected.map((item, index) => `${index + 1}. ${item}`),
    "",
    "【输出格式】",
    `${form.format}，严格程度 ${form.strictness}/5。`,
    "",
    "【评估原则】",
    "1. 保持客观，避免无依据的过度赞美。",
    "2. 关键错误请直接指出。",
    "3. 建议必须具体、可立即执行。",
  ];
  if (form.extra.trim()) lines.push("", "【补充说明】", form.extra.trim());
  lines.push("", "【我的口译内容】", "[在此粘贴口译录音转写文本]", "", "【原文】", "[在此粘贴原文]");
  return lines.join("\n");
});

function toggleDimension(item) {
  if (form.selected.includes(item)) {
    form.selected = form.selected.filter((value) => value !== item);
  } else {
    form.selected.push(item);
  }
}

function applyPreset(key) {
  Object.assign(form, presets[key]);
}

function reset() {
  form.role = "资深口译评估教师（政府外事方向）";
  form.taskType = "汉译日交替传译";
  form.material = "政治政论语篇";
  form.format = "结构化四段式（优点、主要问题、改进建议、参考译文）";
  form.level = "中级学习者（N2-N1）";
  form.strictness = 4;
  form.selected = dimensions.slice(0, 5);
  form.extra = "";
}

async function copyPrompt() {
  await navigator.clipboard.writeText(prompt.value);
  copied.value = true;
  window.setTimeout(() => (copied.value = false), 1600);
}
</script>

<template>
  <div class="grid gap-5 xl:grid-cols-[420px_minmax(0,1fr)]">
    <section class="panel space-y-4">
      <div>
        <h2 class="text-lg font-semibold text-brand">PromptForge 提示词设置</h2>
        <p class="mt-1 text-sm text-slate-500">生成可复制的口译评价提示词，也会被闭环练习复用。</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <button class="btn-secondary" @click="applyPreset('political')">政治语篇</button>
        <button class="btn-secondary" @click="applyPreset('business')">商务研讨会</button>
        <button class="btn-secondary" @click="applyPreset('englishBusiness')">中英商务</button>
        <button class="btn-secondary" @click="applyPreset('numeric')">数字训练</button>
      </div>
      <div>
        <label class="field-label">角色设定</label>
        <select v-model="form.role" class="input">
          <option>资深口译评估教师（政府外事方向）</option>
          <option>日语商务口译专家（商务礼仪方向）</option>
          <option>日本语言学博士（翻译教学方向）</option>
          <option>英语商务口译专家（国际商务方向）</option>
          <option>英语语言与翻译教学专家</option>
          <option>鼓励型口译陪练（情感支持型）</option>
          <option>严格的口译考官（CATTI 标准评分）</option>
        </select>
      </div>
      <div class="grid gap-3 sm:grid-cols-2">
        <div>
          <label class="field-label">任务类型</label>
          <select v-model="form.taskType" class="input">
            <option>汉译日交替传译</option>
            <option>日译汉交替传译</option>
            <option>汉译日视译</option>
            <option>日译汉视译</option>
            <option>汉译英交替传译</option>
            <option>英译汉交替传译</option>
            <option>汉译英视译</option>
            <option>英译汉视译</option>
            <option>数字口译训练</option>
          </select>
        </div>
        <div>
          <label class="field-label">学习者水平</label>
          <select v-model="form.level" class="input">
            <option>初学者（N3-N2）</option>
            <option>中级学习者（N2-N1）</option>
            <option>高级学习者（N1以上）</option>
            <option>初级学习者（CEFR A2-B1）</option>
            <option>中级学习者（CEFR B1-B2）</option>
            <option>高级学习者（CEFR C1-C2）</option>
          </select>
        </div>
      </div>
      <div>
        <label class="field-label">评价维度</label>
        <div class="flex flex-wrap gap-2">
          <button v-for="item in dimensions" :key="item" class="chip" :class="{ 'chip-active': form.selected.includes(item) }" @click="toggleDimension(item)">
            {{ item }}
          </button>
        </div>
      </div>
      <div>
        <label class="field-label">严格程度：{{ form.strictness }}/5</label>
        <input v-model.number="form.strictness" class="w-full" min="1" max="5" type="range" />
      </div>
      <div>
        <label class="field-label">补充说明</label>
        <textarea v-model="form.extra" class="input min-h-24 resize-y"></textarea>
      </div>
    </section>

    <section class="panel">
      <div class="mb-3 flex items-center justify-between">
        <div>
          <h2 class="text-lg font-semibold text-brand">生成结果</h2>
          <p class="text-sm text-slate-500">字数：{{ prompt.length }}</p>
        </div>
        <div class="flex gap-2">
          <button class="btn-secondary" @click="reset"><RotateCcw class="h-4 w-4" />重置</button>
          <button class="btn-success" @click="copyPrompt"><Copy class="h-4 w-4" />{{ copied ? "已复制" : "复制" }}</button>
        </div>
      </div>
      <pre class="min-h-[520px] whitespace-pre-wrap rounded-lg bg-slate-900 p-5 text-sm leading-7 text-slate-100">{{ prompt }}</pre>
    </section>
  </div>
</template>
