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
const { descriptor } = parse(readFileSync(new URL('../src/components/ExportButton.vue', import.meta.url), 'utf8'));
const code = transformSync(compileScript(descriptor, { id: 'export-test' }).content, { format: 'cjs' }).code;

async function fixture(downloadBlob, disabled = false) {
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports, Blob, console,
    require: (name) => name === '../api' ? { downloadBlob } : require(name),
  });
  let ctx;
  await renderToString(vue.createSSRApp({ setup() {
    ctx = module.exports.default.setup({ path: '/practices/12/export', filename: 'practice-12', disabled }, { expose() {} });
    return () => null;
  } }));
  return ctx;
}

test('export format determines both the endpoint and the downloaded extension', async () => {
  const requests = [];
  const c = await fixture(async (...args) => { requests.push(args); });
  await c.exportFile();
  c.format.value = 'csv';
  await c.exportFile();
  assert.deepEqual(requests, [
    ['/practices/12/export.xlsx', 'practice-12.xlsx'],
    ['/practices/12/export.csv', 'practice-12.csv'],
  ]);
});

test('pending or disabled exports cannot submit duplicate downloads', async () => {
  let finish;
  let calls = 0;
  const download = () => { calls += 1; return new Promise((resolve) => { finish = resolve; }); };
  const c = await fixture(download);
  const pending = c.exportFile();
  assert.equal(c.exporting.value, true);
  await c.exportFile();
  assert.equal(calls, 1);
  finish();
  await pending;
  assert.equal(c.exporting.value, false);
  const disabled = await fixture(download, true);
  await disabled.exportFile();
  assert.equal(calls, 1);
});

test('download errors display the JSON message from a Blob and permit retry', async () => {
  let fail = true;
  const c = await fixture(async () => {
    if (fail) throw { response: { data: new Blob([JSON.stringify({ error: '无权访问该练习记录' })]) } };
  });
  await c.exportFile();
  assert.equal(c.error.value, '无权访问该练习记录');
  assert.equal(c.exporting.value, false);
  fail = false;
  await c.exportFile();
  assert.equal(c.error.value, '');
});
