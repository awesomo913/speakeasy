"""Audio recorder with energy-based silence detection.

Uses sounddevice (bundled PortAudio) — zero C compilation needed.
"""
import io
import threading
import time
import wave
from collections.abc import Callable

import numpy as np
import sounddevice as sd

from speakeasy_log import log_event


class AudioCapture:
    """Records mono 16kHz 16-bit audio. Detects speech vs silence via RMS energy.

    Callbacks (all called from audio thread):
        on_speech_start()   — first speech frame after silence
        on_silence()        — when consecutive silence exceeds threshold
        on_audio_chunk()    — every frame (ndarray float32 [-1,1])
    """

    RATE = 16000
    CHANNELS = 1
    FRAME_MS = 30
    DTYPE = np.int16

    def __init__(
        self,
        silence_timeout_s: float = 10.0,
        max_duration_s: float = 60.0,
        energy_threshold: float = 0.02,
        on_speech_start: Callable[[], None] | None = None,
        on_silence: Callable[[], None] | None = None,
        on_audio_chunk: Callable[[np.ndarray], None] | None = None,
    ):
        self._silence_timeout_s = silence_timeout_s
        self._max_duration_s = max_duration_s
        self._energy_threshold = energy_threshold
        self._on_speech_start = on_speech_start
        self._on_silence = on_silence
        self._on_audio_chunk = on_audio_chunk

        self._stream: sd.InputStream | None = None
        self._frames: list[np.ndarray] = []
        self._speaking = False
        self._silent_frames = 0
        self._total_frames = 0
        self._start_time = 0.0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._frames_per_chunk = int(self.RATE * self.FRAME_MS / 1000)
        self._max_frames = int(self.RATE * self._max_duration_s / self._frames_per_chunk)

    # ------------------------------------------------------------------
    def start(self) -> None:
        """Begin recording. Non-blocking — spawns a background thread."""
        if self._thread and self._thread.is_alive():
            return
        self._frames.clear()
        self._speaking = False
        self._silent_frames = 0
        self._total_frames = 0
        self._start_time = time.monotonic()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()

    def stop(self) -> bytes:
        """Stop recording, return WAV bytes."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        return self._to_wav()

    def is_recording(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    def _record_loop(self) -> None:
        try:
            self._stream = sd.InputStream(
                samplerate=self.RATE,
                channels=self.CHANNELS,
                dtype=self.DTYPE,
                blocksize=self._frames_per_chunk,
                callback=self._audio_callback,
            )
            with self._stream:
                while not self._stop_event.is_set():
                    self._stop_event.wait(0.1)
        except sd.PortAudioError as exc:
            print(f"[AudioCapture] stream error: {exc}")
            log_event("failure", "audio input stream error", {"error": str(exc)})

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if self._stop_event.is_set():
            return

        chunk = indata[:, 0].astype(np.float32) / 32768.0  # normalize to [-1, 1]
        self._frames.append(chunk.copy())
        self._total_frames += 1

        rms = float(np.sqrt(np.mean(chunk ** 2)))
        is_speech = rms > self._energy_threshold

        if is_speech:
            if not self._speaking:
                self._speaking = True
                if self._on_speech_start:
                    self._on_speech_start()
            self._silent_frames = 0
        else:
            if self._speaking:
                self._silent_frames += 1
                silence_s = self._silent_frames * self.FRAME_MS / 1000.0
                if silence_s >= self._silence_timeout_s:
                    if self._on_silence:
                        self._on_silence()
                    return

        if self._on_audio_chunk:
            self._on_audio_chunk(chunk)

        # Max duration guard
        elapsed = time.monotonic() - self._start_time
        if elapsed >= self._max_duration_s:
            if self._on_silence:
                self._on_silence()

    # ------------------------------------------------------------------
    def _to_wav(self) -> bytes:
        if not self._frames:
            return b""
        audio = np.concatenate(self._frames)
        int16 = (audio * 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(self.RATE)
            wf.writeframes(int16.tobytes())
        return buf.getvalue()
