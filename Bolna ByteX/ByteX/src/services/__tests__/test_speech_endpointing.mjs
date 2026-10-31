import test from 'node:test';
import assert from 'node:assert/strict';

// 1. Mock Browser Environment before importing services
class MockSpeechRecognition {
  static latestInstance = null;

  constructor() {
    MockSpeechRecognition.latestInstance = this;
    this.continuous = false;
    this.interimResults = false;
    this.lang = 'en-US';
    this.onstart = null;
    this.onresult = null;
    this.onerror = null;
    this.onend = null;
    this.started = false;
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

  emitResult(resultsArray, resultIndex = 0) {
    const results = resultsArray.map((item) => {
      const res = [{ transcript: item.transcript }];
      res.isFinal = !!item.isFinal;
      return res;
    });
    results.length = resultsArray.length;
    if (this.onresult) {
      this.onresult({
        resultIndex,
        results,
      });
    }
  }

  emitError(errorType) {
    if (this.onerror) {
      this.onerror({ error: errorType });
    }
  }

  emitEnd() {
    this.started = false;
    if (this.onend) {
      this.onend();
    }
  }
}

// Setup globals for SpeechRecognition and navigator
globalThis.window = {
  SpeechRecognition: MockSpeechRecognition,
  webkitSpeechRecognition: MockSpeechRecognition,
};
globalThis.SpeechRecognition = MockSpeechRecognition;

try {
  Object.defineProperty(globalThis, 'navigator', {
    value: {
      userAgent: 'Chrome/120.0.0.0 Windows',
      mediaDevices: {
        getUserMedia: async () => ({
          getTracks: () => [{ stop: () => {} }],
        }),
      },
    },
    configurable: true,
    writable: true,
  });
} catch (e) {
  if (globalThis.navigator) {
    globalThis.navigator.mediaDevices = {
      getUserMedia: async () => ({
        getTracks: () => [{ stop: () => {} }],
      }),
    };
  }
}

// 2. Import WakeWordService
const { WakeWordService } = await import('../wakeWordService.ts');

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test('Speech Endpointing - Interim results do NOT submit commands prematurely (cleanCmd >= 3)', async () => {
  const service = new WakeWordService();
  service.setSilenceTimeout(100); // 100ms for fast test execution
  await service.start();

  const rec = MockSpeechRecognition.latestInstance;
  assert.ok(rec, 'Mock recognition instance should be initialized');

  const capturedCommands = [];
  service.onCommandCaptured((cmd) => capturedCommands.push(cmd));

  // Trigger wake word into command mode
  service.triggerWakeWord('Hey ByteX');
  assert.equal(service.getState(), 'LISTENING_FOR_COMMAND');

  // Emit interim result >= 3 characters ("How")
  rec.emitResult([{ transcript: 'How', isFinal: false }], 0);
  assert.equal(capturedCommands.length, 0, 'Interim result "How" must not submit immediately');

  // Emit longer interim result
  rec.emitResult([{ transcript: 'How do I install Python', isFinal: false }], 0);
  assert.equal(capturedCommands.length, 0, 'Longer interim result must not submit immediately');

  // Let silence timer expire (100ms + margin)
  await sleep(150);
  assert.equal(capturedCommands.length, 1, 'Command should only submit after silence window');
  assert.equal(capturedCommands[0], 'How do I install Python');

  service.stop();
});

test('Speech Endpointing - Multi-part speech across result indices is combined correctly', async () => {
  const service = new WakeWordService();
  service.setSilenceTimeout(100);
  await service.start();

  const rec = MockSpeechRecognition.latestInstance;
  const capturedCommands = [];
  service.onCommandCaptured((cmd) => capturedCommands.push(cmd));

  service.triggerWakeWord('Hey ByteX');
  assert.equal(service.getState(), 'LISTENING_FOR_COMMAND');

  // Part 1 finalized at idx 0: "create a new react app"
  rec.emitResult([{ transcript: 'create a new react app', isFinal: true }], 0);
  assert.equal(capturedCommands.length, 0, 'Final segment 1 should wait for silence window');

  // Brief pause (30ms), then Part 2 arrives at idx 1 (interim then final)
  await sleep(30);
  rec.emitResult(
    [
      { transcript: 'create a new react app', isFinal: true },
      { transcript: 'with typescript', isFinal: false },
    ],
    1
  );
  assert.equal(capturedCommands.length, 0, 'Interim segment 2 resets silence window');

  rec.emitResult(
    [
      { transcript: 'create a new react app', isFinal: true },
      { transcript: 'with typescript', isFinal: true },
    ],
    1
  );
  assert.equal(capturedCommands.length, 0, 'Segment 2 final waits for silence window');

  // Allow silence window to complete
  await sleep(150);
  assert.equal(capturedCommands.length, 1, 'Multi-part speech should be combined into exactly 1 command');
  assert.equal(capturedCommands[0], 'create a new react app with typescript');

  service.stop();
});

test('Speech Endpointing - Final results submit at most once (no duplicate submissions)', async () => {
  const service = new WakeWordService();
  service.setSilenceTimeout(80);
  await service.start();

  const rec = MockSpeechRecognition.latestInstance;
  const capturedCommands = [];
  service.onCommandCaptured((cmd) => capturedCommands.push(cmd));

  service.triggerWakeWord('Hey ByteX');

  // Emit final speech
  rec.emitResult([{ transcript: 'open settings', isFinal: true }], 0);

  // Wait for silence timeout
  await sleep(120);
  assert.equal(capturedCommands.length, 1);
  assert.equal(capturedCommands[0], 'open settings');

  // Wait additional time; verify no second trigger
  await sleep(100);
  assert.equal(capturedCommands.length, 1, 'Must not duplicate command after initial submission');

  service.stop();
});

test('Speech Endpointing - Short valid commands ("hi", "ok", "yes") are preserved and submitted', async () => {
  const service = new WakeWordService();
  service.setSilenceTimeout(60);
  await service.start();

  const rec = MockSpeechRecognition.latestInstance;
  const capturedCommands = [];
  service.onCommandCaptured((cmd) => capturedCommands.push(cmd));

  service.triggerWakeWord('Hey ByteX');

  // Emit short command ("hi" is 2 letters, was blocked by cleanCmd.length >= 3 in old code)
  rec.emitResult([{ transcript: 'hi', isFinal: false }], 0);
  assert.equal(capturedCommands.length, 0);

  await sleep(100);
  assert.equal(capturedCommands.length, 1, 'Short command "hi" must be submitted after silence');
  assert.equal(capturedCommands[0], 'hi');

  service.stop();
});

test('Speech Endpointing - Cancellation clears pending timers and transcript buffers', async () => {
  const service = new WakeWordService();
  service.setSilenceTimeout(100);
  await service.start();

  const rec = MockSpeechRecognition.latestInstance;
  const capturedCommands = [];
  service.onCommandCaptured((cmd) => capturedCommands.push(cmd));

  service.triggerWakeWord('Hey ByteX');

  // Emit partial speech
  rec.emitResult([{ transcript: 'delete all files', isFinal: false }], 0);
  assert.equal(service.hasPendingSpeech(), true);

  // User cancels or interrupts
  service.cancel();
  assert.equal(service.hasPendingSpeech(), false, 'cancel() must clear pending speech buffer');

  // Wait past silence timeout
  await sleep(150);
  assert.equal(capturedCommands.length, 0, 'Cancelled utterance must never be submitted');

  service.stop();
});

test('Speech Endpointing - Recognition restart (onend -> restart) does not duplicate commands', async () => {
  const service = new WakeWordService();
  service.setSilenceTimeout(60);
  await service.start();

  const rec = MockSpeechRecognition.latestInstance;
  const capturedCommands = [];
  service.onCommandCaptured((cmd) => capturedCommands.push(cmd));

  service.triggerWakeWord('Hey ByteX');

  rec.emitResult([{ transcript: 'launch edge browser', isFinal: true }], 0);
  await sleep(100);
  assert.equal(capturedCommands.length, 1);

  // Recognition engine ends (e.g. timeout / network hiccup) and restarts
  rec.emitEnd();

  // Wait restart delay
  await sleep(350);

  // Verify command was not duplicated on restart
  assert.equal(capturedCommands.length, 1, 'Restarting recognition must not duplicate previous command');
  assert.equal(service.hasPendingSpeech(), false);

  service.stop();
});

test('Speech Endpointing - Wake word + command in one breath buffers correctly and submits after silence', async () => {
  const service = new WakeWordService();
  service.setSilenceTimeout(100);
  await service.start();

  const rec = MockSpeechRecognition.latestInstance;
  const capturedCommands = [];
  const wakeWordEvents = [];
  service.onCommandCaptured((cmd) => capturedCommands.push(cmd));
  service.onWakeWord((w) => wakeWordEvents.push(w));

  // User speaks in LISTENING_FOR_WAKE_WORD: "Hey ByteX open notepad" (interim)
  rec.emitResult([{ transcript: 'Hey ByteX open notepad', isFinal: false }], 0);

  // Should transition to LISTENING_FOR_COMMAND, notify wake, but NOT submit command yet!
  assert.equal(service.getState(), 'LISTENING_FOR_COMMAND');
  assert.equal(wakeWordEvents.length, 1);
  assert.equal(capturedCommands.length, 0, 'Command must not be submitted prematurely while speaking');

  // User continues speaking: "Hey ByteX open notepad and write report" (interim update on same index)
  rec.emitResult([{ transcript: 'Hey ByteX open notepad and write report', isFinal: false }], 0);
  assert.equal(capturedCommands.length, 0, 'Interim continuation must not submit prematurely');

  // Now segment finalizes
  rec.emitResult([{ transcript: 'Hey ByteX open notepad and write report', isFinal: true }], 0);
  assert.equal(capturedCommands.length, 0, 'Wait for silence endpointing');

  // Silence window elapses
  await sleep(150);
  assert.equal(capturedCommands.length, 1, 'Full command must be submitted after silence');
  assert.equal(capturedCommands[0], 'open notepad and write report');

  service.stop();
});

test('Speech Endpointing - Stop phrase aborts continuous session without submitting prompt', async () => {
  const service = new WakeWordService();
  service.setSilenceTimeout(100);
  await service.start();

  const rec = MockSpeechRecognition.latestInstance;
  const capturedCommands = [];
  service.onCommandCaptured((cmd) => capturedCommands.push(cmd));

  service.triggerWakeWord('Hey ByteX');
  assert.equal(service.getState(), 'LISTENING_FOR_COMMAND');

  // User says "stop"
  rec.emitResult([{ transcript: 'stop', isFinal: false }], 0);

  // Should transition back to LISTENING_FOR_WAKE_WORD
  assert.equal(service.getState(), 'LISTENING_FOR_WAKE_WORD');
  assert.equal(capturedCommands.length, 0, 'Stop phrase must not be dispatched as an assistant command');
  assert.equal(service.hasPendingSpeech(), false);

  service.stop();
});

test('Speech Endpointing - Empty or punctuation-only transcripts are safely ignored', async () => {
  const service = new WakeWordService();
  service.setSilenceTimeout(60);
  await service.start();

  const rec = MockSpeechRecognition.latestInstance;
  const capturedCommands = [];
  service.onCommandCaptured((cmd) => capturedCommands.push(cmd));

  service.triggerWakeWord('Hey ByteX');

  // Empty / whitespace
  rec.emitResult([{ transcript: '   ', isFinal: true }], 0);
  await sleep(100);
  assert.equal(capturedCommands.length, 0, 'Whitespace-only transcript must not submit');

  // Punctuation noise only
  rec.emitResult([{ transcript: '...?!', isFinal: true }], 0);
  await sleep(100);
  assert.equal(capturedCommands.length, 0, 'Punctuation-only transcript must not submit');

  service.stop();
});
