<script setup>
import {
  Bot,
  MessageSquare,
  Send,
  Sparkles,
  Trash2,
  User,
} from "@lucide/vue";
import { nextTick, ref } from "vue";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();

const input = ref("");
const sending = ref(false);
const error = ref("");
const messagesContainer = ref(null);

const messages = ref([
  {
    role: "assistant",
    content: "你好，我是 AI 学习助手。有什么问题都可以直接问我。",
  },
]);

const suggestions = [
  "帮我解释一下今天学习的知识点",
  "帮我润色一段中文",
  "帮我翻译一段日语",
  "给我制定一个学习计划",
];

async function scrollToBottom() {
  await nextTick();
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop =
      messagesContainer.value.scrollHeight;
  }
}

async function sendMessage(text = null) {
  const content = (text ?? input.value).trim();

  if (!content || sending.value) return;

  error.value = "";

  messages.value.push({
    role: "user",
    content,
  });

  input.value = "";

  await scrollToBottom();

  sending.value = true;

  try {
    /*
     * 不建议把最开始的欢迎语传给后端，
     * 所以只传真正产生的对话消息。
     */
    const conversation = messages.value
      .filter(
        (item, index) =>
          !(index === 0 && item.role === "assistant")
      )
      .map((item) => ({
        role: item.role,
        content: item.content,
      }));

    const response = await fetch("/api/llm/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({
        messages: conversation,
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "请求失败");
    }

    messages.value.push({
      role: "assistant",
      content: data.message,
    });
  } catch (err) {
    error.value = err.message || "AI 服务暂时不可用，请稍后重试";
  } finally {
    sending.value = false;
    await scrollToBottom();
  }
}

function clearConversation() {
  messages.value = [
    {
      role: "assistant",
      content: "你好，我是 AI 学习助手。有什么问题都可以直接问我。",
    },
  ];

  input.value = "";
  error.value = "";
}

function handleKeydown(event) {
  // Enter 发送
  // Shift + Enter 换行
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}
</script>

<template>
  <div class="grid gap-5 lg:grid-cols-[300px_minmax(0,1fr)]">
    <!-- 左侧信息栏 -->
    <section class="panel">
      <div class="flex items-center gap-2 text-brand">
        <Sparkles class="h-5 w-5" />
        <h2 class="font-semibold">AI 学习助手</h2>
      </div>

      <p class="mt-3 text-sm leading-6 text-slate-500">
        你可以在这里与 AI 进行自由对话，包括语言学习、翻译、
        知识问答、写作辅助等。
      </p>

      <div class="mt-5 border-t border-slate-200 pt-4">
        <h3 class="mb-3 text-sm font-semibold text-brand">
          当前用户
        </h3>

        <div class="space-y-2 text-sm">
          <div>
            <span class="text-slate-500">姓名：</span>
            {{ auth.user?.name || "用户" }}
          </div>

          <div>
            <span class="text-slate-500">角色：</span>
            {{
              {
                student: "学生",
                teacher: "教师",
                admin: "管理员",
              }[auth.user?.role] || "用户"
            }}
          </div>
        </div>
      </div>

      <div class="mt-5 border-t border-slate-200 pt-4">
        <h3 class="mb-3 text-sm font-semibold text-brand">
          你可以试试
        </h3>

        <div class="space-y-2">
          <button
            v-for="item in suggestions"
            :key="item"
            type="button"
            class="w-full rounded-md bg-slate-50 px-3 py-2 text-left text-sm text-slate-600 transition hover:bg-slate-100 hover:text-brand"
            @click="sendMessage(item)"
          >
            {{ item }}
          </button>
        </div>
      </div>

      <div class="mt-5 border-t border-slate-200 pt-4">
        <button
          type="button"
          class="flex w-full items-center justify-center gap-2 rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-600 transition hover:bg-slate-50"
          @click="clearConversation"
        >
          <Trash2 class="h-4 w-4" />
          新建对话
        </button>
      </div>
    </section>

    <!-- 主聊天区 -->
    <section class="panel flex min-h-[680px] flex-col">
      <!-- 标题 -->
      <div
        class="flex items-center justify-between border-b border-slate-200 pb-4"
      >
        <div class="flex items-center gap-2 text-brand">
          <MessageSquare class="h-5 w-5" />
          <h2 class="font-semibold">智能体对话</h2>
        </div>

        <div class="flex items-center gap-2 text-xs text-slate-400">
          <span
            class="inline-block h-2 w-2 rounded-full bg-emerald-500"
          />
          AI 服务
        </div>
      </div>

      <!-- 消息区域 -->
      <div
        ref="messagesContainer"
        class="flex-1 space-y-5 overflow-y-auto py-5"
      >
        <div
          v-for="(message, index) in messages"
          :key="index"
          class="flex gap-3"
          :class="
            message.role === 'user'
              ? 'flex-row-reverse'
              : ''
          "
        >
          <!-- 头像 -->
          <div
            class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
            :class="
              message.role === 'assistant'
                ? 'bg-brand/10 text-brand'
                : 'bg-slate-100 text-slate-600'
            "
          >
            <Bot
              v-if="message.role === 'assistant'"
              class="h-5 w-5"
            />
            <User v-else class="h-5 w-5" />
          </div>

          <!-- 消息 -->
          <div
            class="max-w-[80%] rounded-xl px-4 py-3 text-sm leading-7"
            :class="
              message.role === 'assistant'
                ? 'bg-slate-50 text-slate-700'
                : 'bg-brand text-white'
            "
          >
            <div class="whitespace-pre-wrap break-words">
              {{ message.content }}
            </div>
          </div>
        </div>

        <!-- AI 正在回复 -->
        <div v-if="sending" class="flex gap-3">
          <div
            class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand/10 text-brand"
          >
            <Bot class="h-5 w-5" />
          </div>

          <div
            class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-500"
          >
            <div class="flex items-center gap-1">
              <span
                class="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400"
              />
              <span
                class="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:150ms]"
              />
              <span
                class="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:300ms]"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- 错误提示 -->
      <p
        v-if="error"
        class="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700"
      >
        {{ error }}
      </p>

      <!-- 输入区 -->
      <div class="border-t border-slate-200 pt-4">
        <div
          class="rounded-xl border border-slate-200 bg-white p-3 transition focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/10"
        >
          <textarea
            v-model="input"
            rows="3"
            class="w-full resize-none border-0 bg-transparent text-sm leading-6 text-slate-700 outline-none placeholder:text-slate-400"
            placeholder="输入你的问题……"
            :disabled="sending"
            @keydown="handleKeydown"
          />

          <div class="mt-2 flex items-center justify-between">
            <span class="text-xs text-slate-400">
              Enter 发送 · Shift + Enter 换行
            </span>

            <button
              type="button"
              class="btn-primary flex items-center gap-2"
              :disabled="sending || !input.trim()"
              @click="sendMessage()"
            >
              <Send class="h-4 w-4" />
              {{ sending ? "生成中..." : "发送" }}
            </button>
          </div>
        </div>

        <p class="mt-2 text-center text-xs text-slate-400">
          AI 生成内容可能存在错误，请结合实际情况判断。
        </p>
      </div>
    </section>
  </div>
</template>