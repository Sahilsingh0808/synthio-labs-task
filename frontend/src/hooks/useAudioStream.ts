import { useCallback, useEffect, useRef } from "react";

const SAMPLE_RATE = 24_000;
const BUFFER_SIZE = 4_096;

export interface AudioStreamHandle {
  startRecording: () => Promise<void>;
  stopRecording: () => void;
  playChunk: (base64: string) => void;
  stopPlayback: () => void;
  getAnalyser: () => AnalyserNode | null;
  cleanup: () => void;
}

export function useAudioStream(
  onAudioChunk: (buffer: ArrayBuffer) => void,
): AudioStreamHandle {
  const chunkHandlerRef = useRef(onAudioChunk);
  chunkHandlerRef.current = onAudioChunk;

  const ctxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const nextPlayTimeRef = useRef(0);
  const activeSourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set());

  const ensureContext = useCallback(() => {
    if (!ctxRef.current) {
      ctxRef.current = new AudioContext({ sampleRate: SAMPLE_RATE });
    }
    return ctxRef.current;
  }, []);

  const startRecording = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: SAMPLE_RATE,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    streamRef.current = stream;

    const ctx = ensureContext();
    if (ctx.state === "suspended") await ctx.resume();

    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    analyserRef.current = analyser;

    const processor = ctx.createScriptProcessor(BUFFER_SIZE, 1, 1);
    processorRef.current = processor;

    processor.onaudioprocess = (event: AudioProcessingEvent) => {
      const float32 = event.inputBuffer.getChannelData(0);
      const int16 = new Int16Array(float32.length);
      for (let i = 0; i < float32.length; i++) {
        const clamped = Math.max(-1, Math.min(1, float32[i]));
        int16[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
      }
      chunkHandlerRef.current(int16.buffer);
    };

    const source = ctx.createMediaStreamSource(stream);
    sourceRef.current = source;
    source.connect(analyser);
    analyser.connect(processor);
    processor.connect(ctx.destination);
  }, [ensureContext]);

  const stopRecording = useCallback(() => {
    processorRef.current?.disconnect();
    analyserRef.current?.disconnect();
    sourceRef.current?.disconnect();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    processorRef.current = null;
    sourceRef.current = null;
    streamRef.current = null;
  }, []);

  const playChunk = useCallback((base64: string) => {
    const ctx = ensureContext();
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const int16 = new Int16Array(bytes.buffer);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32_768;

    const buffer = ctx.createBuffer(1, float32.length, SAMPLE_RATE);
    buffer.copyToChannel(float32, 0);

    const startAt = Math.max(ctx.currentTime, nextPlayTimeRef.current);
    nextPlayTimeRef.current = startAt + buffer.duration;

    const node = ctx.createBufferSource();
    node.buffer = buffer;
    node.connect(ctx.destination);
    node.onended = () => {
      activeSourcesRef.current.delete(node);
    };
    activeSourcesRef.current.add(node);
    node.start(startAt);
  }, [ensureContext]);

  const stopPlayback = useCallback(() => {
    activeSourcesRef.current.forEach((node) => {
      try {
        node.stop();
      } catch {
        // already stopped
      }
    });
    activeSourcesRef.current.clear();
    nextPlayTimeRef.current = 0;
  }, []);

  const getAnalyser = useCallback(() => analyserRef.current, []);

  const cleanup = useCallback(() => {
    stopPlayback();
    stopRecording();
    const ctx = ctxRef.current;
    ctxRef.current = null;
    analyserRef.current = null;
    nextPlayTimeRef.current = 0;
    void ctx?.close().catch(() => {});
  }, [stopPlayback, stopRecording]);

  useEffect(() => {
    return () => {
      cleanup();
    };
  }, [cleanup]);

  return { startRecording, stopRecording, playChunk, stopPlayback, getAnalyser, cleanup };
}
