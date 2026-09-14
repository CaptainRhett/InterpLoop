<script setup>
import { Bot, MessageSquare, Send, Plus, User } from "@lucide/vue";
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { useAuthStore } from "../stores/auth";
import { api } from "../api";

const auth = useAuthStore();
const input = ref("");
const sending = ref(false);
const loading = ref(false);
const error = ref("");
const messagesContainer = ref(null);
const conversations = ref([]);
const nextCursor = ref(null);
const selected = ref(null);
const turns = ref([]);
const busy = ref(false);
const hasMore = ref(false);
const retryRequest = ref(null);
let epoch = 0;
let accountEpoch = 0;
let pollTimer = null;
const messages = computed(() => {
  const stored = turns.value.flatMap((turn) => [
  { id: `${turn.id}-user`, role: "user", content: turn.user_content },
  ...(turn.assistant_content ? [{ id: `${turn.id}-assistant`, role: "assistant", content: turn.assistant_content }] : []),
]);
  const pending = retryRequest.value;
  if (pending && selected.value && pending.conversation_id === selected.value.id && !turns.value.some((turn) => turn.request_id === pending.request_id)) {
    stored.push({ id: `pending-${pending.request_id}`, role: "user", content: pending.message });
  }
  return stored;
});
const retryableTurn = computed(() => {
  const last = turns.value.at(-1);
  return last && last.status !== "completed" && !busy.value ? last : null;
});

async function scrollToBottom() {
  await nextTick();
  if (messagesContainer.value) messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
}
function updateSummary(conversation) {
  conversations.value = conversations.value.map((item) => item.id === conversation.id ? conversation : item);
}
function applyDetail(data, merge = false) {
  selected.value = data.conversation;
  turns.value = merge ? [...new Map([...turns.value, ...data.turns].map((turn) => [turn.id, turn])).values()].sort((a, b) => a.sequence - b.sequence) : data.turns;
  busy.value = data.busy;
  if (!merge) hasMore.value = data.has_more;
  updateSummary(data.conversation);
  window.clearTimeout(pollTimer);
  if (data.busy) {
    const token = epoch;
    const id = data.conversation.id;
    pollTimer = window.setTimeout(async () => {
      try {
        const { data: latest } = await api.get(`/llm/conversations/${id}`);
        if (epoch === token && selected.value?.id === id) applyDetail(latest, true);
      } catch {
        if (epoch === token) { busy.value = false; error.value = "历史刷新失败，请重新选择会话刷新状态"; }
      }
    }, 2000);
  }
}
async function loadList(more = false) {
  const token = accountEpoch;
  try {
    const { data } = await api.get("/llm/conversations", { params: more ? { before: nextCursor.value } : {} });
    if (token !== accountEpoch) return;
    conversations.value = more ? [...new Map([...conversations.value, ...data.conversations].map((item) => [item.id, item])).values()] : data.conversations;
    nextCursor.value = data.next_cursor;
  } catch (err) {
    if (token === accountEpoch) error.value = err.response?.data?.error || "历史加载失败";
  }
}
async function selectConversation(id) {
  const token = ++epoch;
  window.clearTimeout(pollTimer);
  selected.value = null;
  turns.value = [];
  hasMore.value = false;
  retryRequest.value = null;
  busy.value = false;
  input.value = "";
  error.value = "";
  loading.value = true;
  try {
    const { data } = await api.get(`/llm/conversations/${id}`);
    if (epoch !== token) return;
    applyDetail(data);
    await scrollToBottom();
  } catch (err) {
    if (epoch === token) error.value = err.response?.data?.error || "会话加载失败";
  } finally { if (epoch === token) loading.value = false; }
}
async function newConversation(preserveInput = false) {
  if (loading.value || sending.value) return;
  const token = ++epoch;
  window.clearTimeout(pollTimer);
  loading.value = true;
  error.value = "";
  try {
    const { data } = await api.post("/llm/conversations");
    if (epoch !== token) return;
    conversations.value.unshift(data.conversation);
    if (!preserveInput) input.value = "";
    retryRequest.value = null;
    applyDetail(data);
    return data.conversation.id;
  } catch (err) {
    if (epoch === token) error.value = err.response?.data?.error || "创建会话失败";
  } finally { if (epoch === token) loading.value = false; }
}
async function loadEarlier() {
  if (!selected.value || loading.value || !turns.value.length) return;
  const token = epoch;
  loading.value = true;
  try {
    const { data } = await api.get(`/llm/conversations/${selected.value.id}`, { params: { before: turns.value[0].sequence } });
    if (token !== epoch) return;
    turns.value = [...data.turns, ...turns.value];
    hasMore.value = data.has_more;
  } catch (err) {
    if (token === epoch) error.value = err.response?.data?.error || "历史加载失败";
  } finally { if (token === epoch) loading.value = false; }
}
function requestId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
async function sendMessage(retry = null) {
  if (sending.value || loading.value || busy.value) return;
  const content = retry?.message ?? input.value.trim();
  if (!content || content.length > 8000) return;
  if (!selected.value) {
    const id = await newConversation(true);
    if (!id || selected.value?.id !== id) return;
  }
  // Retain this ID for transport retries. Never derive identities from message text.
  const payload = retry || { conversation_id: selected.value.id, request_id: requestId(),
    expected_version: selected.value.version, message: content };
  const token = epoch;
  const ownerToken = accountEpoch;
  sending.value = true;
  error.value = "";
  retryRequest.value = payload;
  try {
    const { data } = await api.post("/llm/chat", payload);
    if (ownerToken !== accountEpoch) return;
    updateSummary(data.conversation);
    if (token !== epoch) return;
    applyDetail(data, true);
    retryRequest.value = null;
    input.value = "";
    await scrollToBottom();
  } catch (err) {
    if (token !== epoch || ownerToken !== accountEpoch) return;
    error.value = err.response?.data?.error || "发送状态尚未确认，可使用原请求重试";
    if (err.response?.data?.conversation) {
      applyDetail(err.response.data, true);
      retryRequest.value = null;
      input.value = "";
    } else if (err.response) {
      retryRequest.value = null;
      if (err.response.status === 409) {
        const { data } = await api.get(`/llm/conversations/${payload.conversation_id}`).catch(() => ({ data: null }));
        if (data && token === epoch) {
          applyDetail(data, true);
          if (data.turns.some((turn) => turn.request_id === payload.request_id)) input.value = "";
        }
      }
    }
  } finally { if (ownerToken === accountEpoch) sending.value = false; }
}
function retryTurn() {
  const turn = retryableTurn.value;
  if (turn) return sendMessage({ conversation_id: selected.value.id, request_id: turn.request_id,
    expected_version: selected.value.version, message: turn.user_content });
}
function handleKeydown(event) {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    if (!retryRequest.value) sendMessage();
  }
}
watch(() => auth.user?.id, async () => {
  accountEpoch += 1;
  epoch += 1;
  window.clearTimeout(pollTimer);
  conversations.value = [];
  selected.value = null;
  turns.value = [];
  input.value = "";
  retryRequest.value = null;
  sending.value = false;
  busy.value = false;
  loading.value = false;
  error.value = "";
  nextCursor.value = null;
  hasMore.value = false;
  if (auth.user) await loadList();
}, { immediate: true });
onBeforeUnmount(() => { accountEpoch += 1; epoch += 1; window.clearTimeout(pollTimer); });
</script>

<template>
  <div class="grid gap-5 lg:grid-cols-[300px_minmax(0,1fr)]">
    <section class="panel flex max-h-[780px] flex-col">
      <div class="flex items-center justify-between gap-2">
        <h2 class="font-semibold text-brand">对话历史</h2>
        <button class="btn-secondary" :disabled="sending || loading" @click="newConversation()"><Plus class="h-4 w-4" />新建</button>
      </div>
      <p class="mt-2 text-xs text-slate-500">历史自动保存，仅当前账号可见。</p>
      <div class="mt-4 flex-1 space-y-2 overflow-y-auto">
        <button v-for="item in conversations" :key="item.id" class="w-full rounded border px-3 py-3 text-left text-sm"
          :class="selected?.id === item.id ? 'border-brand bg-blue-50 text-brand' : 'border-slate-200 hover:bg-slate-50'"
          @click="selectConversation(item.id)">
          <span class="block truncate font-medium">{{ item.title }}</span>
          <span class="mt-1 block text-xs text-slate-400">{{ item.updated_at.slice(0, 19).replace('T', ' ') }}</span>
        </button>
        <p v-if="!conversations.length" class="py-5 text-sm text-slate-500">暂无历史，直接发送消息即可开始对话。</p>
        <button v-if="nextCursor" class="btn-secondary w-full" @click="loadList(true)">更多会话</button>
      </div>
      <button class="btn-secondary mt-3" @click="loadList()">刷新历史</button>
    </section>

    <!-- 主聊天区 -->
    <section class="panel flex h-[780px] min-h-[500px] flex-col">
      <!-- 标题 -->
      <div
        class="flex items-center justify-between border-b border-slate-200 pb-4"
      >
        <div class="flex items-center gap-2 text-brand">
          <MessageSquare class="h-5 w-5" />
          <h2 class="font-semibold">{{ selected?.title || "智能体对话" }}</h2>
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
        <p v-if="loading" class="text-sm text-slate-500">正在加载历史…</p>
        <p v-if="!selected && !loading" class="text-sm text-slate-500">直接输入并发送即可开始新对话，也可以从左侧继续历史会话。</p>
        <button v-if="hasMore" class="btn-secondary" :disabled="loading" @click="loadEarlier">加载更早消息</button>
        <p v-if="selected && !messages.length && !loading" class="text-sm text-slate-500">有什么问题都可以直接问我。</p>
        <div
          v-for="message in messages"
          :key="message.id"
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
        <div v-if="busy || (sending && retryRequest && selected && retryRequest.conversation_id === selected.id)" class="flex gap-3">
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

      <button v-if="retryRequest && !sending" class="btn-secondary mb-3" @click="sendMessage(retryRequest)">使用原请求重试发送</button>
      <button v-else-if="retryableTurn && !sending" class="btn-secondary mb-3" @click="retryTurn">重试上一条回复</button>
      <!-- 输入区 -->
      <div class="border-t border-slate-200 pt-4">
        <div
          class="rounded-xl border border-slate-200 bg-white p-3 transition focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/10"
        >
          <textarea
            v-model="input"
            rows="3"
            maxlength="8000"
            class="w-full resize-none border-0 bg-transparent text-sm leading-6 text-slate-700 outline-none placeholder:text-slate-400"
            placeholder="输入你的问题……"
            :disabled="sending || busy || loading || !!retryRequest"
            @keydown="handleKeydown"
          />

          <div class="mt-2 flex items-center justify-between">
            <span class="text-xs text-slate-400">
              Enter 发送 · Shift + Enter 换行
            </span>

            <button
              type="button"
              class="btn-primary flex items-center gap-2"
              :disabled="sending || busy || loading || !!retryRequest || !input.trim()"
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
