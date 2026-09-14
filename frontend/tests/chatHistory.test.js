import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { webcrypto } from 'node:crypto';
import { parse, compileScript } from '@vue/compiler-sfc';
import { transformSync } from 'esbuild';

const require = createRequire(import.meta.url);
const vue = require('vue');
const { descriptor } = parse(readFileSync(new URL('../src/views/ChatAgent.vue', import.meta.url), 'utf8'));
const code = transformSync(compileScript(descriptor, { id: 'chat-history-test' }).content, { format: 'cjs' }).code;
const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
const detail = (id, text = '', version = 0) => ({ conversation: { id, title: id, version }, busy: false, has_more: false,
  turns: text ? [{ id: version || 1, request_id: `${id}-request`, sequence: version || 1, user_content: text, assistant_content: 'reply', status: 'completed' }] : [] });

function fixture(api) {
  const auth = vue.reactive({ user: { id: 1 } });
  const hooks = [];
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports,
    require: (name) => name === '../api' ? { api } : name === '../stores/auth' ? { useAuthStore: () => auth }
      : name === 'vue' ? { ...vue, onBeforeUnmount: (fn) => hooks.push(fn) } : require(name),
    crypto: webcrypto, window: { setTimeout: () => 1, clearTimeout() {} }, console });
  const scope = vue.effectScope();
  const ctx = scope.run(() => module.exports.default.setup({}, { expose() {} }));
  return { ctx, auth, stop: () => { hooks.forEach((fn) => fn()); scope.stop(); } };
}

test('out-of-order history loads and late replies never land in the wrong conversation', async () => {
  const slow = deferred();
  const reply = deferred();
  const api = { get: async (path) => path === '/llm/conversations' ? { data: { conversations: [], next_cursor: null } }
    : path.endsWith('/slow') ? slow.promise : { data: detail(path.split('/').at(-1)) }, post: () => reply.promise };
  const h = fixture(api);
  const first = h.ctx.selectConversation('slow');
  await h.ctx.selectConversation('fast');
  slow.resolve({ data: detail('slow', 'old history') });
  await first;
  assert.equal(h.ctx.selected.value.id, 'fast');
  assert.equal(h.ctx.messages.value.length, 0);
  h.ctx.input.value = 'question';
  const send = h.ctx.sendMessage();
  assert.equal(h.ctx.messages.value[0].content, 'question');
  await h.ctx.selectConversation('other');
  reply.resolve({ data: detail('fast', 'question', 1) });
  await send;
  assert.equal(h.ctx.selected.value.id, 'other');
  assert.equal(h.ctx.messages.value.length, 0);
  h.stop();
});

test('transport retry preserves request identity and sends no client history', async () => {
  const calls = [];
  const api = { get: async () => ({ data: { conversations: [], next_cursor: null } }),
    post: async (path, payload) => { calls.push(payload); if (calls.length === 1) throw new Error('network');
      return { data: detail('current', payload.message, 1) }; } };
  const h = fixture(api);
  h.ctx.applyDetail(detail('current'));
  h.ctx.input.value = 'same message';
  await h.ctx.sendMessage();
  await h.ctx.sendMessage(h.ctx.retryRequest.value);
  assert.equal(calls[0].request_id, calls[1].request_id);
  assert.equal(calls[0].conversation_id, 'current');
  assert.equal('messages' in calls[0], false);
  assert.equal(h.ctx.messages.value.length, 2);
  assert.equal(h.ctx.retryRequest.value, null);
  h.stop();
});

test('switching accounts immediately clears history and rejects earlier list responses', async () => {
  const old = deferred();
  let count = 0;
  const h = fixture({ get: async () => ++count === 1 ? old.promise : { data: { conversations: [], next_cursor: null } } });
  h.ctx.applyDetail(detail('private', 'private text', 1));
  h.auth.user = { id: 2 };
  await vue.nextTick();
  await flush();
  old.resolve({ data: { conversations: [{ id: 'old-user-conversation' }], next_cursor: null } });
  await flush();
  assert.equal(h.ctx.messages.value.length, 0);
  assert.equal(h.ctx.conversations.value.length, 0);
  assert.equal(h.ctx.selected.value, null);
  h.stop();
});

test('first message creates a conversation automatically and double sends do not duplicate it', async () => {
  const created = deferred();
  const calls = [];
  const h = fixture({ get: async () => ({ data: { conversations: [], next_cursor: null } }),
    post: async (path, payload) => {
      calls.push({ path, payload });
      if (path === '/llm/conversations') return created.promise;
      return { data: detail('auto-created', payload.message, 1) };
    } });
  await flush();
  h.ctx.input.value = 'first question';
  const send = h.ctx.sendMessage();
  await h.ctx.sendMessage();
  assert.equal(calls.length, 1);
  assert.equal(h.ctx.input.value, 'first question');
  created.resolve({ data: detail('auto-created') });
  await send;
  assert.equal(calls.length, 2);
  assert.equal(calls[1].path, '/llm/chat');
  assert.equal(calls[1].payload.conversation_id, 'auto-created');
  assert.equal(calls[1].payload.message, 'first question');
  assert.equal(h.ctx.conversations.value[0].id, 'auto-created');
  assert.equal(h.ctx.input.value, '');
  h.stop();
});

test('failed auto-creation preserves input and account changes cancel the pending send', async () => {
  const created = deferred();
  let count = 0;
  const h = fixture({ get: async () => ({ data: { conversations: [], next_cursor: null } }),
    post: async () => { if (++count === 1) throw new Error('creation failed'); return created.promise; } });
  h.ctx.input.value = 'unsent question';
  await h.ctx.sendMessage();
  assert.equal(h.ctx.input.value, 'unsent question');
  assert.equal(h.ctx.selected.value, null);
  assert.equal(h.ctx.loading.value, false);
  const retry = h.ctx.sendMessage();
  h.auth.user = { id: 2 };
  await vue.nextTick();
  created.resolve({ data: detail('previous-account') });
  await retry;
  assert.equal(count, 2, 'must not send a message to the previous account conversation');
  assert.equal(h.ctx.selected.value, null);
  assert.equal(h.ctx.input.value, '');
  h.stop();
});
