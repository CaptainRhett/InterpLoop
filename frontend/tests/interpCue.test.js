import assert from 'node:assert/strict';
import test from 'node:test';
import { createCuePlayer, splitSentences } from '../src/utils/interpCue.js';

const flush = async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); };

function harness(synthesize = async () => ({})) {
  const utterances = [];
  const audio = [];
  const timers = new Map();
  const indices = [];
  const statuses = [];
  const playing = [];
  const player = createCuePlayer({
    synthesize,
    onIndex: (index) => indices.push(index),
    onStatus: (status) => statuses.push(status),
    onPlaying: (value) => playing.push(value),
    speech: { cancel() {}, speak: (utterance) => utterances.push(utterance) },
    makeUtterance: (text) => ({ text }),
    makeAudio: () => {
      const item = { play: async () => {}, pause() { this.paused = true; }, removeAttribute() {}, load() {} };
      audio.push(item);
      return item;
    },
    schedule: (callback, delay) => { const id = Symbol(); timers.set(id, { callback, delay }); return id; },
    unschedule: (id) => timers.delete(id),
  });
  const play = (options = {}) => player.play({
    sentences: ['First sentence.', 'Second sentence.'], lang: 'en-US', voice: '', getInterval: () => 8, ...options,
  });
  return { player, play, utterances, audio, timers, indices, statuses, playing };
}

test('splits English periods, CJK punctuation, newlines and trailing text', () => {
  assert.deepEqual(splitSentences('Hello world. Next sentence!\n你好。次の文？\nLast fragment'),
    ['Hello world.', 'Next sentence!', '你好。', '次の文？', 'Last fragment']);
  assert.deepEqual(splitSentences('Hello.World. Really?! "Yes." Next.'),
    ['Hello.', 'World.', 'Really?!', '"Yes."', 'Next.']);
  assert.deepEqual(splitSentences('  \n\r\n'), []);
});

test('keeps decimals, titles, initials and domains within sentences', () => {
  assert.deepEqual(splitSentences('Dr. Smith paid 3.14 dollars. Mr. J. Jones visited example.com. Done.'),
    ['Dr. Smith paid 3.14 dollars.', 'Mr. J. Jones visited example.com.', 'Done.']);
});

for (const source of ['browser', 'audio']) {
  test(`${source}: waits for the end event, then the full interval; no final delay`, async () => {
    const h = harness(async () => source === 'audio' ? { audio_base64: 'mock' } : {});
    const run = h.play();
    await flush();
    assert.deepEqual(h.indices, [0]);
    assert.equal(h.timers.size, 0, 'reading time must not consume the pause');
    const clips = source === 'audio' ? h.audio : h.utterances;
    const end = () => source === 'audio' ? clips.at(-1).onended() : clips.at(-1).onend();
    end();
    await flush();
    assert.equal(h.timers.size, 1);
    const timer = [...h.timers.values()][0];
    assert.equal(timer.delay, 8000);
    assert.deepEqual(h.indices, [0]);
    timer.callback();
    await flush();
    assert.deepEqual(h.indices, [0, 1]);
    end();
    await run;
    assert.equal(h.timers.size, 0);
    assert.equal(h.statuses.at(-1), '播放完成');
    assert.equal(h.playing.at(-1), false);
  });
}

test('stop during a TTS request prevents late playback', async () => {
  let respond;
  let signal;
  const h = harness((payload, requestSignal) => {
    signal = requestSignal;
    return new Promise((resolve) => { respond = resolve; });
  });
  const run = h.play();
  h.player.stop();
  assert.equal(signal.aborted, true);
  respond({ audio_base64: 'late' });
  await run;
  assert.equal(h.audio.length, 0);
  assert.equal(h.utterances.length, 0);
  assert.equal(h.timers.size, 0);
});

test('stop during speech settles the run and ignores a late end event', async () => {
  const h = harness();
  const run = h.play();
  await flush();
  const lateEnd = h.utterances[0].onend;
  h.player.stop();
  lateEnd();
  await run;
  assert.equal(h.timers.size, 0);
  assert.deepEqual(h.indices, [0]);
});

test('stop during the interval clears the pending next sentence', async () => {
  const h = harness();
  const run = h.play();
  await flush();
  h.utterances[0].onend();
  await flush();
  h.player.stop();
  await run;
  assert.equal(h.timers.size, 0);
  assert.deepEqual(h.indices, [0]);
});

test('replaying the current sentence cancels the previous queue', async () => {
  const h = harness();
  const first = h.play();
  await flush();
  const lateEnd = h.utterances[0].onend;
  const replay = h.play({ single: true });
  await flush();
  lateEnd();
  h.utterances[1].onend();
  await Promise.all([first, replay]);
  assert.deepEqual(h.indices, [0, 0]);
  assert.equal(h.timers.size, 0);
});

test('service failure falls back to browser speech and waits for completion', async () => {
  const h = harness(async () => { throw new Error('service unavailable'); });
  const run = h.play({ single: true });
  await flush();
  assert.equal(h.utterances.length, 1);
  assert.equal(h.playing.at(-1), true);
  h.utterances[0].onend();
  await run;
  assert.equal(h.playing.at(-1), false);
});

test('audio failure uses browser fallback; speech failure stops the queue', async () => {
  const h = harness(async () => ({ audio_base64: 'broken' }));
  const run = h.play();
  await flush();
  h.audio[0].onerror();
  await flush();
  assert.equal(h.audio[0].paused, true);
  h.utterances[0].onerror();
  await run;
  assert.match(h.statuses.at(-1), /浏览器朗读失败/);
  assert.equal(h.playing.at(-1), false);
  assert.equal(h.timers.size, 0);
});

for (const source of ['browser', 'audio']) {
  test(`${source}: pause/resume keeps the same sentence and does not finish early`, async () => {
    const events = [];
    let clip;
    const player = createCuePlayer({
      synthesize: async () => source === 'audio' ? { audio_base64: 'mock' } : {},
      onIndex() {}, onStatus() {}, onPlaying() {},
      onPaused: (paused) => events.push(paused ? 'paused' : 'resumed'),
      speech: { cancel() {}, speak: (value) => { clip = value; }, pause() { events.push('pause'); }, resume() { events.push('resume'); } },
      makeUtterance: (text) => ({ text }),
      makeAudio: () => (clip = { play: async () => { events.push('play'); }, pause() { events.push('pause'); }, removeAttribute() {}, load() {} }),
    });
    let finished = false;
    const run = player.play({ sentences: ['One sentence.'], single: true, lang: 'en-US' }).then((value) => { finished = value; });
    await flush();
    const originalClip = clip;
    player.togglePause();
    await flush();
    assert.equal(finished, false);
    assert.equal(events.at(-1), 'paused');
    player.togglePause();
    assert.equal(clip, originalClip);
    assert.equal(events.at(-1), 'resumed');
    if (source === 'audio') clip.onended();
    else clip.onend();
    await run;
    assert.equal(finished, true);
  });
}
