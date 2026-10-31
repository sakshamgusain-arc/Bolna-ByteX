export type TTSStateCallback = (isSpeaking: boolean) => void;

export interface SpeakOptions {
  rate?: number;
  volume?: number;
  pitch?: number;
  language?: string;
  voiceURI?: string;
  speakOnlyHighlights?: boolean;
}

interface QueuedSpeechSegment {
  id: string;
  text: string;
  options: SpeakOptions;
}

class TTSService {
  private isSpeakingState: boolean = false;
  private stateCallbacks: Set<TTSStateCallback> = new Set();

  // Single ordered FIFO speech queue & stream buffer
  private speechQueue: QueuedSpeechSegment[] = [];
  private enqueuedSegmentHashes: Set<string> = new Set();
  private streamBuffer: string = '';
  private isPlayingSegment: boolean = false;
  private isStreamSuppressed: boolean = false;

  private speechStartTime: number = 0;
  private currentAmplitude: number = 0;
  private boundaryBurst: number = 0;
  private currentVolumeLevel: number = 1.0;

  public isSupported(): boolean {
    return 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;
  }

  public getAvailableVoices(): SpeechSynthesisVoice[] {
    if (!this.isSupported()) return [];
    return window.speechSynthesis.getVoices();
  }

  /**
   * Intelligently finds the highest quality natural/neural voice available on the OS/Browser.
   */
  public getBestVoice(targetLang: string = 'en-US'): SpeechSynthesisVoice | null {
    const voices = this.getAvailableVoices();
    if (!voices.length) return null;

    const priorityKeywords = ['natural', 'neural', 'online', 'google', 'aria', 'guy', 'jenny', 'ana', 'zira'];
    
    for (const kw of priorityKeywords) {
      const match = voices.find((v) => 
        v.lang?.toLowerCase().startsWith(targetLang.slice(0, 2).toLowerCase()) &&
        ((v.name && v.name.toLowerCase().includes(kw)) || (v.voiceURI && v.voiceURI.toLowerCase().includes(kw)))
      );
      if (match) return match;
    }

    const langMatch = voices.find((v) => v.lang.toLowerCase() === targetLang.toLowerCase());
    if (langMatch) return langMatch;

    const enMatch = voices.find((v) => v.lang.toLowerCase().startsWith('en'));
    if (enMatch) return enMatch;

    return voices[0] || null;
  }

  /**
   * Cleans text for speech output, stripping code blocks, URLs, and formatting.
   */
  public sanitizeSpeechSegment(raw: string): string {
    if (!raw || !raw.trim()) return '';

    let text = raw.trim();

    // 1. Strip internal reasoning or protocol tags before speech
    text = text
      .replace(/<think>[\s\S]*?<\/think>/gi, '')
      .replace(/<tool_call>[\s\S]*?<\/tool_call>/gi, '')
      .replace(/<tool>[\s\S]*?<\/tool>/gi, '')
      .replace(/<\/?think>/gi, '')
      .replace(/<\/?tool_call>/gi, '')
      .replace(/<\/?tool>/gi, '')
      .replace(/\{"thought"[\s\S]*?\}/gi, '')
      .trim();

    // 2. Replace multi-line code blocks with brief spoken notification
    text = text.replace(/```[a-zA-Z0-9_\+\#]*\s*[\s\S]*?```/gi, "I've generated the code and displayed it on screen.");
    text = text.replace(/`[^`]+`/g, 'code snippet');

    // 3. Strip URLs
    text = text.replace(/https?:\/\/\S+/g, 'link');

    // 4. Strip markdown formatting (*, _, ~, #, [, ], (, ), >, etc.)
    text = text.replace(/[*_~`#\[\]()>]/g, '');

    // 5. Clean up excessive whitespace
    text = text.replace(/\s+/g, ' ').trim();

    return text;
  }

  /**
   * Extracts ONLY the concise highlighted bullet points & key summary sentences for speech output.
   */
  public extractHighlightedSummary(text: string): string {
    if (!text || !text.trim()) return '';

    const cleanSanitized = this.sanitizeSpeechSegment(text);
    if (!cleanSanitized) return '';

    const lines = cleanSanitized.split('\n').map((l) => l.trim()).filter(Boolean);
    
    // 1. Extract top bullet points or numbered highlights if present
    const bulletLines = lines.filter((l) => /^[•*\-\d+\.]\s+/.test(l));
    if (bulletLines.length > 0) {
      const keyHighlights = bulletLines.slice(0, 3).map((l) => 
        l.replace(/^[•*\-\d+\.]\s+/, '').trim()
      );
      const summary = keyHighlights.join('. ');
      return summary.length > 500 ? summary.slice(0, 497) + '...' : summary;
    }

    // 2. Otherwise extract first 2 key sentences
    const sentences = cleanSanitized.split(/(?<=[.!?])\s+/).filter(Boolean);
    const summary = sentences.slice(0, 2).join(' ');
    return summary.length > 500 ? summary.slice(0, 497) + '...' : summary;
  }

  public onStateChange(callback: TTSStateCallback): () => void {
    this.stateCallbacks.add(callback);
    return () => this.stateCallbacks.delete(callback);
  }

  private notifyState(speaking: boolean) {
    this.isSpeakingState = speaking;
    if (speaking) {
      this.speechStartTime = performance.now();
      this.boundaryBurst = 0.6;
    } else {
      this.boundaryBurst = 0.0;
    }
    this.stateCallbacks.forEach((fn) => fn(speaking));
  }

  public isSpeaking(): boolean {
    return this.isSpeakingState || this.isPlayingSegment || (this.isSupported() && window.speechSynthesis.speaking);
  }

  public getQueueLength(): number {
    return this.speechQueue.length;
  }

  /**
   * Returns organic real-time vocal amplitude for the orb's speech breathing.
   * Quiet volume = gentle breathing, loud volume = expansive breathing.
   */
  public getAudioAmplitude(): number {
    if (!this.isSpeaking()) {
      this.currentAmplitude *= 0.85; // smooth release
      return Math.max(0, this.currentAmplitude);
    }

    const now = performance.now();
    const elapsed = (now - this.speechStartTime) / 1000;

    // Organic vocal formant modulation across harmonic frequencies
    const vocalWave = 
      Math.sin(elapsed * 12.0) * 0.35 + 
      Math.sin(elapsed * 22.0) * 0.22 + 
      Math.cos(elapsed * 6.5) * 0.25;

    const cadence = Math.max(0.12, Math.abs(vocalWave));

    if (this.boundaryBurst > 0) {
      this.boundaryBurst *= 0.88;
    }

    const rawTarget = (cadence + this.boundaryBurst * 0.45) * this.currentVolumeLevel;
    const target = Math.min(1.0, Math.max(0.08, rawTarget));

    // Attack / Release envelope smoothing
    const alpha = target > this.currentAmplitude ? 0.35 : 0.08;
    this.currentAmplitude += (target - this.currentAmplitude) * alpha;

    return this.currentAmplitude;
  }

  /**
   * Stops ongoing speech immediately and clears the ordered queue.
   * If suppressStream is true, incoming stream tokens for the current message are muted.
   */
  public stop(suppressStream: boolean = false) {
    this.speechQueue = [];
    this.enqueuedSegmentHashes.clear();
    this.streamBuffer = '';
    this.isPlayingSegment = false;
    this.isStreamSuppressed = suppressStream;

    if (this.isSupported()) {
      try {
        window.speechSynthesis.cancel();
      } catch (e) {
        console.warn('[ByteX TTS] Cancel error:', e);
      }
    }
    this.notifyState(false);
  }

  public resetStreamSuppression() {
    this.isStreamSuppressed = false;
  }

  public getIsStreamSuppressed(): boolean {
    return this.isStreamSuppressed;
  }

  /**
   * Enqueues an individual speakable segment into the single ordered FIFO speech queue.
   * Guarantees each segment is spoken once in strict sequential order.
   */
  public queueSegment(text: string, options: SpeakOptions = {}) {
    if (this.isStreamSuppressed) return;

    const cleanText = this.sanitizeSpeechSegment(text);
    if (!cleanText) return;

    // Duplicate segment prevention
    const hash = cleanText.toLowerCase();
    if (this.enqueuedSegmentHashes.has(hash)) {
      return;
    }
    this.enqueuedSegmentHashes.add(hash);

    const segmentId = `seg_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;
    this.speechQueue.push({ id: segmentId, text: cleanText, options });

    // If not currently playing a segment, begin playback immediately
    if (!this.isPlayingSegment) {
      this.playNextInQueue();
    }
  }

  /**
   * Progressively feeds incoming stream tokens, segmenting at natural sentence boundaries
   * and initiating speech playback before generation completes.
   */
  public feedStreamChunk(chunk: string, options: SpeakOptions = {}) {
    if (!this.isSupported() || !chunk || this.isStreamSuppressed) return;

    // Skip internal reasoning and protocol tags early
    if (chunk.includes('<think>') || chunk.includes('<tool_call>') || chunk.includes('<tool>')) {
      return;
    }

    this.streamBuffer += chunk;

    // Boundary regex: matches sentence ending with [.!?] followed by whitespace or newline
    const sentenceRegex = /^([\s\S]*?[.!?])(?:\s+|\n+)([\s\S]*)$/;
    let match = this.streamBuffer.match(sentenceRegex);

    while (match) {
      const sentence = match[1];
      this.streamBuffer = match[2];

      const cleanSentence = this.sanitizeSpeechSegment(sentence);
      if (cleanSentence) {
        this.queueSegment(cleanSentence, options);
      }

      match = this.streamBuffer.match(sentenceRegex);
    }

    // Long-clause segmentation: if buffer exceeds 120 chars without full stop, split on comma/semicolon/newline
    if (this.streamBuffer.length > 120) {
      const clauseMatch = this.streamBuffer.match(/^([\s\S]*?([,;:]|\n\n))\s+([\s\S]*)$/);
      if (clauseMatch && clauseMatch[1].trim().length > 30) {
        const clause = clauseMatch[1];
        this.streamBuffer = clauseMatch[3];
        const cleanClause = this.sanitizeSpeechSegment(clause);
        if (cleanClause) {
          this.queueSegment(cleanClause, options);
        }
      }
    }
  }

  /**
   * Flushes any remaining buffered text when stream completion (ASSISTANT_COMPLETE) arrives.
   */
  public flushStream(options: SpeakOptions = {}) {
    if (this.isStreamSuppressed) {
      this.streamBuffer = '';
      return;
    }

    if (this.streamBuffer && this.streamBuffer.trim()) {
      const remaining = this.sanitizeSpeechSegment(this.streamBuffer);
      this.streamBuffer = '';
      if (remaining) {
        this.queueSegment(remaining, options);
      }
    }
  }

  /**
   * Plays the next segment in the ordered FIFO queue.
   */
  private playNextInQueue() {
    if (!this.isSupported()) return;

    if (this.speechQueue.length === 0) {
      this.isPlayingSegment = false;
      this.notifyState(false);
      return;
    }

    this.isPlayingSegment = true;
    const current = this.speechQueue.shift()!;

    try {
      const utterance = new SpeechSynthesisUtterance(current.text);
      const vol = current.options.volume ?? 1.0;
      utterance.rate = current.options.rate ?? 1.0;
      utterance.volume = vol;
      this.currentVolumeLevel = Math.max(0.4, Math.min(1.6, vol));
      utterance.pitch = current.options.pitch ?? 1.0;

      const targetLang =
        current.options.language === 'auto'
          ? 'en-US'
          : current.options.language === 'hi-IN-hinglish'
          ? 'hi-IN'
          : current.options.language || 'en-US';
      utterance.lang = targetLang;

      const voices = this.getAvailableVoices();
      let selectedVoice: SpeechSynthesisVoice | null = null;
      if (current.options.voiceURI) {
        selectedVoice = voices.find((v) => v.voiceURI === current.options.voiceURI) || null;
      }
      if (!selectedVoice) {
        selectedVoice = this.getBestVoice(targetLang);
      }
      if (selectedVoice) {
        utterance.voice = selectedVoice;
      }

      utterance.onstart = () => {
        this.notifyState(true);
      };

      utterance.onboundary = () => {
        this.boundaryBurst = 0.75;
      };

      utterance.onend = () => {
        this.isPlayingSegment = false;
        this.playNextInQueue();
      };

      utterance.onerror = (e) => {
        console.warn('[ByteX TTS] Segment playback error:', e);
        this.isPlayingSegment = false;
        // Automatically advance queue on error to avoid stalling
        this.playNextInQueue();
      };

      window.speechSynthesis.speak(utterance);
    } catch (e) {
      console.warn('[ByteX TTS] Playback exception:', e);
      this.isPlayingSegment = false;
      this.playNextInQueue();
    }
  }

  /**
   * Speaks a complete response (non-streaming or highlighted summary).
   * Stops previous audio, sanitizes text, and queues for playback.
   */
  public speak(text: string, options: SpeakOptions = {}) {
    if (!this.isSupported() || !text || !text.trim()) {
      return;
    }

    // Stop ongoing speech and clear queue
    this.stop();

    const spokenText =
      options.speakOnlyHighlights !== false
        ? this.extractHighlightedSummary(text)
        : this.sanitizeSpeechSegment(text);

    if (!spokenText) return;

    this.queueSegment(spokenText, options);
  }
}

export const ttsService = new TTSService();
export default ttsService;
