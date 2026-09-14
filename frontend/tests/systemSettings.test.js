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
  const saved = { settings: { LLM_PROVIDER: 'doubao', ASR_PROVIDER: 'xunfei', DOUBAO_MODEL: 'model' },
    secrets_configured: { DOUBAO_API_KEY: true } };
  const api = {
    get: async () => ({ data: saved }),
    put: async (path, values) => { requests.push({ path, values: { ...values } }); return { data: saved }; },
    post: async (path, body) => {
      requests.push({ path, body });
      if (path.endsWith('/asr')) throw { response: { data: { ok: false, error: '调用失败', elapsed_ms: 12 } } };
      return { data: { ok: true, result: { message: '连接成功' }, elapsed_ms: 10 } };
    },
  };
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports,
    require: (name) => name === '../api' ? { api } : require(name), FormData, console });
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
  ctx.testFile.value = new Blob(['audio']);
  await ctx.test('asr');
  assert.equal(ctx.results.asr.ok, false);
  assert.equal(ctx.results.asr.error, '调用失败');
  assert.equal(ctx.testing.value, '');
  await ctx.restoreEnvironment();
  assert.ok(Object.values(requests.at(-1).values).every((value) => value === null));
  assert.equal(ctx.results.llm, null);
  assert.equal(ctx.results.asr, null);
});
