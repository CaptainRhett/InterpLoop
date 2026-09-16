import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { parse, compileScript } from '@vue/compiler-sfc';
import { transformSync } from 'esbuild';

const require = createRequire(import.meta.url);
const vue = require('vue');
const pinia = require('pinia');
const flush = async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); };
const storeCode = transformSync(readFileSync(new URL('../src/stores/auth.js', import.meta.url), 'utf8'), { format: 'cjs' }).code;
const { descriptor } = parse(readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8'));
const appCode = transformSync(compileScript(descriptor, { id: 'guest-app-test' }).content, { format: 'cjs' }).code;

function load(code, imports, globals = {}) {
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports, require: (name) => imports[name] || require(name), ...globals });
  return module.exports;
}

function fixture(user) {
  const clock = { time: Date.now() };
  class ClockDate extends Date {
    static now() { return clock.time; }
  }
  const routes = [];
  const timers = new Map();
  const listeners = new Map();
  const hooks = [];
  let nextTimer = 0;
  let rejected;
  let ejected = false;
  let channel;
  const broadcasts = [];
  const api = {
    post: async (path) => path.startsWith('/auth/guest') ? { data: { user } } : { data: {} },
    get: async () => ({ data: { user, contexts: [] } }),
    interceptors: { response: { use: (_success, onError) => { rejected = onError; return 1; }, eject: () => { ejected = true; } } },
  };
  pinia.setActivePinia(pinia.createPinia());
  const auth = load(storeCode, { '../api': { api } }).useAuthStore();
  const window = {
    BroadcastChannel: class {
      constructor() { channel = this; }
      postMessage(data) { broadcasts.push(data); }
      close() {}
    },
    setTimeout: (fn, delay) => { timers.set(++nextTimer, { fn, delay }); return nextTimer; },
    clearTimeout: (id) => timers.delete(id),
    addEventListener: (name, fn) => listeners.set(name, fn),
    removeEventListener: (name) => listeners.delete(name),
  };
  const component = load(appCode, {
    vue: { ...vue, onBeforeUnmount: (fn) => hooks.push(fn) },
    'vue-router': { useRouter: () => ({ replace: (route) => routes.push(route) }) },
    './api': { api }, './stores/auth': { useAuthStore: () => auth },
  }, { window, Date: ClockDate });
  const scope = vue.effectScope();
  scope.run(() => component.default.setup({}, { expose() {} }));
  return { auth, api, routes, timers, listeners, broadcasts,
    advance: (milliseconds) => { clock.time += milliseconds; },
    receive: (data) => channel.onmessage({ data }),
    reject: (error) => rejected(error),
    stop: () => { hooks.forEach((fn) => fn()); scope.stop(); assert.equal(ejected, true); },
  };
}

const guest = () => ({ id: 2, role: 'guest', guest_session_id: 'trial-2', guest_expires_at: new Date(Date.now() + 7200000).toISOString() });

test('guest entry and page reload restore the same temporary identity; expiry clears it and returns to login', async () => {
  const h = fixture(guest());
  await h.auth.enterGuest();
  await vue.nextTick();
  assert.equal(h.auth.isGuest, true);
  assert.equal(h.auth.isAdmin, false);
  assert.equal(h.auth.isTeacher, false);
  const deadline = h.auth.user.guest_expires_at;
  await h.auth.loadMe();
  await vue.nextTick();
  assert.equal(h.auth.user.guest_expires_at, deadline);
  assert.equal(h.timers.size, 1);
  const timer = [...h.timers.values()][0];
  assert.ok(timer.delay > 7190000 && timer.delay <= 7200000);
  h.auth.user.guest_expires_at = new Date(Date.now() - 1000).toISOString();
  await vue.nextTick();
  await [...h.timers.values()][0].fn();
  await vue.nextTick();
  assert.equal(h.auth.user, null);
  assert.equal(h.auth.contexts.length, 0);
  assert.equal(h.routes.at(-1).name, 'login');
  assert.equal(h.routes.at(-1).query.guest, 'expired');
  assert.equal(h.timers.size, 0);
  h.stop();
});

test('revoked guest sessions clear local state on 401 while failed password login preserves a valid guest', async () => {
  const h = fixture(guest());
  await h.auth.enterGuest();
  const loginError = { response: { status: 401 }, config: { url: '/auth/login' } };
  await assert.rejects(h.reject(loginError));
  assert.equal(h.auth.isGuest, true);
  await assert.rejects(h.reject({ response: { status: 401, data: { code: 'GUEST_SESSION_EXPIRED' } }, config: { url: '/llm/conversations' } }));
  assert.equal(h.auth.user, null);
  assert.equal(h.routes.length, 1);
  h.stop();
});

test('regular accounts have no guest expiry timer and are not cleared by the guest handler', async () => {
  const h = fixture({ id: 1, role: 'student', guest_expires_at: null });
  await h.auth.loadMe();
  await vue.nextTick();
  assert.equal(h.timers.size, 0);
  await assert.rejects(h.reject({ response: { status: 401 } }));
  assert.equal(h.auth.user.id, 1);
  assert.equal(h.routes.length, 0);
  await h.auth.logout();
  assert.equal(h.auth.user, null);
  h.stop();
});

test('ending a guest trial clears other tabs without affecting a different trial', async () => {
  const user = guest();
  const first = fixture(user);
  const second = fixture(user);
  const other = fixture({ ...guest(), id: 3, guest_session_id: 'trial-3' });
  await first.auth.enterGuest();
  await second.auth.enterGuest();
  await other.auth.enterGuest();
  await vue.nextTick();
  await first.auth.logout();
  await vue.nextTick();
  const ended = first.broadcasts.filter((message) => message.type === 'guest-ended');
  assert.equal(ended.length, 1);
  second.receive(ended[0]);
  other.receive(ended[0]);
  assert.equal(second.auth.user, null);
  assert.equal(second.routes.at(-1).query.guest, 'expired');
  assert.equal(other.auth.user.id, 3);
  first.stop(); second.stop(); other.stop();
});

test('renewal preserves identity and extends other tabs without logging them out', async () => {
  const user = guest();
  const first = fixture({ ...user });
  const second = fixture({ ...user });
  await first.auth.enterGuest();
  await second.auth.enterGuest();
  const expiresAt = new Date(Date.parse(user.guest_expires_at) + 3600000).toISOString();
  first.api.post = async () => ({ data: { user: { ...user, guest_expires_at: expiresAt } } });
  await first.auth.renewGuest();
  await vue.nextTick();
  assert.equal(first.auth.user.guest_session_id, user.guest_session_id);
  assert.equal(first.auth.user.guest_expires_at, expiresAt);
  assert.equal(first.broadcasts.some((message) => message.type === 'guest-ended'), false);
  second.receive(first.broadcasts.at(-1));
  assert.equal(second.auth.user.guest_expires_at, expiresAt);
  assert.equal(second.routes.length, 0);
  first.auth.updateGuestExpiry(user.guest_expires_at);
  assert.equal(first.auth.user.guest_expires_at, expiresAt, 'late responses must not shorten the renewed deadline');
  first.stop(); second.stop();
});

test('expired local deadline is checked against the server before discarding a renewed trial', async () => {
  const user = guest();
  const h = fixture({ ...user });
  await h.auth.enterGuest();
  h.auth.user.guest_expires_at = new Date(Date.now() - 1000).toISOString();
  h.api.get = async () => ({ data: { user } });
  await vue.nextTick();
  await [...h.timers.values()][0].fn();
  assert.equal(h.auth.user.guest_expires_at, user.guest_expires_at);
  assert.equal(h.routes.length, 0);
  h.stop();
});

test('late renewal response cannot restore a trial after logout', async () => {
  const h = fixture(guest());
  await h.auth.enterGuest();
  let resolve;
  const user = { ...h.auth.user };
  h.api.post = (path) => path.endsWith('/renew') ? new Promise((done) => { resolve = done; }) : Promise.resolve({ data: {} });
  const pending = h.auth.renewGuest();
  await h.auth.logout();
  resolve({ data: { user } });
  await pending;
  assert.equal(h.auth.user, null);
  assert.equal(h.auth.renewingGuest, false);
  h.stop();
});

test('activity renews the trial at most once per minute and idle pages do not renew', async () => {
  const user = guest();
  const h = fixture(user);
  await h.auth.enterGuest();
  await vue.nextTick();
  let renewals = 0;
  h.api.post = async (path) => {
    assert.equal(path, '/auth/guest/renew');
    renewals += 1;
    return { data: { user: { ...user, guest_expires_at: new Date(Date.now() + 7200000 + renewals * 60000).toISOString() } } };
  };
  h.advance(61000);
  assert.equal(renewals, 0, 'elapsed time alone must not keep an idle guest alive');
  h.listeners.get('keydown')();
  await flush();
  assert.equal(renewals, 1);
  h.listeners.get('pointerdown')();
  h.listeners.get('input')();
  assert.equal(renewals, 1);
  h.advance(61000);
  h.listeners.get('focus')();
  await flush();
  assert.equal(renewals, 2);
  assert.equal(h.routes.length, 0);
  h.stop();
});
