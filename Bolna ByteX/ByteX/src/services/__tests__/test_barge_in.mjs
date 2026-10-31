import test from 'node:test';
import assert from 'node:assert/strict';

// ---------------------------------------------------------
// 1. Browser Mocks for Web Audio API & Speech Synthesis
// ---------------------------------------------------------

class MockMediaStreamTrack {
  constructor(kind = 'audio') {
    this.kind = kind;
    this.stopped = false;
  }
  stop() {
    this.stopped = true;
  }
}

class MockMediaStream {
  constructor() {
    this.tracks = [new MockMediaStreamTrack('audio')];
  }
  getTracks() {
    return this.tracks;
  }
}

class MockAnalyserNode {
  constructor() {
    this.fftSize = 256;
    this.frequencyBinCount = 128;
    this.smoothingTimeConstant = 0.3;
    this.simulatedBuffer = new Uint8Array(128).fill(128); // 128 = 0.0 amplitude
  }

  setSimulatedAmplitude(amp) {
    // normalized amplitude in [-1, 1], stored as byte centered at 128
    const val = Math.max(0, Math.min(255, Math.round(128 + amp * 128)));
    this.simulatedBuffer.fill(val);
  }

  getByteTimeDomainData(array) {
    array.set(this.simulatedBuffer);
  }
}

class MockAudioContext {
  constructor() {
    this.state = 'running';
    this.closed = false;
    this.analyser = new MockAnalyserNode();
  }

  async resume() {
    this.state = 'running';
  }

  async close() {
    this.state = 'closed';
    this.closed = true;
  }

  createMediaStreamSource() {
    return {
      connect: () => {},
    };
  }

  createAnalyser() {
    return this.analyser;
  }
}

class MockSpeechSynthesisUtterance {
  constructor(text) {
    this.text = text;
    this.rate = 1.0;
    this.volume = 1.0;
    this.pitch = 1.0;
    this.lang = 'en-US';
    this.onstart = null;
    this.onend = null;
    this.onerror = null;
    this.onboundary = null;
  }
}

class MockSpeechSynthesis {
  constructor() {
    this.speaking = false;
    this.currentUtterance = null;
    this.cancelCallCount = 0;
  }

  getVoices() {
    return [{ name: 'Test Voice', lang: 'en-US', voiceURI: 'test-voice-uri' }];
  }

  speak(utterance) {
    this.speaking = true;
    this.currentUtterance = utterance;
    if (utterance.onstart) utterance.onstart();
  }

  cancel() {
    this.speaking = false;
    this.currentUtterance = null;
    this.cancelCallCount++;
  }
}

class MockSpeechRecognition {
  static latestInstance = null;
  constructor() {
    MockSpeechRecognition.latestInstance = this;
    this.continuous = false;
    this.interimResults = false;
    this.lang = 'en-US';
    this.started = false;
    this.onstart = null;
    this.onend = null;
    this.onresult = null;
    this.onerror = null;
  }
  start() {
    this.started = true;
    if (this.onstart) this.onstart();
  }
  stop() {
    this.started = false;
    if (this.onend) this.onend();
  }
  abort() {
    this.started = false;
    if (this.onend) this.onend();
  }
}

// Global browser simulation
const mockSynthesis = new MockSpeechSynthesis();
globalThis.window = {
  AudioContext: MockAudioContext,
  webkitAudioContext: MockAudioContext,
  speechSynthesis: mockSynthesis,
  SpeechSynthesisUtterance: MockSpeechSynthesisUtterance,
  SpeechRecognition: MockSpeechRecognition,
  webkitSpeechRecognition: MockSpeechRecognition,
};
globalThis.SpeechSynthesisUtterance = MockSpeechSynthesisUtterance;
globalThis.SpeechRecognition = MockSpeechRecognition;

try {
  Object.defineProperty(globalThis, 'navigator', {
    value: {
      userAgent: 'Chrome/120.0.0.0 Windows',
      mediaDevices: {
        getUserMedia: async () => new MockMediaStream(),
      },
    },
    configurable: true,
    writable: true,
  });
} catch (e) {
  if (globalThis.navigator) {
    globalThis.navigator.mediaDevices = {
      getUserMedia: async () => new MockMediaStream(),
    };
  }
}

// Import services after globals are set
const { BargeInService } = await import('../bargeInService.ts');
const { ttsService } = await import('../ttsService.ts');
const { WakeWordService } = await import('../wakeWordService.ts');
const { default: sttService } = await import('../sttService.ts');

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// ---------------------------------------------------------
// 2. Unit Tests for Function 566
// ---------------------------------------------------------

test('BargeInService - Configuration defaults, setters and limits', () => {
  const service = new BargeInService();
  const cfg = service.getConfig();
  assert.equal(cfg.energyThreshold, 0.045, 'Default energy threshold is 0.045');
  assert.equal(cfg.persistenceMs, 120, 'Default persistence is 120ms');
  assert.equal(cfg.gracePeriodMs, 250, 'Default grace period is 250ms');
  assert.equal(cfg.cooldownMs, 800, 'Default cooldown is 800ms');

  service.setConfig({ energyThreshold: 0.35, persistenceMs: 250, gracePeriodMs: 0 });
  assert.equal(service.getConfig().energyThreshold, 0.35);
  assert.equal(service.getConfig().persistenceMs, 250);
  assert.equal(service.getConfig().gracePeriodMs, 0, 'Allows setting gracePeriodMs to 0');

  // Clamping test
  service.setConfig({ energyThreshold: 0.005, persistenceMs: 10 });
  assert.equal(service.getConfig().energyThreshold, 0.015, 'Clamped to minimum 0.015');
  assert.equal(service.getConfig().persistenceMs, 50, 'Clamped to minimum 50ms');

  service.dispose();
});

test('BargeInService - Grace period ignores loud audio at start of playback', async () => {
  const service = new BargeInService();
  service.setConfig({ gracePeriodMs: 120, persistenceMs: 50, sampleIntervalMs: 10 });
  await service.startMonitoring();

  let interrupted = false;
  service.onInterruption(() => {
    interrupted = true;
  });

  // Inject loud amplitude immediately during grace period
  const analyser = service.audioContext.analyser;
  analyser.setSimulatedAmplitude(0.40);

  // Poll frames within first 40ms (well within the 120ms grace window)
  service.processAudioFrame();
  service.processAudioFrame();
  service.processAudioFrame();

  assert.equal(interrupted, false, 'No interruption during grace period');

  service.stopMonitoring();
  service.dispose();
});

test('BargeInService - Short noise spikes do not trigger false interruption', async () => {
  const service = new BargeInService();
  service.setConfig({ gracePeriodMs: 0, persistenceMs: 100, energyThreshold: 0.045 });
  await service.startMonitoring();

  let interrupted = false;
  service.onInterruption(() => {
    interrupted = true;
  });

  const analyser = service.audioContext.analyser;

  // Single loud spike (e.g. mic click or table tap)
  analyser.setSimulatedAmplitude(0.50);
  service.processAudioFrame();

  // Immediately followed by quiet audio
  analyser.setSimulatedAmplitude(0.02);
  service.processAudioFrame();
  await sleep(120);
  service.processAudioFrame();

  assert.equal(interrupted, false, 'Transient noise spike was ignored and did not interrupt');

  service.stopMonitoring();
  service.dispose();
});

test('BargeInService - Sustained speech triggers exactly one interruption event', async () => {
  const service = new BargeInService();
  service.setConfig({ gracePeriodMs: 0, persistenceMs: 50, energyThreshold: 0.045 });
  await service.startMonitoring();

  const events = [];
  service.onInterruption((evt) => {
    events.push(evt);
  });

  const analyser = service.audioContext.analyser;
  analyser.setSimulatedAmplitude(0.35);

  // Frame 1: speech begins
  service.processAudioFrame();
  assert.equal(events.length, 0, 'Frame 1: pending sustained persistence');

  // Wait for persistence window to elapse with continuous speech
  await sleep(70);
  service.processAudioFrame();

  assert.equal(events.length, 1, 'Interruption triggered after persistence window');
  assert.ok(events[0].amplitude >= 0.045, 'Reported amplitude exceeds threshold');
  assert.ok(events[0].duration >= 50, 'Reported duration reflects persistence');
  assert.equal(service.getIsMonitoring(), false, 'Monitoring stops automatically after interruption');

  service.dispose();
});

test('BargeInService - Cooldown prevents immediate re-trigger loop', async () => {
  const service = new BargeInService();
  service.setConfig({ gracePeriodMs: 0, persistenceMs: 50, cooldownMs: 250 });
  await service.startMonitoring();

  let interruptCount = 0;
  service.onInterruption(() => {
    interruptCount++;
  });

  const analyser = service.audioContext.analyser;
  analyser.setSimulatedAmplitude(0.40);
  service.processAudioFrame();
  await sleep(70);
  service.processAudioFrame();

  assert.equal(interruptCount, 1, 'First interruption triggered');

  // Attempt to immediately start monitoring again while cooldown is active
  const started = await service.startMonitoring();
  assert.equal(started, false, 'Start monitoring deferred during cooldown window');

  // After cooldown expires, startMonitoring succeeds
  await sleep(260);
  const restarted = await service.startMonitoring();
  assert.equal(restarted, true, 'Start monitoring allowed after cooldown window');

  service.stopMonitoring();
  service.dispose();
});

test('BargeInService - Resource cleanup on stopMonitoring and dispose', async () => {
  const service = new BargeInService();
  await service.startMonitoring();

  const track = service.micStream.getTracks()[0];
  const audioCtx = service.audioContext;

  assert.equal(service.getIsMonitoring(), true);
  assert.equal(track.stopped, false);

  service.stopMonitoring();

  assert.equal(service.getIsMonitoring(), false);
  assert.equal(track.stopped, true, 'Microphone track stopped');
  assert.equal(audioCtx.closed, true, 'AudioContext closed');
  assert.equal(service.micStream, null);
  assert.equal(service.audioContext, null);

  service.dispose();
});

test('TTSService - Interruption stops playback, clears queue and stream buffers', () => {
  // Reset any prior state
  ttsService.stop();
  ttsService.resetStreamSuppression();

  // Queue initial sentences
  ttsService.feedStreamChunk('First sentence is here. Second sentence continues.');
  assert.ok(ttsService.isSpeaking(), 'TTS starts speaking first sentence');

  // Interruption occurs: call stop(true) with stream suppression
  ttsService.stop(true);

  assert.equal(ttsService.isSpeaking(), false, 'Speech stopped');
  assert.equal(ttsService.getIsStreamSuppressed(), true, 'Stream suppression active');
  assert.equal(mockSynthesis.cancelCallCount > 0, true, 'Browser synthesis cancelled');

  // Late arriving chunks from interrupted response must be discarded
  ttsService.feedStreamChunk(' Late stale tokens arriving after barge-in.');
  ttsService.flushStream();

  assert.equal(ttsService.isSpeaking(), false, 'Stale stream chunks suppressed and not spoken');

  // Reset suppression for next user turn
  ttsService.resetStreamSuppression();
  assert.equal(ttsService.getIsStreamSuppressed(), false);

  ttsService.feedStreamChunk('New answer after new prompt. Spoken normally.');
  assert.ok(ttsService.isSpeaking(), 'New speech proceeds after suppression reset');
  ttsService.stop();
});

test('Listening State Transition - Wake-word mode normal TTS finish enters CONTINUOUS_LISTENING', async () => {
  const wakeWord = new WakeWordService();
  await wakeWord.start();

  // Simulate assistant speaking (wakeWord paused)
  wakeWord.pause();
  assert.equal(wakeWord.getState(), 'IDLE');

  // Normal speech completes naturally -> enters CONTINUOUS_LISTENING so user can speak next command without wake phrase
  wakeWord.onTTSFinished();
  assert.equal(wakeWord.getState(), 'CONTINUOUS_LISTENING');

  wakeWord.stop();
});

test('Listening State Transition - Wake-word mode onInterruption enters CONTINUOUS_LISTENING for hands-free follow-up', async () => {
  const wakeWord = new WakeWordService();
  await wakeWord.start();

  // Simulate assistant speaking (wakeWord paused)
  wakeWord.pause();
  assert.equal(wakeWord.getState(), 'IDLE');

  // Acoustic interruption triggers onInterruption() -> enables hands-free command listening without clicking
  wakeWord.onInterruption();
  assert.equal(wakeWord.getState(), 'CONTINUOUS_LISTENING');

  wakeWord.stop();
});

test('Listening State Transition - "Stop" during speech cancels playback and maintains CONTINUOUS_LISTENING', async () => {
  const wakeWord = new WakeWordService();
  await wakeWord.start();

  // Assistant speaking
  ttsService.speak('Test response from ByteX');
  assert.ok(ttsService.isSpeaking());
  wakeWord.pause();

  // User says "Stop"
  const handled = wakeWord.handleStopOrStandby('Stop');
  assert.equal(handled, true);
  assert.equal(ttsService.isSpeaking(), false, 'Speech cancelled');
  assert.equal(wakeWord.getState(), 'CONTINUOUS_LISTENING', 'ByteX remains in CONTINUOUS_LISTENING ready for next command');

  wakeWord.stop();
});

test('Listening State Transition - Explicit standby phrase returns to LISTENING_FOR_WAKE_WORD', async () => {
  const wakeWord = new WakeWordService();
  await wakeWord.start();

  // In active conversation mode
  wakeWord.onTTSFinished();
  assert.equal(wakeWord.getState(), 'CONTINUOUS_LISTENING');

  // User explicitly says "stop listening" or "goodbye"
  const handled = wakeWord.handleStopOrStandby('stop listening');
  assert.equal(handled, true);
  assert.equal(wakeWord.getState(), 'LISTENING_FOR_WAKE_WORD', 'Returned to standby wake-word listening');

  wakeWord.stop();
});

test('Listening State Transition - Wake-word disabled activates direct STT listening', async () => {
  // Wake-word is disabled
  const wakeWord = new WakeWordService();
  wakeWord.stop();
  assert.equal(wakeWord.getState(), 'DISABLED');

  // Acoustic interruption triggers STT directly
  const started = await sttService.start();
  assert.equal(started, true, 'STT started');
  assert.equal(sttService.getIsListening(), true, 'ByteX actively enters STT listening state');

  sttService.stop();
  assert.equal(sttService.getIsListening(), false);
});
