"""Transcription via faster-whisper — accurate offline speech-to-text.

Outputs natural text WITH punctuation and capitalization (unlike the old Vosk
small model). Handles long, multi-sentence dictation in a single pass.

The model is loaded once and cached. On first use faster-whisper downloads the
model into the standard Hugging Face cache (~/.cache/huggingface) and reuses it
forever after — so the exe stays small and only the first run needs internet.
"""
import io
import threading
import time
import traceback
import wave
from collections.abc import Callable

import numpy as np

try:
    # main.py installs the logger + adds ~/.claude/scripts to sys.path first.
    from crash_logger import log_event
except Exception:  # pragma: no cover
    def log_event(*_args, **_kwargs):
        pass


# ── Tuning knobs (safe to tweak) ─────────────────────────────────────
#   WHISPER_MODEL  : "tiny" < "base" < "small" < "medium" < "large-v3"
#                    (bigger = more accurate, slower, more RAM)
#   COMPUTE_TYPE   : "int8" is fast + light on CPU; "float32" is slower/heavier
#   BEAM_SIZE      : higher = more accurate, slower (1 = greedy/fastest)
WHISPER_MODEL = "small"
COMPUTE_TYPE = "int8"
BEAM_SIZE = 5
SAMPLE_RATE = 16000


class Transcriber:
    """Loads a faster-whisper model once, then transcribes WAV bytes on demand."""

    def __init__(self):
        self._model = None
        self._lock = threading.Lock()
        self._loaded = False

    # ------------------------------------------------------------------
    def ensure_loaded(self) -> None:
        """Load the model if not already loaded (blocks; downloads on first run)."""
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            from faster_whisper import WhisperModel

            print(f"[Transcriber] Loading Whisper model '{WHISPER_MODEL}'...")
            t0 = time.perf_counter()
            try:
                self._model = WhisperModel(
                    WHISPER_MODEL, device="cpu", compute_type=COMPUTE_TYPE
                )
            except Exception as exc:
                log_event("boundary", "whisper model load",
                          {"model": WHISPER_MODEL, "ok": False, "error": str(exc)})
                raise
            log_event("boundary", "whisper model load",
                      {"model": WHISPER_MODEL, "ok": True,
                       "ms": round((time.perf_counter() - t0) * 1000)})
            self._loaded = True
            print("[Transcriber] Model ready.")

    # ------------------------------------------------------------------
    @staticmethod
    def _wav_to_float32(wav_bytes: bytes) -> np.ndarray:
        """Decode 16-bit mono PCM WAV bytes to a float32 array in [-1, 1]."""
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            width, channels = wf.getsampwidth(), wf.getnchannels()
            frames = wf.readframes(wf.getnframes())
        # AudioCapture always produces 16-bit mono. Guard so a future change
        # doesn't silently feed Whisper byte-misaligned garbage.
        if width != 2 or channels != 1:
            raise ValueError(f"expected 16-bit mono WAV, got {width * 8}-bit {channels}ch")
        if not frames:
            return np.zeros(0, dtype=np.float32)
        return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

    def transcribe(self, wav_bytes: bytes) -> str:
        """Transcribe WAV bytes → punctuated text."""
        self.ensure_loaded()
        audio = self._wav_to_float32(wav_bytes)
        if audio.size == 0:
            return ""

        t0 = time.perf_counter()
        segments, _info = self._model.transcribe(
            audio,
            language="en",
            beam_size=BEAM_SIZE,
            vad_filter=True,                 # skip silent gaps (no hallucinations)
            condition_on_previous_text=False,  # prevents repetition loops on long audio
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        log_event("perf", "whisper transcribe",
                  {"audio_s": round(audio.size / SAMPLE_RATE, 1),
                   "ms": round((time.perf_counter() - t0) * 1000),
                   "chars": len(text)})
        return text

    def transcribe_async(
        self,
        wav_bytes: bytes,
        on_done: Callable[[str], None],
        on_error: Callable[[Exception], None] | None = None,
    ):
        def _run():
            try:
                on_done(self.transcribe(wav_bytes))
            except Exception as exc:
                log_event("failure", "transcription thread error",
                          {"error": str(exc), "tb": traceback.format_exc()})
                if on_error:
                    on_error(exc)

        threading.Thread(target=_run, daemon=True).start()
