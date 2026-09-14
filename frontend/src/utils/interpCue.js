// Keep decimal points, common English abbreviations and closing quotes intact.
export function splitSentences(text) {
  const sentences = [];
  for (const line of text.split(/\r?\n+/)) {
    let start = 0;
    const endings = /[。！？!?]+|\.+/g;
    for (const match of line.matchAll(endings)) {
      const index = match.index;
      let end = index + match[0].length;
      if (match[0] === ".") {
        const before = line.slice(start, index);
        const after = line.slice(end);
        if (/\d$/.test(before) && /^\d/.test(after)) continue;
        if (/\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|e\.g|i\.e)$/i.test(before) && /\S/.test(after)) continue;
        // Initials/acronyms (J. Smith, U.S.) and dots inside domains.
        if (/\b[A-Z]$/.test(before) && /^\s*[A-Za-z]/.test(after)) continue;
        if (/[A-Za-z]$/.test(before) && /^[a-z]/.test(after)) continue;
      }
      while (/["'”’」』）)\]]/.test(line[end] || "\0")) end += 1;
      const sentence = line.slice(start, end).trim();
      if (sentence) sentences.push(sentence);
      start = end;
    }
    const remaining = line.slice(start).trim();
    if (remaining) sentences.push(remaining);
  }
  return sentences;
}

export function createCuePlayer({
  synthesize,
  onIndex,
  onStatus,
  onPlaying,
  onPaused = () => {},
  onPausable = () => {},
  speech = globalThis.speechSynthesis,
  makeUtterance = (text) => new SpeechSynthesisUtterance(text),
  makeAudio = (url) => new Audio(url),
  schedule = (callback, delay) => setTimeout(callback, delay),
  unschedule = (timer) => clearTimeout(timer),
}) {
  let generation = 0;
  let controller = null;
  let cancelWait = null;
  let playbackControl = null;
  let paused = false;

  function stop() {
    generation += 1;
    controller?.abort();
    controller = null;
    cancelWait?.();
    cancelWait = null;
    playbackControl = null;
    paused = false;
    onPaused(false);
    onPausable(false);
    speech?.cancel();
    onPlaying(false);
  }

  // Cancellation resolves the wait too, so stopped playback never leaves a
  // pending run that can schedule another sentence after a late TTS response.
  function waitFor(start) {
    return new Promise((resolve, reject) => {
      let cleanup = () => {};
      let settled = false;
      const finish = (error) => {
        if (settled) return;
        settled = true;
        cleanup();
        cancelWait = null;
        if (error) reject(error);
        else resolve();
      };
      cancelWait = () => finish();
      try {
        cleanup = start(() => finish(), (error) => finish(error));
        if (settled) cleanup();
      } catch (error) {
        finish(error);
      }
    });
  }

  function browserSpeech(text, lang) {
    if (!speech) throw new Error("当前浏览器不支持语音朗读");
    return waitFor((done, fail) => {
      const utterance = makeUtterance(text);
      utterance.lang = lang;
      utterance.rate = 0.9;
      utterance.onend = done;
      utterance.onerror = () => fail(new Error("浏览器朗读失败，请检查系统语音和浏览器声音权限"));
      playbackControl = { pause: () => speech.pause(), resume: () => speech.resume() };
      onPausable(true);
      speech.speak(utterance);
      return () => {
        playbackControl = null;
        onPausable(false);
        utterance.onend = null;
        utterance.onerror = null;
      };
    });
  }

  function audioSpeech(data) {
    return waitFor((done, fail) => {
      const audio = makeAudio(`data:${data.mime_type || "audio/mpeg"};base64,${data.audio_base64}`);
      audio.onended = done;
      audio.onerror = () => fail(new Error("音频解码或播放失败"));
      playbackControl = { pause: () => audio.pause(), resume: () => audio.play().catch(fail) };
      onPausable(true);
      audio.play().catch(fail);
      return () => {
        playbackControl = null;
        onPausable(false);
        audio.onended = null;
        audio.onerror = null;
        audio.pause();
        audio.removeAttribute("src");
        audio.load();
      };
    });
  }

  async function play({ sentences, index = 0, single = false, lang, voice, getInterval }) {
    stop();
    if (!sentences.length) return;
    const run = generation;
    const active = () => generation === run;
    controller = new AbortController();
    onPlaying(true);
    try {
      for (let i = index; i < sentences.length && active(); i += 1) {
        onIndex(i);
        onStatus(`正在播放第 ${i + 1} 句`);
        let data;
        try {
          data = await synthesize({ text: sentences[i], lang, voice }, controller.signal);
        } catch {
          // Service failures use browser speech; an aborted run must stay silent.
        }
        if (!active()) return;
        if (data?.audio_base64) {
          try {
            await audioSpeech(data);
          } catch {
            if (active()) await browserSpeech(sentences[i], lang);
          }
        } else {
          await browserSpeech(sentences[i], lang);
        }
        if (!active()) return;
        if (single || i === sentences.length - 1) break;
        const seconds = getInterval();
        onStatus(`第 ${i + 1} 句播放完毕，停顿 ${seconds} 秒`);
        await waitFor((done) => {
          const timer = schedule(done, seconds * 1000);
          return () => unschedule(timer);
        });
      }
      if (active()) onStatus("播放完成");
      return active();
    } catch (error) {
      if (active()) onStatus(error.message || "播放失败");
      return false;
    } finally {
      if (active()) {
        controller = null;
        onPlaying(false);
      }
    }
  }

  function togglePause() {
    if (!playbackControl) return;
    if (paused) playbackControl.resume();
    else playbackControl.pause();
    paused = !paused;
    onPaused(paused);
  }

  return { play, stop, togglePause };
}
