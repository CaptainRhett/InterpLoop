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
const { descriptor } = parse(readFileSync(new URL('../src/views/FeedbackLogView.vue', import.meta.url), 'utf8'));
const code = transformSync(compileScript(descriptor, { id: 'feedback-test' }).content, { format: 'cjs' }).code;

async function fixture({ query = { practice: '12', version: '34' }, parseFails = false } = {}) {
  const requests = [];
  const auth = { user: { id: 7, student_no: 'S007', name: '学生' }, contexts: [
    { enrollment_id: 1, class_group: { id: 1 }, course: { id: 1 } },
    { enrollment_id: 2, class_group: { id: 2 }, course: { id: 3 } },
  ] };
  const api = {
    get: async (path) => {
      requests.push({ path });
      if (path === '/feedback-logs') return { data: { feedback_logs: [] } };
      assert.equal(path, '/practices/12');
      return { data: {
        practice: { id: 12, user: { id: 7 }, context: { class_group: { id: 2 }, course: { id: 3 } } },
        evaluation_versions: [
          { id: 35, version_number: 3, feedback_text: 'Newer evaluation' },
          { id: 34, version_number: 2, feedback_text: 'Requested evaluation' },
        ],
      } };
    },
    post: async (path, body) => {
      requests.push({ path, body });
      assert.equal(path, '/feedback/parse', 'import must not save a feedback record');
      if (parseFails) throw { response: { data: { error: '解析服务暂时不可用' } } };
      return { data: { pros: '优点', cons: '问题', suggestions: '建议', overall: '总评', counts: { pros: 1, cons: 1, suggestions: 1 } } };
    },
  };
  let mounted;
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports, console,
    require: (name) => {
      if (name === 'vue') return { ...vue, onMounted: (callback) => { mounted = callback; } };
      if (name === 'vue-router') return { useRoute: () => ({ query }) };
      if (name === '../api') return { api };
      if (name === '../components/ExportButton.vue') return {};
      if (name === '../stores/auth') return { useAuthStore: () => auth };
      return require(name);
    },
  });
  let ctx;
  await renderToString(vue.createSSRApp({ setup() { ctx = module.exports.default.setup({}, { expose() {} }); return () => null; } }));
  await mounted();
  return { ctx, requests };
}

test('Feedback imports and parses the selected version and restores its course context', async () => {
  const { ctx: c, requests } = await fixture();
  assert.equal(c.form.raw_text, 'Requested evaluation');
  assert.equal(c.form.task_id, 'LP-12-V2');
  assert.equal(c.form.context_id, 2);
  assert.equal(c.form.student_no, 'S007');
  assert.equal(c.form.student_name, '学生');
  assert.equal(c.form.pros, '优点');
  assert.equal(c.form.cons, '问题');
  assert.equal(c.form.suggestions, '建议');
  assert.equal(c.form.overall, '总评');
  assert.equal(requests.at(-1).body.raw_text, 'Requested evaluation');
  assert.equal(c.loadingFeedback.value, false);
  assert.equal(c.parsing.value, false);
});

test('direct Feedback navigation leaves the input empty without parsing', async () => {
  const { ctx: c, requests } = await fixture({ query: {} });
  assert.equal(c.form.raw_text, '');
  assert.deepEqual(requests.map((r) => r.path), ['/feedback-logs']);
});

test('parse failure keeps the imported text available for retry', async () => {
  const { ctx: c } = await fixture({ parseFails: true });
  assert.equal(c.form.raw_text, 'Requested evaluation');
  assert.equal(c.error.value, '解析服务暂时不可用');
  assert.equal(c.loadingFeedback.value, false);
  assert.equal(c.parsing.value, false);
});

test('missing evaluation version reports an error without importing another version', async () => {
  const { ctx: c, requests } = await fixture({ query: { practice: '12', version: '999' } });
  assert.equal(c.form.raw_text, '');
  assert.match(c.error.value, /没有可解析的 AI 评价/);
  assert.equal(requests.some((r) => r.path === '/feedback/parse'), false);
  assert.equal(c.loadingFeedback.value, false);
});
