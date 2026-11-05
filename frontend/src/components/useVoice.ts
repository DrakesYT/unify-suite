import { useCallback, useEffect, useRef, useState } from "react";

/** The parts of the browser's Web Speech API we use (not in TypeScript's DOM types yet). */
interface SpeechResult {
  readonly isFinal: boolean;
  readonly 0: { transcript: string };
}
interface SpeechEvent {
  readonly results: ArrayLike<SpeechResult>;
}
interface Recognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: SpeechEvent) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type RecognitionCtor = new () => Recognition;

function recognitionClass(): RecognitionCtor | null {
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor;
    webkitSpeechRecognition?: RecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const ERRORS: Record<string, string> = {
  "not-allowed": "Microphone access is blocked for this site.",
  "service-not-allowed": "Microphone access is blocked for this site.",
  "no-speech": "Didn't catch that. Try again.",
  "audio-capture": "No microphone found.",
  network: "Speech recognition needs an internet connection.",
};

/** Dictation with the browser's own speech recognition. `onText` gets the words so far. */
export function useVoice(onText: (text: string) => void) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recognition = useRef<Recognition | null>(null);
  const supported = recognitionClass() !== null;

  useEffect(() => () => recognition.current?.abort(), []);

  const toggle = useCallback(() => {
    if (recognition.current) {
      recognition.current.stop();
      return;
    }
    const Ctor = recognitionClass();
    if (!Ctor) return;
    const r = new Ctor();
    r.lang = navigator.language || "en-US";
    r.interimResults = true;
    r.continuous = false;
    r.onresult = (e) => {
      onText(
        Array.from(e.results)
          .map((res) => res[0].transcript)
          .join("")
          .trim(),
      );
    };
    r.onerror = (e) => {
      if (e.error !== "aborted") setError(ERRORS[e.error] ?? "Voice input stopped.");
    };
    r.onend = () => {
      recognition.current = null;
      setListening(false);
    };
    recognition.current = r;
    setError(null);
    setListening(true);
    r.start();
  }, [onText]);

  return { supported, listening, error, toggle };
}
