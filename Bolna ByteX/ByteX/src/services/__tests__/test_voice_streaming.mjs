import test from 'node:test';
import assert from 'node:assert/strict';

// 1. Mock Browser Speech & Media Environment before importing modules
class MockSpeechSynthesisUtterance {
  constructor(text) {
    this.text = text;
    this.rate = 1.0;
    this.volume = 1.0;
    this.pitch = 1.0;
    this.lang = 'en-US';
    this.voice = null;
    this.onstart = null;
    this.onend = null;
    this.onerror = null;
    this.onboundary = null;
  }
}

class MockSpeechSynthesis {
  constructor() {
    this.speaking = false;
    this.pending = false;
    this.paused = false;
    this.currentUtterance = null;
    this.spokenUtterances = [];
    this.cancelCallCount = 0;
  }

  getVoices() {
    return [
      { name: 'Microsoft Jenny Online (Natural) - English (United States)', lang: 'en-US', voiceURI: 'natural-jenny' },
      { name: 'Google US English', lang: 'en-US', voiceURI: 'google-en' },
      { name: 'Microsoft Swara Online (Natural) - Hindi (India)', lang: 'hi-IN', voiceURI: 'natural-swara' },
    ];
  }

  speak(utterance) {
    this.speaking = true;
    this.currentUtterance = utterance;
    this.spokenUtterances.push(utterance);
    if (utterance.onstart) {
      utterance.onstart();
    }
  }

  cancel() {
    this.speaking = false;
    this.currentUtterance = null;
    this.cancelCallCount++;
  }

  // Helper for test simulation
  finishCurrentUtterance() {
    if (this.currentUtterance) {
      const u = this.currentUtterance;
      this.speaking = false;
      this.currentUtterance = null;
      if (u.onend) {
        u.onend();
      }
    }
  }

  errorCurrentUtterance(err = { error: 'audio-busy' }) {
    if (this.currentUtterance) {
      const u = this.currentUtterance;
      this.speaking = false;
      this.currentUtterance = null;
      if (u.onerror) {
        u.onerror(err);
      }
    }
  }
}

class MockSpeechRecognition {
  constructor() {
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
}

// Setup globals
const mockSynthesis = new MockSpeechSynthesis();
globalThis.window = {
  speechSynthesis: mockSynthesis,
  SpeechSynthesisUtterance: MockSpeechSynthesisUtterance,
  SpeechRecognition: MockSpeechRecognition,
};
globalThis.SpeechSynthesisUtterance = MockSpeechSynthesisUtterance;
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
  // If navigator already exists, mock properties
  if (globalThis.navigator) {
    globalThis.navigator.mediaDevices = {
      getUserMedia: async () => ({
        getTracks: () => [{ stop: () => {} }],
      }),
    };
  }
}
globalThis.performance = {
  now: () => Date.now(),
};

// Import TTSService
const { ttsService } = await import('../ttsService.ts');

test('TTS Service - Environment detection', () => {
  assert.equal(ttsService.isSupported(), true);
  const voices = ttsService.getAvailableVoices();
  assert.equal(voices.length, 3);
  const bestVoice = ttsService.getBestVoice('en-US');
  assert.ok(bestVoice);
  assert.ok(bestVoice.voiceURI.includes('natural'));
});

test('TTS Service - Sanitization of reasoning tags, code blocks, URLs and markdown', () => {
  // 1. Internal reasoning tags
  const textWithThink = '<think>I need to plan this step-by-step</think>The weather in Tokyo is sunny.';
  assert.equal(ttsService.sanitizeSpeechSegment(textWithThink), 'The weather in Tokyo is sunny.');

  // 2. Tool calls
  const textWithTool = '<tool_call>{"name": "fetch_data"}</tool_call>Here is the requested information.';
  assert.equal(ttsService.sanitizeSpeechSegment(textWithTool), 'Here is the requested information.');

  // 3. Multi-line code block replacement
  const textWithCode = 'Here is the solution: ```python\nprint("Hello")\n``` It runs smoothly.';
  const sanitizedCode = ttsService.sanitizeSpeechSegment(textWithCode);
  assert.ok(sanitizedCode.includes("I've generated the code and displayed it on screen."));
  assert.ok(!sanitizedCode.includes('print("Hello")'));

  // 4. URL sanitization
  const textWithUrl = 'Check https://example.com/api for details.';
  assert.equal(ttsService.sanitizeSpeechSegment(textWithUrl), 'Check link for details.');

  // 5. Markdown formatting
  const textWithMarkdown = 'This is **bold** and *italic* with `inline code`.';
  assert.equal(ttsService.sanitizeSpeechSegment(textWithMarkdown), 'This is bold and italic with code snippet.');
});

test('TTS Service - Incremental streaming and early playback initiation', () => {
  ttsService.stop();
  mockSynthesis.spokenUtterances = [];

  // Feed chunks of Sentence 1 progressively
  ttsService.feedStreamChunk('Hello ');
  assert.equal(mockSynthesis.spokenUtterances.length, 0, 'Should not speak before sentence boundary');

  ttsService.feedStreamChunk('world! ');
  // First sentence is complete ("Hello world!") -> speech playback begins immediately
  assert.equal(mockSynthesis.spokenUtterances.length, 1, 'Playback must begin immediately upon first sentence completion');
  assert.equal(mockSynthesis.spokenUtterances[0].text, 'Hello world!');
  assert.equal(ttsService.isSpeaking(), true);

  // Feed Sentence 2 while Sentence 1 is still actively speaking
  ttsService.feedStreamChunk('This is streaming speech. ');
  // Utterance 2 must be queued, not interrupting utterance 1
  assert.equal(mockSynthesis.spokenUtterances.length, 1, 'Sentence 2 stays queued until Sentence 1 ends');
  assert.equal(ttsService.getQueueLength(), 1, 'Queue has exactly 1 waiting segment');

  // Complete Sentence 1
  mockSynthesis.finishCurrentUtterance();

  // Sentence 2 should now be dequeued and actively spoken
  assert.equal(mockSynthesis.spokenUtterances.length, 2, 'Sentence 2 begins speaking after Sentence 1 ends');
  assert.equal(mockSynthesis.spokenUtterances[1].text, 'This is streaming speech.');

  // Feed trailing text without trailing period, then flush at ASSISTANT_COMPLETE
  ttsService.feedStreamChunk('Final closing remarks');
  assert.equal(mockSynthesis.spokenUtterances.length, 2);
  ttsService.flushStream();
  assert.equal(ttsService.getQueueLength(), 1, 'Flushed text is enqueued');

  mockSynthesis.finishCurrentUtterance();
  assert.equal(mockSynthesis.spokenUtterances.length, 3);
  assert.equal(mockSynthesis.spokenUtterances[2].text, 'Final closing remarks');

  mockSynthesis.finishCurrentUtterance();
  assert.equal(ttsService.isSpeaking(), false);
});

test('TTS Service - Duplicate-segment prevention', () => {
  ttsService.stop();
  mockSynthesis.spokenUtterances = [];

  ttsService.queueSegment('Processing your request.');
  ttsService.queueSegment('Processing your request.'); // Exact duplicate
  ttsService.queueSegment('processing your request.'); // Case-insensitive duplicate

  assert.equal(mockSynthesis.spokenUtterances.length, 1);
  assert.equal(ttsService.getQueueLength(), 0, 'Duplicates must not be enqueued');

  mockSynthesis.finishCurrentUtterance();
  assert.equal(mockSynthesis.spokenUtterances.length, 1);
});

test('TTS Service - Interruption and queue cancellation', () => {
  ttsService.stop();
  mockSynthesis.spokenUtterances = [];
  mockSynthesis.cancelCallCount = 0;

  // Queue multiple segments
  ttsService.queueSegment('First item in progress.');
  ttsService.queueSegment('Second item waiting.');
  ttsService.queueSegment('Third item waiting.');

  assert.equal(mockSynthesis.spokenUtterances.length, 1);
  assert.equal(ttsService.getQueueLength(), 2);
  assert.equal(ttsService.isSpeaking(), true);

  // User interrupts (e.g. presses push-to-talk or types new command)
  ttsService.stop();

  assert.ok(mockSynthesis.cancelCallCount >= 1, 'speechSynthesis.cancel() must be called');
  assert.equal(ttsService.getQueueLength(), 0, 'Queue must be empty after stop');
  assert.equal(ttsService.isSpeaking(), false, 'isSpeaking must be false after stop');

  // Even if onend was triggered by cancel, queue does not advance
  mockSynthesis.finishCurrentUtterance();
  assert.equal(mockSynthesis.spokenUtterances.length, 1, 'No further segments should play');
});

test('TTS Service - Playback error recovery prevents queue deadlock', () => {
  ttsService.stop();
  mockSynthesis.spokenUtterances = [];

  ttsService.queueSegment('Segment that triggers audio error.');
  ttsService.queueSegment('Subsequent segment that should still play.');

  assert.equal(mockSynthesis.spokenUtterances.length, 1);
  assert.equal(ttsService.getQueueLength(), 1);

  // Trigger error on first segment
  mockSynthesis.errorCurrentUtterance({ error: 'synthesis-unavailable' });

  // Error handler must advance the queue to next segment rather than hanging
  assert.equal(mockSynthesis.spokenUtterances.length, 2);
  assert.equal(mockSynthesis.spokenUtterances[1].text, 'Subsequent segment that should still play.');

  mockSynthesis.finishCurrentUtterance();
  assert.equal(ttsService.isSpeaking(), false);
});

test('TTS Service - Long clause segmentation (>120 chars without period)', () => {
  ttsService.stop();
  mockSynthesis.spokenUtterances = [];

  const longClause = 'Here is a very detailed explanation of the architecture, where multiple subsystems interact continuously across the network without stopping; and here is the conclusion.';
  
  // Feed long clause in chunks
  ttsService.feedStreamChunk(longClause);

  // Buffer is > 120 chars with comma/semicolon -> splits early so speech is not delayed
  assert.ok(mockSynthesis.spokenUtterances.length >= 1, 'Should segment before reaching end of 150+ char clause');
  ttsService.flushStream();
  mockSynthesis.finishCurrentUtterance();
  ttsService.stop();
});

test('STT Service - Mocked Recognition flow and error handling', async () => {
  const { default: sttService } = await import('../sttService.ts');
  
  assert.equal(sttService.isSupported(), true);

  let capturedTranscript = '';
  let capturedError = '';
  let capturedState = false;

  const unsubResult = sttService.onResult((text) => { capturedTranscript = text; });
  const unsubError = sttService.onError((err) => { capturedError = err; });
  const unsubState = sttService.onStateChange((state) => { capturedState = state; });

  // 1. Test Start & State
  const started = await sttService.start();
  assert.equal(started, true);
  assert.equal(capturedState, true);

  // 2. Simulate Result Event
  const mockRec = sttService.recognition;
  assert.ok(mockRec);

  const mockEvent = {
    resultIndex: 0,
    results: [
      [{ transcript: 'Open calculator and calculate twenty plus five' }]
    ]
  };
  mockRec.results = mockEvent.results;
  mockRec.onresult(mockEvent);

  assert.equal(capturedTranscript, 'Open calculator and calculate twenty plus five');

  // 3. Simulate Error Event
  mockRec.onerror({ error: 'not-allowed' });
  assert.ok(capturedError.includes('Microphone permission') || capturedError.includes('denied'));

  // 4. Cancel
  sttService.cancel();
  assert.equal(sttService.getIsListening(), false);

  unsubResult();
  unsubError();
  unsubState();
});
