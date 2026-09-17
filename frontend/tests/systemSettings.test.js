import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { parse, compileScript } from '@vue/compiler-sfc';
import { transformSync } from 'esbuild';
import { renderToString } from '@vue/server-renderer';

const require = createRequire(import.meta.url);
const vue = require('vue');
const { descriptor } = parse(readFileSync(new URL('../src/components/SystemSettings.vue', import.meta.url), 'utf8'));
const code = transformSync(compileScript(descriptor, { id: 'settings-test' }).content, { format: 'cjs' }).code;

test('admin settings retain blank secrets, require saving edits, and show test failures', async () => {
  const requests = [];
  let processor;
  let sourceDisconnected = false;
  let processorDisconnected = false;
  let trackStopped = false;
  let contextClosed = false;
  let timerCleared = false;
  class AudioContext {
    constructor() {
      this.state = 'running';
      this.sampleRate = 48000;
      this.destination = {};
    }
    createMediaStreamSource() {
      return { connect() {}, disconnect() { sourceDisconnected = true; } };
    }
    createScriptProcessor() {
      processor = { connect() {}, disconnect() { processorDisconnected = true; } };
      return processor;
    }
    close() {
      this.state = 'closed';
      contextClosed = true;
      return Promise.resolve();
    }
  }
  const stream = { getTracks: () => [{ stop() { trackStopped = true; } }] };
  const window = {
    isSecureContext: true,
    AudioContext,
    setInterval: () => 1,
    clearInterval: () => { timerCleared = true; },
  };
  const navigator = { mediaDevices: { getUserMedia: async () => stream } };
  const saved = { settings: { LLM_PROVIDER: 'doubao', ASR_PROVIDER: 'xunfei', DOUBAO_MODEL: 'model' },
    secrets_configured: { DOUBAO_API_KEY: true } };
  const api = {
    get: async () => ({ data: saved }),
    put: async (path, values) => { requests.push({ path, values: { ...values } }); return { data: saved }; },
    post: async (path, body, options) => {
      requests.push({ path, body, options });
      if (path.endsWith('/asr')) throw { response: { data: { ok: false, error: '调用失败', elapsed_ms: 12 } } };
      return { data: { ok: true, result: { message: '连接成功' }, elapsed_ms: 10 } };
    },
  };
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports,
    require: (name) => name === '../api' ? { api } : require(name), Blob, FormData, navigator, window, console });
  let ctx;
  await renderToString(vue.createSSRApp({ setup() { ctx = module.exports.default.setup({}, { expose() {} }); return () => null; } }));
  await ctx.load();
  assert.equal(ctx.settings.DOUBAO_API_KEY, '');
  assert.match(ctx.secretPlaceholder('DOUBAO_API_KEY'), /已配置/);
  ctx.settings.DOUBAO_API_KEY = 'replacement';
  ctx.dirty.value = true;
  await ctx.test('llm');
  assert.equal(requests.length, 0);
  await ctx.save();
  assert.equal(requests[0].values.DOUBAO_API_KEY, 'replacement');
  assert.deepEqual(Object.keys(requests[0].values), ['DOUBAO_API_KEY']);
  assert.equal(ctx.settings.DOUBAO_API_KEY, '');
  assert.equal(ctx.dirty.value, false);
  await ctx.test('llm');
  assert.equal(ctx.results.llm.result.message, '连接成功');
  ctx.testLang.value = 'ja-JP';
  await ctx.startTestRecording();
  assert.equal(ctx.testRecording.value, true);
  processor.onaudioprocess({
    inputBuffer: { getChannelData: () => new Float32Array(480).fill(0.5) },
    outputBuffer: { getChannelData: () => new Float32Array(480) },
  });
  await ctx.stopTestRecording();
  const asrRequest = requests.find((request) => request.path.endsWith('/asr'));
  assert.equal(asrRequest.body.get('lang'), 'ja-JP');
  assert.equal(asrRequest.body.get('audio').name, 'test-recording.pcm');
  assert.equal(asrRequest.body.get('audio').size, 320);
  assert.equal(asrRequest.options.timeout, 90000);
  assert.equal(trackStopped, true);
  assert.equal(sourceDisconnected, true);
  assert.equal(processorDisconnected, true);
  assert.equal(contextClosed, true);
  assert.equal(timerCleared, true);
  assert.equal(ctx.results.asr.ok, false);
  assert.equal(ctx.results.asr.error, '调用失败');
  assert.equal(ctx.testing.value, '');

  await ctx.startTestRecording();
  processor.onaudioprocess({
    inputBuffer: { getChannelData: () => new Float32Array(1441000).fill(0.25) },
    outputBuffer: { getChannelData: () => new Float32Array(1) },
  });
  await Promise.resolve();
  await Promise.resolve();
  const cappedRequest = requests.filter((request) => request.path.endsWith('/asr')).at(-1);
  assert.equal(cappedRequest.body.get('audio').size, 16000 * 2 * 30);
  assert.equal(ctx.testRecording.value, false);

  await ctx.restoreEnvironment();
  assert.ok(Object.values(requests.at(-1).values).every((value) => value === null));
  assert.equal(ctx.results.llm, null);
  assert.equal(ctx.results.asr, null);
});
