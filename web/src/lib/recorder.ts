/** Recording an answer as the audio the local pipeline actually wants.
 *
 *  whisper.cpp and Silero both want 16 kHz mono 16-bit PCM. Producing exactly
 *  that here means the backend needs no ffmpeg and no transcoding step, and the
 *  bytes that arrive are the bytes that get measured.
 *
 *  The route is MediaRecorder -> decodeAudioData -> OfflineAudioContext -> WAV.
 *  Every step is a stable API; the older ScriptProcessorNode path would give raw
 *  PCM without the intermediate encode, but it is deprecated and this is not the
 *  place to depend on something browsers are removing.
 */

/** Browser noise suppression is designed to delete exactly what we measure.
 *  A filled pause is low-energy voiced sound with no linguistic content, which
 *  is precisely what a noise gate is built to remove — leave it on and the
 *  "um" is gone before the detector ever sees it. */
export const CAPTURE_CONSTRAINTS: MediaTrackConstraints = {
  channelCount: 1,
  echoCancellation: true,
  noiseSuppression: false,
  autoGainControl: false,
};

const TARGET_RATE = 16000;

export interface Recording {
  wav: Blob;
  durationSec: number;
}

function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const ascii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
  };

  ascii(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  ascii(36, "data");
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, clamped * 32767, true);
    offset += 2;
  }
  return new Blob([buffer], { type: "audio/wav" });
}

export class AnswerRecorder {
  private recorder: MediaRecorder;
  private stream: MediaStream;
  private chunks: Blob[] = [];

  private constructor(stream: MediaStream, recorder: MediaRecorder) {
    this.stream = stream;
    this.recorder = recorder;
    this.recorder.ondataavailable = (e) => {
      if (e.data.size > 0) this.chunks.push(e.data);
    };
  }

  static async start(): Promise<AnswerRecorder> {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: CAPTURE_CONSTRAINTS });
    const recorder = new MediaRecorder(stream);
    const self = new AnswerRecorder(stream, recorder);
    recorder.start();
    return self;
  }

  /** Stop, release the microphone, and return 16 kHz mono WAV. */
  async stop(): Promise<Recording> {
    const finished = new Promise<void>((resolve) => {
      this.recorder.onstop = () => resolve();
    });
    this.recorder.stop();
    await finished;
    // Release the mic promptly: a tab holding it shows a recording indicator,
    // which is alarming when the answer is already over.
    this.stream.getTracks().forEach((t) => t.stop());

    const encoded = await new Blob(this.chunks, { type: this.recorder.mimeType }).arrayBuffer();
    const decodeCtx = new AudioContext();
    let decoded: AudioBuffer;
    try {
      decoded = await decodeCtx.decodeAudioData(encoded);
    } finally {
      void decodeCtx.close();
    }

    // The browser resamples properly here. Decimating by hand would alias, and
    // aliasing in the 3–4 kHz band is exactly where the detector is listening.
    const frames = Math.max(1, Math.round((decoded.duration * TARGET_RATE)));
    const offline = new OfflineAudioContext(1, frames, TARGET_RATE);
    const source = offline.createBufferSource();
    source.buffer = decoded;
    source.connect(offline.destination);
    source.start();
    const resampled = await offline.startRendering();

    return {
      wav: encodeWav(resampled.getChannelData(0), TARGET_RATE),
      durationSec: decoded.duration,
    };
  }

  /** Abandon the recording without producing anything. */
  cancel() {
    try {
      if (this.recorder.state !== "inactive") this.recorder.stop();
    } catch {
      /* already stopped */
    }
    this.stream.getTracks().forEach((t) => t.stop());
  }
}

export function canRecord(): boolean {
  return (
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== "undefined" &&
    typeof OfflineAudioContext !== "undefined"
  );
}
