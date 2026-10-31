/**
 * ByteX Core — Acoustic Voice Barge-In Service (Function 566)
 *
 * Enables true hands-free acoustic voice barge-in during assistant speech synthesis.
 * Uses client-side Web Audio API (AudioContext + AnalyserNode) with hardware echo cancellation
 * to detect sustained speech activity during playback and instantly stop TTS output.
 *
 * Budget: Strictly ₹0 (Built on native browser Web Audio API & MediaStream constraints).
 */

export interface BargeInConfig {
  energyThreshold?: number; // RMS amplitude threshold for speech detection (default: 0.045)
  persistenceMs?: number; // Required sustained duration above threshold (default: 120ms)
  gracePeriodMs?: number; // Blanking window at start of playback to ignore speaker pops (default: 250ms)
  cooldownMs?: number; // Debounce window after an interruption (default: 800ms)
  sampleIntervalMs?: number; // Sampling interval for time-domain analysis (default: 25ms)
  enabled?: boolean; // Master toggle
}

export interface InterruptionEvent {
  amplitude: number;
  duration: number;
  timestamp: number;
}

export type BargeInCallback = (event: InterruptionEvent) => void;

export class BargeInService {
  private isMonitoring: boolean = false;
  private audioContext: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private micStream: MediaStream | null = null;
  private dataArray: Uint8Array | null = null;
  private timerId: any = null;

  // Configuration with tuned defaults
  private config: Required<BargeInConfig> = {
    energyThreshold: 0.045,
    persistenceMs: 120,
    gracePeriodMs: 250,
    cooldownMs: 800,
    sampleIntervalMs: 25,
    enabled: true,
  };

  // State tracking
  private monitoringStartTime: number = 0;
  private speechStartTimestamp: number = 0;
  private lastInterruptionTime: number = 0;
  private currentAmplitude: number = 0;
  private baselineNoiseFloor: number = 0.02;

  private interruptionCallbacks: Set<BargeInCallback> = new Set();

  constructor() {
    if (typeof window !== 'undefined') {
      (window as any).bargeInService = this;
    }
  }

  public isSupported(): boolean {
    return (
      typeof window !== 'undefined' &&
      (typeof window.AudioContext !== 'undefined' || typeof (window as any).webkitAudioContext !== 'undefined') &&
      typeof navigator !== 'undefined' &&
      !!navigator.mediaDevices?.getUserMedia
    );
  }

  public setConfig(newConfig: Partial<BargeInConfig>) {
    if (newConfig.energyThreshold !== undefined) {
      const val = Number(newConfig.energyThreshold);
      this.config.energyThreshold = Math.max(0.015, Math.min(0.5, Number.isFinite(val) ? val : 0.045));
    }
    if (newConfig.persistenceMs !== undefined) {
      const val = Number(newConfig.persistenceMs);
      this.config.persistenceMs = Math.max(50, Math.min(2000, Number.isFinite(val) ? val : 120));
    }
    if (newConfig.gracePeriodMs !== undefined) {
      const val = Number(newConfig.gracePeriodMs);
      this.config.gracePeriodMs = Math.max(0, Math.min(1000, Number.isFinite(val) ? val : 250));
    }
    if (newConfig.cooldownMs !== undefined) {
      const val = Number(newConfig.cooldownMs);
      this.config.cooldownMs = Math.max(100, Math.min(5000, Number.isFinite(val) ? val : 800));
    }
    if (newConfig.sampleIntervalMs !== undefined) {
      const val = Number(newConfig.sampleIntervalMs);
      this.config.sampleIntervalMs = Math.max(10, Math.min(200, Number.isFinite(val) ? val : 25));
    }
    if (newConfig.enabled !== undefined) {
      this.config.enabled = !!newConfig.enabled;
    }
  }

  public getConfig(): Required<BargeInConfig> {
    return { ...this.config };
  }

  public setThreshold(threshold: number) {
    this.setConfig({ energyThreshold: threshold });
  }

  public getThreshold(): number {
    return this.config.energyThreshold;
  }

  public getIsMonitoring(): boolean {
    return this.isMonitoring;
  }

  public getCurrentAmplitude(): number {
    return this.currentAmplitude;
  }

  public getBaselineNoiseFloor(): number {
    return this.baselineNoiseFloor;
  }

  public onInterruption(callback: BargeInCallback): () => void {
    this.interruptionCallbacks.add(callback);
    return () => this.interruptionCallbacks.delete(callback);
  }

  private notifyInterruption(event: InterruptionEvent) {
    this.interruptionCallbacks.forEach((cb) => {
      try {
        cb(event);
      } catch (err) {
        console.error('[BargeIn] Error in interruption callback:', err);
      }
    });
  }

  /**
   * Starts real-time acoustic monitoring of the microphone during TTS playback.
   * Acquires a stream with echo cancellation and noise suppression constraints.
   */
  public async startMonitoring(): Promise<boolean> {
    if (!this.config.enabled || !this.isSupported()) {
      return false;
    }

    // Cooldown check: prevent immediate re-trigger loop
    const now = Date.now();
    if (now - this.lastInterruptionTime < this.config.cooldownMs) {
      console.log(`[BargeIn] Monitoring start deferred: cooldown active (${now - this.lastInterruptionTime}ms < ${this.config.cooldownMs}ms)`);
      return false;
    }

    if (this.isMonitoring) {
      return true;
    }

    try {
      this.monitoringStartTime = now;
      this.speechStartTimestamp = 0;
      this.currentAmplitude = 0;

      // 1. Request microphone stream with hardware AEC and noise suppression constraints
      if (!this.micStream && navigator.mediaDevices?.getUserMedia) {
        this.micStream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
      }

      // 2. Initialize Web Audio API pipeline
      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
      if (!this.audioContext || this.audioContext.state === 'closed') {
        this.audioContext = new AudioContextClass();
      }

      if (this.audioContext.state === 'suspended') {
        await this.audioContext.resume().catch(() => {});
      }

      if (this.micStream && this.audioContext) {
        const source = this.audioContext.createMediaStreamSource(this.micStream);
        this.analyser = this.audioContext.createAnalyser();
        this.analyser.fftSize = 256;
        this.analyser.smoothingTimeConstant = 0.3;
        source.connect(this.analyser);
        this.dataArray = new Uint8Array(this.analyser.frequencyBinCount);
      }

      this.isMonitoring = true;
      console.log('[BargeIn] Acoustic barge-in monitoring active during assistant speech.');

      // 3. Start high-frequency time-domain amplitude polling loop
      this.startPollingLoop();
      return true;
    } catch (e: any) {
      console.warn('[BargeIn] Failed to start acoustic monitoring (permission or audioContext error):', e);
      this.stopMonitoring();
      return false;
    }
  }

  private startPollingLoop() {
    if (this.timerId) {
      clearInterval(this.timerId);
    }

    this.timerId = setInterval(() => {
      this.processAudioFrame();
    }, this.config.sampleIntervalMs);
  }

  /**
   * Processes a single time-domain audio frame to calculate RMS energy and detect sustained speech.
   */
  public processAudioFrame() {
    if (!this.isMonitoring || !this.analyser || !this.dataArray) {
      return;
    }

    const now = Date.now();

    // 1. Grace blanking period at start of playback (ignores initial driver pops or speaker clicks)
    if (now - this.monitoringStartTime < this.config.gracePeriodMs) {
      return;
    }

    // 2. Extract byte time domain data (values centered at 128)
    (this.analyser as any).getByteTimeDomainData(this.dataArray);

    let sumSquares = 0;
    const len = this.dataArray.length;
    for (let i = 0; i < len; i++) {
      const normalized = (this.dataArray[i] - 128) / 128; // -1.0 to 1.0
      sumSquares += normalized * normalized;
    }

    const rawRms = Math.sqrt(sumSquares / len);
    this.currentAmplitude = rawRms;

    // 3. Compute dynamic effective threshold (ensures threshold is always above background noise floor)
    const effectiveThreshold = Math.max(this.config.energyThreshold, this.baselineNoiseFloor * 2.2);

    // 4. Persistence check: must exceed threshold for sustained window (default: 120ms)
    if (rawRms >= effectiveThreshold) {
      if (this.speechStartTimestamp === 0) {
        this.speechStartTimestamp = now;
        console.log(`[BargeIn] Acoustic onset detected: RMS=${rawRms.toFixed(3)} >= threshold=${effectiveThreshold.toFixed(3)}`);
      } else {
        const sustainedDuration = now - this.speechStartTimestamp;
        if (sustainedDuration >= this.config.persistenceMs) {
          // Genuine speech-like interruption confirmed!
          console.log(
            `[BargeIn] Acoustic interruption confirmed! (RMS: ${rawRms.toFixed(3)} >= ${effectiveThreshold.toFixed(3)}, duration: ${sustainedDuration}ms)`
          );
          this.lastInterruptionTime = now;
          const event: InterruptionEvent = {
            amplitude: rawRms,
            duration: sustainedDuration,
            timestamp: now,
          };
          this.stopMonitoring();
          this.notifyInterruption(event);
        }
      }
    } else {
      // Below threshold: reset speech timestamp and update noise floor estimate (bounded to max 0.20)
      this.speechStartTimestamp = 0;
      this.baselineNoiseFloor = Math.min(0.20, this.baselineNoiseFloor * 0.95 + rawRms * 0.05);
    }
  }

  /**
   * Stops real-time acoustic monitoring and releases all audio hardware resources cleanly.
   */
  public stopMonitoring() {
    this.isMonitoring = false;
    this.speechStartTimestamp = 0;
    this.currentAmplitude = 0;

    if (this.timerId) {
      clearInterval(this.timerId);
      this.timerId = null;
    }

    if (this.micStream) {
      this.micStream.getTracks().forEach((track) => {
        try {
          track.stop();
        } catch (e) {}
      });
      this.micStream = null;
    }

    if (this.audioContext && this.audioContext.state !== 'closed') {
      try {
        this.audioContext.close().catch(() => {});
      } catch (e) {}
      this.audioContext = null;
    }

    this.analyser = null;
    this.dataArray = null;
  }

  /**
   * Full cleanup of listeners, tracks, and timers upon unmount.
   */
  public dispose() {
    this.stopMonitoring();
    this.interruptionCallbacks.clear();
  }

  public getDiagnosticData() {
    return {
      isMonitoring: this.isMonitoring,
      currentAmplitude: this.currentAmplitude,
      baselineNoiseFloor: this.baselineNoiseFloor,
      effectiveThreshold: Math.max(this.config.energyThreshold, this.baselineNoiseFloor * 2.2),
      config: this.config,
      lastInterruptionTime: this.lastInterruptionTime,
      hasStream: !!this.micStream,
      hasAudioContext: !!this.audioContext,
    };
  }
}

export const bargeInService = new BargeInService();
export default bargeInService;
