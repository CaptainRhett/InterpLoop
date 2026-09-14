import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { parse, compileScript } from '@vue/compiler-sfc';
import { transformSync } from 'esbuild';
import { renderToString } from '@vue/server-renderer';
import { createCuePlayer, splitSentences } from '../src/utils/interpCue.js';
import * as languages from '../src/languages.js';

const require = createRequire(import.meta.url);
const vue = require('vue');
const { descriptor } = parse(readFileSync(new URL('../src/views/LoopPracticeView.vue', import.meta.url), 'utf8'));
const compiled = transformSync(compileScript(descriptor, { id: 'loop-test' }).content, { format: 'cjs' }).code;
const flush = async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); };

async function fixture() {
  let utterance;
  let processor;
  const uploads = [];
  const requests = [];
  const auth = { contexts: [], user: { role: 'student' } };
  const api = { post: async (path, data) => {
    requests.push({ path, data });
    if (path === '/tts') return { data: {} };
    if (path === '/practices') return { data: { practice: { id: 1 } } };
    if (path.endsWith('/audio')) {
      const index = Number(data.get('segment_index'));
      uploads.push(index);
      return { data: { practice: { id: 1 }, asr: { transcript: `Translation ${index + 1}.` } } };
    }
    if (path.endsWith('/evaluate')) return { data: { practice: { id: 1 }, evaluation: { score: '8' }, evaluation_version: { id: 1, version_number: 1 } } };
    throw new Error(`Unexpected API: ${path}`);
  } };
  const speech = { cancel() {}, speak(value) { utterance = value; }, pause() {}, resume() {} };
  class AudioContext {
    state = 'running'; sampleRate = 16000; destination = {};
    createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
    createScriptProcessor() { processor = { connect() {}, disconnect() {} }; return processor; }
    close() { this.state = 'closed'; }
  }
  const module = { exports: {} };
  vm.runInNewContext(compiled, {
    module, exports: module.exports,
    require: (name) => {
      if (name === '../api') return { api };
      if (name === '../stores/auth') return { useAuthStore: () => auth };
      if (name === '../languages') return languages;
      if (name === '../utils/interpCue') return { splitSentences, createCuePlayer: (options) => createCuePlayer({ ...options, speech, makeUtterance: (text) => ({ text }) }) };
      return require(name);
    },
    window: { isSecureContext: true, AudioContext, setInterval: () => 1, clearInterval() {} },
    navigator: { mediaDevices: { getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }) } },
    Blob, FormData, console,
  });
  let ctx;
  await renderToString(vue.createSSRApp({ setup() { ctx = module.exports.default.setup({}, { expose() {} }); return () => null; } }));
  return { ctx, uploads, requests, endSpeech: () => utterance.onend(),
    capture: () => processor.onaudioprocess({ inputBuffer: { getChannelData: () => new Float32Array([0.1, 0.2]) }, outputBuffer: { getChannelData: () => new Float32Array(2) } }) };
}

test('loop alternates playback/recording, hides source optionally, and evaluates all sentences', async () => {
  const h = await fixture();
  const c = h.ctx;
  c.state.sourceText = 'First sentence. Second sentence.';
  c.state.direction = '英→中';
  const begin = c.goRecording();
  await flush();
  assert.equal(c.state.segments.length, 2);
  assert.equal(c.state.step, 3);
  await c.startRecording();
  assert.equal(c.recording.value, false, 'cannot record over source audio');
  c.player.togglePause();
  assert.equal(c.sourcePaused.value, true);
  c.player.togglePause();
  h.endSpeech();
  await begin;
  await c.startRecording();
  assert.equal(c.sourceHidden.value, true);
  h.capture();
  await c.stopAndUpload();
  assert.equal(c.sourceHidden.value, false);
  assert.equal(c.state.step, 3, 'first recording must not jump to evaluation');
  c.currentSegment.value.transcript = 'Corrected first translation.';
  c.nextSegment();
  await flush();
  assert.equal(c.state.segmentIndex, 1);
  h.endSpeech();
  await flush();
  c.state.hideSource = false;
  await c.startRecording();
  assert.equal(c.sourceHidden.value, false);
  h.capture();
  await c.stopAndUpload();
  c.nextSegment();
  assert.equal(c.state.step, 4);
  assert.equal(c.state.asrText, 'Corrected first translation.\nTranslation 2.');
  assert.deepEqual(h.uploads, [0, 1]);
  await c.evaluate();
  assert.equal(h.requests.at(-1).data.asr_text, c.state.asrText);
  assert.equal(c.state.evaluation.score, '8');
  c.newPractice();
});
