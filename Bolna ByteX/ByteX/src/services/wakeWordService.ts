import ttsService from './ttsService.ts';

export type WakeWordState =
  | 'DISABLED'
  | 'IDLE'
  | 'LISTENING_FOR_WAKE_WORD'
  | 'WAKE_DETECTED'
  | 'LISTENING_FOR_COMMAND'
  | 'PROCESSING'
  | 'SPEAKING'
  | 'CONTINUOUS_LISTENING'
  | 'ERROR';

export type WakeWordStateCallback = (state: WakeWordState) => void;
export type WakeWordEventCallback = (commandText: string) => void;
export type WakeWordErrorCallback = (error: string) => void;

const INSTANCE_ID = `WAKE_SRV_${Math.random().toString(36).substring(2, 7).toUpperCase()}`;

export function normalizeWakeTranscript(text: string): string {
  if (!text) return '';
  let clean = text.toLowerCase();
  clean = clean.replace(/['’]/g, '');
  clean = clean.replace(/[^a-z0-9\s]/g, ' ');
  clean = clean.replace(/\s+/g, ' ').trim();
  return clean;
}

const BYTEX_ALIASES = [
  'byte\\s*axe',
  'bite\\s*axe',
  'byte\\s*ex',
  'bite\\s*ex',
  'byte\\s*x',
  'bite\\s*x',
  'bit\\s*x',
  'b\\s*t\\s*x',
  'bytex',
  'bitex',
  'byteks',
  'bytes',
  'bites',
  'byte',
  'bite',
  'btx'
];

const PREFIX_PHRASES = [
  'hey\\s+there',
  'hi\\s+there',
  'hello\\s+there',
  'whats\\s+up',
  'whats\\s+happening',
  'how\\s+are\\s+you',
  'hello',
  'hey',
  'hi',
  'yo',
  'a'
];

const STANDALONE_ALIASES = [
  'bytex',
  'byte\\s*x',
  'bitex',
  'a\\s+bytex',
  'a\\s+byte\\s*x'
];

const aliasPattern = BYTEX_ALIASES.join('|');
const prefixPattern = PREFIX_PHRASES.join('|');
const standalonePattern = STANDALONE_ALIASES.join('|');

const WAKE_REGEX = new RegExp(
  `^(?:(?:(?:${prefixPattern})\\s+)(?:${aliasPattern})|(?:${standalonePattern}))\\b\\s*(.*)$`,
  'i'
);

export function matchWakeWord(transcript: string): { isMatch: boolean; commandText: string; matchedAlias: string } {
  if (!transcript || !transcript.trim()) {
    return { isMatch: false, commandText: '', matchedAlias: '' };
  }

  const raw = transcript.trim();
  const norm = normalizeWakeTranscript(raw);

  const match = norm.match(WAKE_REGEX);
  if (match) {
    const remNorm = match[1] ? match[1].trim() : '';
    let remaining = '';

    if (remNorm) {
      const rawWords = raw.split(/\s+/);
      const normWords = norm.split(/\s+/);
      const remWordsCount = remNorm.split(/\s+/).length;
      const consumedCount = normWords.length - remWordsCount;
      if (consumedCount >= 0 && consumedCount < rawWords.length) {
        remaining = rawWords.slice(consumedCount).join(' ').trim();
      } else {
        remaining = remNorm;
      }
    }

    remaining = remaining.replace(/^[.!?,\s:]+/, '').replace(/[.!?,\s:]+$/, '').trim();
    const matchedAlias = norm.slice(0, norm.length - remNorm.length).trim();

    return {
      isMatch: true,
      commandText: remaining,
      matchedAlias,
    };
  }

  return { isMatch: false, commandText: '', matchedAlias: '' };
}

export function isStandbyPhrase(text: string): boolean {
  if (!text || !text.trim()) return false;
  const norm = normalizeWakeTranscript(text);
  const standbyPhrases = [
    'stop listening',
    'go to sleep',
    'goodbye',
    'bye bytex',
    'bye byte',
    'exit',
    'thats all',
    'that is all',
    'standby',
    'go to standby',
    'never mind',
    'nevermind'
  ];
  return standbyPhrases.includes(norm);
}

export function isStopSpeechPhrase(text: string): boolean {
  if (!text || !text.trim()) return false;
  const norm = normalizeWakeTranscript(text);
  const stopSpeechPhrases = [
    'stop',
    'wait stop',
    'stop it',
    'stop speaking',
    'stop talking',
    'cancel',
    'pause',
    'quiet',
    'silence',
    'shut up'
  ];
  return stopSpeechPhrases.includes(norm);
}

export function stripStopSpeechPrefix(text: string): string {
  if (!text || !text.trim()) return '';
  const norm = normalizeWakeTranscript(text);
  const prefixes = [
    'wait stop',
    'stop speaking',
    'stop talking',
    'stop it',
    'stop',
    'cancel',
    'quiet',
    'silence',
    'shut up'
  ];
  for (const prefix of prefixes) {
    if (norm === prefix) {
      return '';
    }
    if (norm.startsWith(prefix + ' ')) {
      const words = text.trim().split(/\s+/);
      const prefixWordCount = prefix.split(/\s+/).length;
      return words.slice(prefixWordCount).join(' ').trim();
    }
  }
  return text.trim();
}

export function isStopPhrase(text: string): boolean {
  return isStandbyPhrase(text) || isStopSpeechPhrase(text);
}

export class WakeWordService {
  public readonly instanceId: string = INSTANCE_ID;
  private state: WakeWordState = 'DISABLED';
  private keyword: string = 'Hey ByteX';
  private recognition: any = null;
  private isPaused: boolean = false;
  private isEnabled: boolean = false;
  private continuousListeningEnabled: boolean = false;
  private commandTimeoutMs: number = 7000;
  private conversationTimeoutMs: number = 15000;

  private wakeResultIndex: number = -1;
  private lastError: string = '';

  private lastTranscript: string = '';
  private lastNormalizedTranscript: string = '';
  private lastMatchedAlias: string = '';
  private lastIsFinal: boolean = false;
  private lastResultIndex: number = -1;
  private lastEventTime: string = 'N/A';
  private permissionState: string = 'UNKNOWN';

  // Speech Endpointing & Silence Window (Function 562)
  private silenceTimeoutMs: number = 1800; // 1.8s trailing silence window
  private endpointingTimer: any = null;
  private accumulatedCommandText: string = '';
  private pendingInterimText: string = '';
  private lastFinalizedResultIndex: number = -1;
  private lastSubmittedCommand: string = '';
  private lastSubmittedTime: number = 0;

  private recognitionRunning: boolean = false;
  private startingRecognition: boolean = false;
  private restartTimer: any = null;

  private retryCount: number = 0;
  private maxRetries: number = 5;
  private commandTimeoutTimer: any = null;
  private continuousTimeoutTimer: any = null;

  private stateCallbacks: Set<WakeWordStateCallback> = new Set();
  private wakeWordCallbacks: Set<WakeWordEventCallback> = new Set();
  private commandCallbacks: Set<WakeWordEventCallback> = new Set();
  private errorCallbacks: Set<WakeWordErrorCallback> = new Set();

  constructor() {
    console.log(`[WakeDebug] WakeWordService instance = ${this.instanceId} initializing`);
    this.initRecognition();
  }

  public isSupported(): boolean {
    const supported =
      typeof window !== 'undefined' &&
      ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window);
    console.log(`[WakeDebug] isSupported = ${supported} (SpeechRecognition: ${typeof (window as any).SpeechRecognition}, webkitSpeechRecognition: ${typeof (window as any).webkitSpeechRecognition})`);
    return supported;
  }

  public setContinuousListening(enabled: boolean) {
    console.log(`[WakeDebug] setContinuousListening = ${enabled} on instance ${this.instanceId}`);
    this.continuousListeningEnabled = enabled;
  }

  public getContinuousListening(): boolean {
    return this.continuousListeningEnabled;
  }

  public setTimeouts(commandSec: number = 7, conversationSec: number = 15) {
    this.commandTimeoutMs = commandSec * 1000;
    this.conversationTimeoutMs = conversationSec * 1000;
  }

  public setSilenceTimeout(timeoutMs: number) {
    this.silenceTimeoutMs = Math.max(100, timeoutMs);
  }

  public getSilenceTimeout(): number {
    return this.silenceTimeoutMs;
  }

  public hasPendingSpeech(): boolean {
    return !!(this.accumulatedCommandText.trim() || this.pendingInterimText.trim());
  }

  public getAccumulatedTranscript(): string {
    let full = this.accumulatedCommandText.trim();
    if (this.pendingInterimText.trim()) {
      full = full ? `${full} ${this.pendingInterimText.trim()}` : this.pendingInterimText.trim();
    }
    return full;
  }

  public clearEndpointingTimer() {
    if (this.endpointingTimer) {
      clearTimeout(this.endpointingTimer);
      this.endpointingTimer = null;
    }
  }

  public resetEndpointingState() {
    this.clearEndpointingTimer();
    this.accumulatedCommandText = '';
    this.pendingInterimText = '';
    this.lastFinalizedResultIndex = -1;
  }

  private scheduleEndpointingTimer(delayMs?: number) {
    this.clearEndpointingTimer();
    const delay = delayMs !== undefined ? delayMs : this.silenceTimeoutMs;
    this.endpointingTimer = setTimeout(() => {
      this.finalizeCommand();
    }, delay);
  }

  public finalizeCommand() {
    this.clearEndpointingTimer();

    let fullText = this.accumulatedCommandText.trim();
    if (this.pendingInterimText.trim()) {
      fullText = fullText ? `${fullText} ${this.pendingInterimText.trim()}` : this.pendingInterimText.trim();
    }

    let cleanCmd = fullText.replace(/^[.!?,\s:]+/, '').replace(/[.!?,\s:]+$/, '').trim();

    // Reset transcript buffers immediately to prevent duplicate or re-entrant submission
    this.accumulatedCommandText = '';
    this.pendingInterimText = '';
    this.lastFinalizedResultIndex = -1;
    this.wakeResultIndex = -1;

    if (!cleanCmd || cleanCmd.length === 0) {
      console.log('[WakeDebug] finalizeCommand: Empty transcript, skipping submission.');
      return;
    }

    if (this.handleStopOrStandby(cleanCmd)) {
      return;
    }

    const stripped = stripStopSpeechPrefix(cleanCmd);
    if (stripped !== cleanCmd) {
      ttsService.stop(true);
      cleanCmd = stripped;
    }

    if (!cleanCmd || cleanCmd.length === 0) {
      console.log('[WakeDebug] finalizeCommand: Empty transcript after stop prefix, remaining in CONTINUOUS_LISTENING.');
      if (this.state === 'CONTINUOUS_LISTENING') {
        this.startContinuousTimeout();
      }
      return;
    }

    const now = Date.now();
    if (cleanCmd.toLowerCase() === this.lastSubmittedCommand.toLowerCase() && (now - this.lastSubmittedTime < 1500)) {
      console.log(`[WakeDebug] finalizeCommand: Duplicate command suppressed within 1500ms: '${cleanCmd}'`);
      return;
    }

    this.lastSubmittedCommand = cleanCmd;
    this.lastSubmittedTime = now;

    console.log(`[WakeDebug] finalizeCommand: Successfully submitting voice command: '${cleanCmd}'`);
    this.clearCommandTimeout();
    this.clearContinuousTimeout();
    this.handleCommandCaptured(cleanCmd);
  }

  public cancel() {
    console.log(`[WakeDebug] cancel() called on instance ${this.instanceId}`);
    this.resetEndpointingState();
    this.clearCommandTimeout();
    this.clearContinuousTimeout();
    this.resetToListening();
  }

  public getKeyword(): string {
    return this.keyword;
  }

  public getState(): WakeWordState {
    return this.state;
  }

  public getLastError(): string {
    return this.lastError;
  }

  public getDiagnosticData() {
    return {
      instanceId: this.instanceId,
      speechRecognitionSupported: typeof (window as any).SpeechRecognition !== 'undefined',
      webkitSpeechRecognitionSupported: typeof (window as any).webkitSpeechRecognition !== 'undefined',
      enabled: this.isEnabled,
      continuousListeningEnabled: this.continuousListeningEnabled,
      state: this.state,
      recognitionInstanceExists: !!this.recognition,
      recognitionRunning: this.recognitionRunning || this.startingRecognition,
      permissionState: this.permissionState,
      lastTranscript: this.lastTranscript,
      lastNormalizedTranscript: this.lastNormalizedTranscript,
      lastMatchedAlias: this.lastMatchedAlias,
      lastIsFinal: this.lastIsFinal,
      lastResultIndex: this.lastResultIndex,
      lastEventTime: this.lastEventTime,
      lastError: this.lastError,
      silenceTimeoutMs: this.silenceTimeoutMs,
      accumulatedCommandText: this.accumulatedCommandText,
      pendingInterimText: this.pendingInterimText,
      lastSubmittedCommand: this.lastSubmittedCommand,
    };
  }

  public isListening(): boolean {
    return (
      this.state === 'LISTENING_FOR_WAKE_WORD' ||
      this.state === 'WAKE_DETECTED' ||
      this.state === 'LISTENING_FOR_COMMAND' ||
      this.state === 'CONTINUOUS_LISTENING'
    );
  }

  public isRunning(): boolean {
    return this.recognitionRunning || this.startingRecognition;
  }

  private setState(newState: WakeWordState) {
    if (this.state !== newState) {
      console.log(`[WakeDebug] state transition: ${this.state} -> ${newState} (instance: ${this.instanceId})`);
      this.state = newState;
      this.notifyState();
    }
  }

  private initRecognition() {
    if (!this.isSupported()) {
      console.warn(`[WakeDebug] SpeechRecognition API unavailable in this browser.`);
      return;
    }

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    this.recognition = new SpeechRecognition();
    console.log(`[WakeDebug] recognition created on instance ${this.instanceId}`);

    this.recognition.continuous = true;
    this.recognition.interimResults = true;
    this.recognition.maxAlternatives = 3;
    this.recognition.lang = 'en-US';

    this.recognition.onstart = () => {
      console.log(`[WakeDebug] ONSTART (instance: ${this.instanceId})`);
      this.startingRecognition = false;
      this.recognitionRunning = true;
      this.retryCount = 0;
      if (this.state === 'DISABLED' || this.state === 'ERROR' || this.state === 'IDLE') {
        this.setState('LISTENING_FOR_WAKE_WORD');
      }
    };

    this.recognition.onresult = (event: any) => {
      if (this.isPaused || !this.isEnabled) {
        console.log(`[WakeDebug] ONRESULT ignored (isPaused: ${this.isPaused}, isEnabled: ${this.isEnabled})`);
        return;
      }

      const resultIndex = event.resultIndex;
      console.log(`[WakeDebug] ONRESULT fired (resultIndex: ${resultIndex}, totalResults: ${event.results.length})`);

      for (let i = resultIndex; i < event.results.length; i++) {
        const resultObj = event.results[i];
        if (!resultObj) continue;

        const transcript = resultObj[0]?.transcript;
        const isFinal = !!resultObj.isFinal;
        if (!transcript || !transcript.trim()) continue;

        const normTranscript = normalizeWakeTranscript(transcript);
        this.lastTranscript = transcript;
        this.lastNormalizedTranscript = normTranscript;
        this.lastIsFinal = isFinal;
        this.lastResultIndex = i;
        this.lastEventTime = new Date().toLocaleTimeString();

        console.log(`[WakeDebug] raw transcript: '${transcript}' (isFinal: ${isFinal}, idx: ${i})`);
        console.log(`[WakeDebug] normalized transcript: '${normTranscript}'`);

        // 1. In LISTENING_FOR_WAKE_WORD state
        if (this.state === 'LISTENING_FOR_WAKE_WORD') {
          const matchRes = matchWakeWord(transcript);
          console.log(`[WakeDebug] match result:`, matchRes);

          if (matchRes.isMatch) {
            console.log(`[WakeDebug] matched alias: '${matchRes.matchedAlias}'`);
            console.log(`[WakeDebug] wake detected! extracted command: '${matchRes.commandText}'`);
            this.lastMatchedAlias = matchRes.matchedAlias;
            this.wakeResultIndex = i;

            if (matchRes.commandText && matchRes.commandText.length > 0) {
              if (isStopPhrase(matchRes.commandText)) {
                console.log(`[WakeDebug] Stop phrase detected during wake extraction: '${matchRes.commandText}'`);
                this.handleStopPhrase();
                break;
              }
              // Utterance contained both wake phrase and command (e.g. "Hey ByteX, open Chrome")
              this.setState('WAKE_DETECTED');
              this.notifyWakeWord(matchRes.commandText);
              this.setState('LISTENING_FOR_COMMAND');
              this.clearCommandTimeout();

              if (isFinal) {
                this.accumulatedCommandText = matchRes.commandText.trim();
                this.pendingInterimText = '';
                this.lastFinalizedResultIndex = i;
              } else {
                this.pendingInterimText = matchRes.commandText.trim();
              }
              this.scheduleEndpointingTimer();
            } else {
              // User only said "Hey ByteX", transition to LISTENING_FOR_COMMAND
              console.log('[WakeDebug] entering command listening');
              this.setState('WAKE_DETECTED');
              this.notifyWakeWord('');
              this.setState('LISTENING_FOR_COMMAND');
              if (isFinal) {
                this.lastFinalizedResultIndex = i;
              }
              this.startCommandTimeout();
            }
            break;
          }
        }
        // 2. In LISTENING_FOR_COMMAND or CONTINUOUS_LISTENING state
        else if (this.state === 'LISTENING_FOR_COMMAND' || this.state === 'CONTINUOUS_LISTENING') {
          // Ignore or update command text for the wakeResultIndex itself
          if (i === this.wakeResultIndex) {
            const matchRes = matchWakeWord(transcript);
            if (matchRes.isMatch && matchRes.commandText && matchRes.commandText.length > 0) {
              if (this.handleStopOrStandby(matchRes.commandText)) {
                break;
              }
              const strippedCmd = stripStopSpeechPrefix(matchRes.commandText);
              const cmdToUse = strippedCmd !== matchRes.commandText ? strippedCmd : matchRes.commandText;
              if (!cmdToUse) {
                break;
              }
              console.log(`[WakeDebug] command updated from wake stream: '${cmdToUse}' (isFinal: ${isFinal})`);
              if (isFinal) {
                this.accumulatedCommandText = cmdToUse.trim();
                this.pendingInterimText = '';
                this.lastFinalizedResultIndex = i;
              } else {
                this.pendingInterimText = cmdToUse.trim();
              }
              this.scheduleEndpointingTimer();
              break;
            }
            if (isFinal) {
              this.lastFinalizedResultIndex = i;
            }
            console.log(`[WakeDebug] ignoring finalization of wake phrase at idx ${i}`);
            continue;
          }

          // If this result index was already finalized in a prior event/loop, skip it
          if (i <= this.lastFinalizedResultIndex) {
            console.log(`[WakeDebug] skipping already finalized result index ${i}`);
            continue;
          }

          const matchRes = matchWakeWord(transcript);
          const finalCommand = matchRes.isMatch ? matchRes.commandText : transcript.trim();
          let cleanCmd = finalCommand.replace(/^[.!?,\s:]+/, '').replace(/[.!?,\s:]+$/, '').trim();

          if (cleanCmd && cleanCmd.length > 0) {
            if (this.handleStopOrStandby(cleanCmd)) {
              break;
            }
            const strippedCmd = stripStopSpeechPrefix(cleanCmd);
            if (strippedCmd !== cleanCmd) {
              cleanCmd = strippedCmd;
              if (!cleanCmd) {
                break;
              }
            }

            // User is actively speaking: clear the command timeout
            this.clearCommandTimeout();
            if (this.state === 'CONTINUOUS_LISTENING') {
              this.startContinuousTimeout();
            }

            if (isFinal) {
              console.log(`[WakeDebug] Segment finalized at idx ${i}: '${cleanCmd}'`);
              if (this.accumulatedCommandText) {
                this.accumulatedCommandText += ' ' + cleanCmd;
              } else {
                this.accumulatedCommandText = cleanCmd;
              }
              this.pendingInterimText = '';
              this.lastFinalizedResultIndex = i;
            } else {
              console.log(`[WakeDebug] Interim speech update at idx ${i}: '${cleanCmd}'`);
              this.pendingInterimText = cleanCmd;
            }

            // Reset silence endpointing window (1.8s)
            this.scheduleEndpointingTimer();
          }
        }
      }
    };

    this.recognition.onerror = (event: any) => {
      const err = event.error;
      console.warn(`[WakeDebug] recognition error: ${err} (instance: ${this.instanceId})`);
      this.startingRecognition = false;
      this.lastError = err;

      if (err === 'no-speech' || err === 'aborted') {
        return;
      }

      if (err === 'audio-capture') {
        console.error('[WakeDebug] microphone audio-capture error');
        this.resetEndpointingState();
        this.permissionState = 'BUSY';
        this.lastError = 'Microphone is unavailable or being used by another application.';
        this.setState('ERROR');
        this.notifyError(this.lastError);
        this.stop();
        return;
      }

      if (err === 'not-allowed' || err === 'service-not-allowed') {
        console.error('[WakeDebug] microphone permission denied or service blocked');
        this.resetEndpointingState();
        this.permissionState = 'DENIED';
        this.lastError = 'Microphone permission is required for wake-word activation.';
        this.setState('ERROR');
        this.notifyError(this.lastError);
        this.stop();
        return;
      }

      this.lastError = `Speech recognition error: ${err}`;
      this.handleBoundedRetry();
    };

    this.recognition.onend = () => {
      console.log(`[WakeDebug] recognition onend (state=${this.state}, enabled=${this.isEnabled}, paused=${this.isPaused})`);
      this.recognitionRunning = false;
      this.startingRecognition = false;

      // Flush any accumulated speech before restarting
      if (this.hasPendingSpeech()) {
        console.log('[WakeDebug] onend flushing accumulated speech before restart');
        this.finalizeCommand();
      } else {
        this.clearEndpointingTimer();
      }

      if (this.isEnabled && !this.isPaused && this.state !== 'ERROR' && this.state !== 'DISABLED') {
        console.log('[WakeDebug] scheduling restart after onend');
        this.scheduleRestart(300);
      }
    };
  }

  public handleStandbyPhrase() {
    console.log('[WakeDebug] Explicit return-to-standby triggered.');
    this.resetEndpointingState();
    this.clearCommandTimeout();
    this.clearContinuousTimeout();
    this.resetToListening();
    this.notifyError('Okay.');
  }

  public handleStopOrStandby(cleanCmd: string): boolean {
    if (!cleanCmd || !cleanCmd.trim()) return false;

    // 1. Explicit return-to-standby commands (e.g., "stop listening", "goodbye", "exit", "that's all")
    if (isStandbyPhrase(cleanCmd)) {
      console.log(`[WakeDebug] Explicit return-to-standby phrase detected: '${cleanCmd}' in state ${this.state}`);
      this.handleStandbyPhrase();
      return true;
    }

    // 2. Stop assistant speech commands (e.g., "stop", "wait stop", "stop talking", "cancel")
    if (isStopSpeechPhrase(cleanCmd)) {
      // If ByteX is speaking or in active conversation (CONTINUOUS_LISTENING):
      // "Stop" means stop the assistant's speech, NOT stop microphone listening!
      if (ttsService.isSpeaking() || this.state === 'CONTINUOUS_LISTENING') {
        console.log(`[WakeDebug] Stop speech phrase captured ('${cleanCmd}'): stopping TTS, remaining in CONTINUOUS_LISTENING.`);
        ttsService.stop(true);
        this.resetEndpointingState();
        this.clearCommandTimeout();
        this.isPaused = false;
        this.setState('CONTINUOUS_LISTENING');
        this.startContinuousTimeout();
        return true;
      }

      // If in initial wake LISTENING_FOR_COMMAND and not speaking:
      // Abort command and return to standby (Function 562 endpointing behavior)
      if (this.state === 'LISTENING_FOR_COMMAND') {
        console.log(`[WakeDebug] Command abort in LISTENING_FOR_COMMAND: returning to standby.`);
        this.handleStandbyPhrase();
        return true;
      }
    }

    // 3. Leading stop speech prefix in a command (e.g., "stop, tell me a joke")
    const stripped = stripStopSpeechPrefix(cleanCmd);
    if (stripped !== cleanCmd) {
      console.log(`[WakeDebug] Leading stop prefix stripped from '${cleanCmd}', remaining command: '${stripped}'`);
      ttsService.stop(true);
      if (!stripped) {
        this.resetEndpointingState();
        this.clearCommandTimeout();
        this.isPaused = false;
        this.setState('CONTINUOUS_LISTENING');
        this.startContinuousTimeout();
        return true;
      }
    }

    return false;
  }

  private handleStopPhrase() {
    this.handleStandbyPhrase();
  }

  private handleCommandCaptured(commandText: string) {
    console.log(`[WakeDebug] handleCommandCaptured: '${commandText}'`);
    this.setState('PROCESSING');
    this.notifyCommand(commandText);
  }

  private startCommandTimeout() {
    this.clearCommandTimeout();
    this.commandTimeoutTimer = setTimeout(() => {
      if (this.state === 'LISTENING_FOR_COMMAND') {
        console.log('[WakeDebug] Command window timed out with no speech. Returning to LISTENING_FOR_WAKE_WORD.');
        this.notifyError("I didn't hear a command.");
        this.resetToListening();
      }
    }, this.commandTimeoutMs);
  }

  private clearCommandTimeout() {
    if (this.commandTimeoutTimer) {
      clearTimeout(this.commandTimeoutTimer);
      this.commandTimeoutTimer = null;
    }
  }

  public startContinuousTimeout() {
    this.clearContinuousTimeout();
    this.continuousTimeoutTimer = setTimeout(() => {
      if (this.state === 'CONTINUOUS_LISTENING') {
        console.log('[WakeDebug] Continuous listening session timed out (15s). Returning to LISTENING_FOR_WAKE_WORD.');
        this.resetToListening();
      }
    }, this.conversationTimeoutMs);
  }

  private clearContinuousTimeout() {
    if (this.continuousTimeoutTimer) {
      clearTimeout(this.continuousTimeoutTimer);
      this.continuousTimeoutTimer = null;
    }
  }

  private clearRestartTimer() {
    if (this.restartTimer) {
      clearTimeout(this.restartTimer);
      this.restartTimer = null;
    }
  }

  private scheduleRestart(delayMs: number = 300) {
    this.clearRestartTimer();
    if (!this.isEnabled || this.isPaused || this.state === 'ERROR' || this.state === 'DISABLED') {
      return;
    }
    console.log(`[WakeDebug] Scheduling recognition restart in ${delayMs}ms...`);
    this.restartTimer = setTimeout(() => {
      this.restartTimer = null;
      this.restartRecognition();
    }, delayMs);
  }

  public resetToListening() {
    this.resetEndpointingState();
    this.clearCommandTimeout();
    this.clearContinuousTimeout();
    this.wakeResultIndex = -1;
    if (this.isEnabled && !this.isPaused) {
      this.setState('LISTENING_FOR_WAKE_WORD');
    } else {
      this.setState('IDLE');
    }
  }

  public onTTSFinished() {
    console.log(`[WakeDebug] onTTSFinished called (state: ${this.state})`);
    if (!this.isEnabled) return;
    this.resetEndpointingState();

    console.log('[WakeDebug] Normal response finished: entering CONTINUOUS_LISTENING for active conversation.');
    this.isPaused = false;
    this.setState('CONTINUOUS_LISTENING');
    this.startContinuousTimeout();
    this.clearRestartTimer();
    this.restartRecognition();
  }

  public onInterruption() {
    console.log(`[WakeDebug] onInterruption called (enabled: ${this.isEnabled})`);
    if (!this.isEnabled) return;
    this.resetEndpointingState();
    this.isPaused = false;
    // Enter CONTINUOUS_LISTENING immediately so the user can speak their follow-up command hands-free without "Hey ByteX"
    this.setState('CONTINUOUS_LISTENING');
    this.startContinuousTimeout();
    this.clearRestartTimer();
    this.restartRecognition();
  }

  public onCommandFinished() {
    console.log(`[WakeDebug] onCommandFinished called (state: ${this.state})`);
    if (!this.isEnabled) return;
    this.resetEndpointingState();

    console.log('[WakeDebug] Command finished: entering CONTINUOUS_LISTENING for active conversation.');
    this.isPaused = false;
    this.setState('CONTINUOUS_LISTENING');
    this.startContinuousTimeout();
    this.clearRestartTimer();
    this.restartRecognition();
  }

  private restartRecognition() {
    if (!this.recognition || !this.isEnabled || this.isPaused) {
      console.log(`[WakeDebug] restartRecognition skipped (rec: ${!!this.recognition}, enabled: ${this.isEnabled}, paused: ${this.isPaused})`);
      return;
    }

    if (this.recognitionRunning || this.startingRecognition) {
      console.log(`[WakeDebug] restartRecognition skipped (already running or starting)`);
      return;
    }

    try {
      console.log(`[WakeDebug] recognition start on instance ${this.instanceId}`);
      this.startingRecognition = true;
      this.recognition.start();
    } catch (e: any) {
      this.startingRecognition = false;
      if (e.name === 'InvalidStateError' || (e.message && e.message.includes('already started'))) {
        console.log('[WakeDebug] recognition already started cleanly (InvalidStateError)');
        this.recognitionRunning = true;
        return;
      }
      console.warn('[WakeDebug] recognition start exception:', e);
      this.handleBoundedRetry();
    }
  }

  private handleBoundedRetry() {
    if (this.retryCount < this.maxRetries) {
      this.retryCount++;
      const delay = Math.min(1000 * Math.pow(2, this.retryCount - 1), 5000);
      console.log(`[WakeDebug] Retrying recognition (${this.retryCount}/${this.maxRetries}) in ${delay}ms...`);
      this.scheduleRestart(delay);
    } else {
      console.warn('[WakeDebug] Maximum restart attempts reached. Returning to ERROR/IDLE.');
      this.lastError = 'Wake-word recognition stopped after repeated connection errors.';
      this.setState('ERROR');
      this.notifyError(this.lastError);
    }
  }

  public async start() {
    console.log(`[WakeDebug] START_CALLED on instance ${this.instanceId}`);

    if (!this.isSupported()) {
      this.lastError = 'Wake-word voice activation is unavailable (speech recognition unsupported by this browser).';
      this.setState('ERROR');
      this.notifyError(this.lastError);
      return;
    }

    // Explicitly request microphone permission first via getUserMedia and immediately release stream tracks
    if (typeof navigator !== 'undefined' && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      try {
        console.log('[WakeDebug] requesting microphone permission via getUserMedia...');
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        this.permissionState = 'GRANTED';
        console.log('[WakeDebug] microphone permission granted. Releasing permission test MediaStream tracks.');
        // CRITICAL FIX: Release MediaStream tracks immediately so microphone hardware is not held locked!
        stream.getTracks().forEach((track) => track.stop());
      } catch (err: any) {
        console.error('[WakeDebug] microphone permission denied by user or device:', err);
        this.permissionState = 'DENIED';
        this.lastError = 'Microphone permission denied. Please allow microphone access in browser settings.';
        this.setState('ERROR');
        this.notifyError(this.lastError);
        return;
      }
    }

    this.resetEndpointingState();
    this.lastSubmittedCommand = '';
    this.lastSubmittedTime = 0;
    this.isEnabled = true;
    this.isPaused = false;
    this.retryCount = 0;
    this.wakeResultIndex = -1;
    this.setState('LISTENING_FOR_WAKE_WORD');
    this.restartRecognition();
  }

  public stop() {
    console.log(`[WakeDebug] stop() called on instance ${this.instanceId}`);
    this.resetEndpointingState();
    this.isEnabled = false;
    this.isPaused = false;
    this.wakeResultIndex = -1;
    this.recognitionRunning = false;
    this.startingRecognition = false;
    this.clearCommandTimeout();
    this.clearContinuousTimeout();
    this.clearRestartTimer();

    if (this.recognition) {
      try {
        this.recognition.abort();
      } catch (e) {
        // Ignore
      }
    }
    this.setState('DISABLED');
  }

  public pause() {
    console.log(`[WakeDebug] pause() called on instance ${this.instanceId}`);
    this.resetEndpointingState();
    this.isPaused = true;
    this.recognitionRunning = false;
    this.startingRecognition = false;
    this.clearCommandTimeout();
    this.clearContinuousTimeout();
    this.clearRestartTimer();

    if (this.recognition) {
      try {
        this.recognition.abort();
      } catch (e) {
        // Ignore
      }
    }
    if (this.state !== 'DISABLED') {
      this.setState('IDLE');
    }
  }

  public resume() {
    console.log(`[WakeDebug] resume() called on instance ${this.instanceId}`);
    if (!this.isEnabled) return;
    this.resetEndpointingState();
    this.isPaused = false;
    this.retryCount = 0;
    this.wakeResultIndex = -1;
    this.setState('LISTENING_FOR_WAKE_WORD');
    this.scheduleRestart(200);
  }

  // Subscriptions
  public onStateChange(callback: WakeWordStateCallback): () => void {
    this.stateCallbacks.add(callback);
    return () => this.stateCallbacks.delete(callback);
  }

  public onWakeWord(callback: WakeWordEventCallback): () => void {
    this.wakeWordCallbacks.add(callback);
    return () => this.wakeWordCallbacks.delete(callback);
  }

  public onCommandCaptured(callback: WakeWordEventCallback): () => void {
    this.commandCallbacks.add(callback);
    return () => this.commandCallbacks.delete(callback);
  }

  public onError(callback: WakeWordErrorCallback): () => void {
    this.errorCallbacks.add(callback);
    return () => this.errorCallbacks.delete(callback);
  }

  private notifyState() {
    this.stateCallbacks.forEach((fn) => fn(this.state));
  }

  private notifyWakeWord(commandText: string) {
    this.wakeWordCallbacks.forEach((fn) => fn(commandText));
  }

  private notifyCommand(commandText: string) {
    this.commandCallbacks.forEach((fn) => fn(commandText));
  }

  private notifyError(error: string) {
    this.errorCallbacks.forEach((fn) => fn(error));
  }

  // Diagnostic helper for raw mic test (Step 2)
  public async runRawMicTest(onLog: (m: string) => void) {
    console.log('[WakeDebug] RAW_MIC_TEST requested');
    if (!this.isSupported()) {
      onLog('RAW_MIC_ERROR: Unsupported browser');
      return;
    }
    try {
      if (typeof navigator !== 'undefined' && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        stream.getTracks().forEach((track) => track.stop());
      }
      const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      const rec = new SR();
      rec.continuous = false;
      rec.interimResults = true;
      rec.lang = 'en-US';

      rec.onstart = () => {
        console.log('[WakeDebug] RAW_MIC_START');
        onLog('RAW_MIC_START');
      };
      rec.onresult = (event: any) => {
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const tr = event.results[i][0].transcript;
          const fin = event.results[i].isFinal;
          console.log('[WakeDebug] RAW_MIC_RESULT', tr, fin);
          onLog(`RAW_MIC_RESULT: "${tr}" (isFinal: ${fin})`);
        }
      };
      rec.onerror = (event: any) => {
        console.log('[WakeDebug] RAW_MIC_ERROR: ' + event.error);
        onLog(`RAW_MIC_ERROR: ${event.error}`);
      };
      rec.onend = () => {
        console.log('[WakeDebug] RAW_MIC_END');
        onLog('RAW_MIC_END');
      };
      rec.start();
    } catch (e: any) {
      onLog(`RAW_MIC_EXCEPTION: ${e.message}`);
    }
  }

  // Diagnostic helper to test microphone audio capture in browser UI
  public async testMicrophoneAudio(onTranscript: (t: string) => void, onErrorMsg: (e: string) => void) {
    console.log('[WakeDebug] Running testMicrophoneAudio...');
    if (!this.isSupported()) {
      onErrorMsg('SpeechRecognition is unsupported in this browser.');
      return;
    }
    try {
      if (typeof navigator !== 'undefined' && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        stream.getTracks().forEach((track) => track.stop());
      }
      const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      const testRec = new SR();
      testRec.continuous = false;
      testRec.interimResults = false;
      testRec.onstart = () => console.log('[WakeDebug] Diagnostic Mic Test listening...');
      testRec.onresult = (evt: any) => {
        const tr = evt.results[0][0].transcript;
        console.log('[WakeDebug] Diagnostic Mic Test heard:', tr);
        onTranscript(tr);
      };
      testRec.onerror = (evt: any) => {
        console.warn('[WakeDebug] Diagnostic Mic Test error:', evt.error);
        onErrorMsg(`Mic test error: ${evt.error}`);
      };
      testRec.start();
    } catch (e: any) {
      onErrorMsg(`Mic test exception: ${e.message}`);
    }
  }

  // Method to manually trigger wake word (used by unit tests)
  public triggerWakeWord(transcript: string = 'Hey ByteX') {
    const { isMatch, commandText } = matchWakeWord(transcript);
    if (isMatch) {
      this.setState('WAKE_DETECTED');
      this.notifyWakeWord(commandText);
      if (commandText) {
        this.handleCommandCaptured(commandText);
      } else {
        this.setState('LISTENING_FOR_COMMAND');
        this.startCommandTimeout();
      }
    }
  }
}

export const wakeWordService = new WakeWordService();
if (typeof window !== 'undefined') {
  (window as any).wakeWordService = wakeWordService;
}
export default wakeWordService;
