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

async function fixture({ getUserMedia, upload } = {}) {
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
      if (upload) await upload();
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
    navigator: { mediaDevices: { getUserMedia: getUserMedia || (async () => ({ getTracks: () => [{ stop() {} }] })) } },
    Blob, FormData, console,
  });
  let ctx;
  await renderToString(vue.createSSRApp({ setup() { ctx = module.exports.default.setup({}, { expose() {} }); return () => null; } }));
  return { ctx, uploads, requests, getUtterance: () => utterance, endSpeech: () => utterance.onend(),
    capture: () => processor.onaudioprocess({ inputBuffer: { getChannelData: () => new Float32Array([0.1, 0.2]) }, outputBuffer: { getChannelData: () => new Float32Array(2) } }) };
}

test('loop alternates playback/recording, hides each source by default, and evaluates all sentences', async () => {
  const h = await fixture();
  const c = h.ctx;
  c.state.sourceText = 'First sentence. Second sentence.';
  c.state.direction = '英→中';
  const begin = c.goRecording();
  await flush();
  assert.equal(c.state.segments.length, 2);
  assert.equal(c.state.step, 3);
  assert.equal(c.state.hideSource, true, 'source is hidden during initial playback');
  await c.startRecording();
  assert.equal(c.recording.value, false, 'cannot record over source audio');
  c.player.togglePause();
  assert.equal(c.sourcePaused.value, true);
  c.player.togglePause();
  h.endSpeech();
  await begin;
  await c.startRecording();
  assert.equal(c.state.hideSource, true);
  h.capture();
  await c.stopAndUpload();
  assert.equal(c.state.hideSource, true, 'source stays hidden after recording');
  assert.equal(c.state.step, 3, 'first recording must not jump to evaluation');
  c.currentSegment.value.transcript = 'Corrected first translation.';
  c.state.hideSource = false;
  c.nextSegment();
  await flush();
  assert.equal(c.state.segmentIndex, 1);
  assert.equal(c.state.hideSource, true, 'next sentence is hidden even if the previous one was revealed');
  h.endSpeech();
  await flush();
  c.state.hideSource = false;
  await c.startRecording();
  assert.equal(c.state.hideSource, false, 'recording respects the visibility toggle');
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
  assert.equal(c.state.hideSource, true, 'new practice resets source visibility');
});

test('pause permits recording, preserves the utterance, and blocks resume until recognition finishes', async () => {
  let openMicrophone;
  let finishUpload;
  const h = await fixture({
    getUserMedia: () => new Promise((resolve) => { openMicrophone = resolve; }),
    upload: () => new Promise((resolve) => { finishUpload = resolve; }),
  });
  const c = h.ctx;
  c.state.sourceText = 'First sentence.';
  const begin = c.goRecording();
  await flush();
  const original = h.getUtterance();
  assert.equal(c.canRecord.value, false);
  c.toggleSourcePause();
  assert.equal(c.canRecord.value, true);
  const start = c.startRecording();
  c.toggleSourcePause();
  assert.equal(c.sourcePaused.value, true, 'cannot resume while microphone permission is pending');
  openMicrophone({ getTracks: () => [{ stop() {} }] });
  await start;
  assert.equal(c.recording.value, true);
  c.toggleSourcePause();
  await c.playSource();
  assert.equal(c.sourcePaused.value, true, 'cannot resume or replay during recording');
  h.capture();
  const upload = c.stopAndUpload();
  c.toggleSourcePause();
  assert.equal(c.sourcePaused.value, true, 'cannot resume during recognition');
  finishUpload();
  await upload;
  c.toggleSourcePause();
  assert.equal(c.sourcePaused.value, false);
  assert.equal(h.getUtterance(), original, 'resume must use the original utterance');
  assert.equal(h.requests.filter((r) => r.path === '/tts').length, 1);
  await c.startRecording();
  assert.equal(c.recording.value, false, 'resumed audio blocks recording');
  h.endSpeech();
  await begin;
  assert.equal(c.canRecord.value, true);
});

test('recording while paused can advance to the next sentence or evaluation, cancelling old playback', async () => {
  const h = await fixture();
  const c = h.ctx;
  c.state.sourceText = 'First sentence. Second sentence.';
  const begin = c.goRecording();
  await flush();
  for (let index = 0; index < 2; index += 1) {
    c.toggleSourcePause();
    await c.startRecording();
    h.capture();
    await c.stopAndUpload();
    const old = h.getUtterance();
    c.nextSegment();
    await flush();
    assert.equal(old.onend, null);
    assert.equal(c.sourcePaused.value, false);
    assert.equal(c.sourcePlayed.value, false);
  }
  await begin;
  assert.equal(c.state.step, 4);
  assert.equal(c.sourcePlaying.value, false);
  assert.equal(c.sourcePausable.value, false);
  assert.equal(c.state.asrText, 'Translation 1.\nTranslation 2.');
});

test('microphone failure preserves paused playback for resuming', async () => {
  const h = await fixture({ getUserMedia: async () => { throw { name: 'NotAllowedError' }; } });
  const c = h.ctx;
  const begin = c.goRecording();
  await flush();
  c.toggleSourcePause();
  await c.startRecording();
  assert.equal(c.sourcePaused.value, true);
  assert.equal(c.captureBusy.value, false);
  c.toggleSourcePause();
  h.endSpeech();
  await begin;
});

test('Feedback link identifies the exact saved evaluation version', async () => {
  const { ctx: c } = await fixture();
  c.state.practice = { id: 12 };
  c.state.evaluationVersion = { id: 34, version_number: 2 };
  assert.equal(c.feedbackLocation.value.name, 'feedbacklog');
  assert.equal(c.feedbackLocation.value.query.practice, '12');
  assert.equal(c.feedbackLocation.value.query.version, '34');
});
