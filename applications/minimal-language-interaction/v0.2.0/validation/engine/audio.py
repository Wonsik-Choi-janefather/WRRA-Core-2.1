"""PCM input with an energy endpoint and replaceable Korean transcription."""
from array import array
from collections import deque
from math import sqrt
import sys

from .stream import Stream

RATE = 16000
FRAME_MS = 20
FRAME_BYTES = RATE * FRAME_MS // 1000 * 2
SHORT_ASSENT_MS = 120


class WhisperKorean:
    def __init__(self, model_path, initial_prompt=None):
        import numpy as np
        from faster_whisper import WhisperModel

        self.initial_prompt = initial_prompt
        self.numpy = np
        self.model = WhisperModel(str(model_path), device="cpu", compute_type="int8")

    def __call__(self, pcm, final):
        return self._decode(pcm, final, self.initial_prompt)

    def without_prompt(self, pcm):
        return self._decode(pcm, True, None)

    def _decode(self, pcm, final, initial_prompt):
        waveform = self.numpy.frombuffer(pcm, dtype="<i2").astype("float32") / 32768
        segments, _ = self.model.transcribe(
            waveform, language="ko", beam_size=3 if final else 1,
            temperature=0, condition_on_previous_text=False, initial_prompt=initial_prompt,
        )
        return "".join(segment.text for segment in segments).strip()


def rms(frame):
    samples = array("h")
    samples.frombytes(frame)
    if sys.byteorder != "little":
        samples.byteswap()
    return sqrt(sum(float(sample) ** 2 for sample in samples) / len(samples))


class AudioInput:
    def __init__(self, transcribe, stream=None, *, threshold=500,
                 silence_ms=700, minimum_voice_ms=160,
                 partial_ms=600, max_turn_ms=15000, crosscheck=None, ignore_short_activity=False):
        settings = (silence_ms, minimum_voice_ms, partial_ms, max_turn_ms)
        if threshold <= 0 or any(n < FRAME_MS or n % FRAME_MS for n in settings):
            raise ValueError("Provide a positive threshold and frame-aligned durations.")
        if max_turn_ms < minimum_voice_ms:
            raise ValueError("The maximum turn must fit the minimum voice duration.")
        self.ignore_short_activity = ignore_short_activity
        self.crosscheck = crosscheck
        self.transcribe = transcribe
        self.stream = stream if stream is not None else Stream()
        self.threshold = threshold
        self.silence = silence_ms // FRAME_MS
        self.minimum = minimum_voice_ms // FRAME_MS
        self.partial = partial_ms // FRAME_MS
        self.maximum = max_turn_ms // FRAME_MS
        self._pending = bytearray()
        self._preroll = deque(maxlen=5)
        self._dropping = False
        self._reset_turn()

    def _reset_turn(self):
        self._frames = []
        self._voiced = self._quiet = self._elapsed = 0
        self._last_partial = None

    def _discard(self, reason):
        self.stream.cancel()
        notify = getattr(self.stream, "recognition_lost", None)
        if notify is not None:
            notify()
        return {"event": "discarded", "reason": reason}

    def _complete(self):
        if self._voiced < self.minimum:
            result = self._short_assent()
            self._reset_turn()
            self.stream.cancel()
            if self.ignore_short_activity:
                return result
            return self._discard("short_activity")

        pcm = b"".join(self._frames)
        self._reset_turn()
        self.stream.cancel()
        text = self.transcribe(pcm, final=True).strip()
        if not text:
            return self._discard("empty_transcript")
        self.stream.feed(text, limit=0)
        result = self.stream.finish() if self.crosscheck is None else self.stream.finish_checked(
            lambda: self.crosscheck(pcm)
        )
        return {"event": "final", "analysis": result}

    def _short_assent(self):
        if (not self.ignore_short_activity or self.crosscheck is None
                or self._voiced * FRAME_MS < SHORT_ASSENT_MS
                or not getattr(self.stream, "awaiting_order_assent", False)):
            return None
        pcm = b"".join(self._frames)
        result = self.stream.finish_short_assent(
            self.transcribe(pcm, final=True), lambda: self.crosscheck(pcm)
        )
        return {"event": "final", "analysis": result} if result is not None else None

    def accept(self, pcm):
        self._pending.extend(pcm)
        events = []
        processed = len(self._pending) // FRAME_BYTES * FRAME_BYTES
        for start in range(0, processed, FRAME_BYTES):
            frame = self._pending[start:start + FRAME_BYTES]
            voice = rms(frame) >= self.threshold
            if self._dropping:
                self._quiet = 0 if voice else self._quiet + 1
                if self._quiet >= self.silence:
                    self._dropping = False
                    self._reset_turn()
                continue
            if not self._frames:
                if not voice:
                    self._preroll.append(bytes(frame))
                    continue
                self._frames.extend(self._preroll)
                self._preroll.clear()
            self._frames.append(bytes(frame))
            self._elapsed += 1
            self._voiced += voice
            self._quiet = 0 if voice else self._quiet + 1

            if self._quiet >= self.silence:
                event = self._complete()
                if event is not None:
                    events.append(event)
            elif self._elapsed >= self.maximum:
                self._reset_turn()
                self._dropping = True
                self.stream.cancel()
                events.append(self._discard("turn_too_long"))
            elif voice and self._voiced >= self.minimum and self._elapsed % self.partial == 0:
                text = self.transcribe(b"".join(self._frames), final=False).strip()
                if text != self._last_partial:
                    self._last_partial = text
                    self.stream.cancel()
                    events.append({"event": "partial", "analysis": self.stream.feed(text)})
        del self._pending[:processed]
        return events

    def end_input(self):
        """Flush a finite recording or explicit user stop."""
        if len(self._pending) % 2:
            raise ValueError("PCM input ended with an incomplete 16-bit sample.")
        events = []
        if self._pending:
            events.extend(self.accept(bytes(FRAME_BYTES - len(self._pending))))
        if self._frames and not self._dropping:
            event = self._complete()
            if event is not None:
                events.append(event)
        self._preroll.clear()
        self._dropping = False
        self._reset_turn()
        return events
