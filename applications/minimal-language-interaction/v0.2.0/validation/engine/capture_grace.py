"""Reserve decode time for a captured response tied to a live question."""
from dataclasses import dataclass, replace

from .deadlines import TimedCafe


@dataclass(frozen=True)
class Job:
    dialogue: str
    question: int
    utterance: str


class CaptureGrace(TimedCafe):
    def __init__(self, wait_ms, grace_ms, onset_window_ms=140):
        super().__init__(wait_ms)
        if type(grace_ms) is not int or grace_ms < 1:
            raise ValueError("Grace must be a positive number of milliseconds.")
        if type(onset_window_ms) is not int or not 0 < onset_window_ms < grace_ms:
            raise ValueError("Onset confirmation duration must be positive and shorter than grace.")
        self.grace_ms = grace_ms
        self.onset_window_ms = onset_window_ms
        self._jobs = {}

    def _expiration(self, dialogue, wait):
        margin = 0 if dialogue in self._jobs else self.onset_window_ms
        return wait.deadline + margin

    def advance(self, now):
        events = super().advance(now)
        for dialogue, job in tuple(self._jobs.items()):
            wait = self._active.get(dialogue)
            if wait is None or wait.question_id != job.question:
                del self._jobs[dialogue]
        return events

    def capture(self, job, onset_ms, detected_ms):
        if onset_ms < 0 or detected_ms - onset_ms != self.onset_window_ms:
            raise ValueError("Invalid capture times.")
        events = self.advance(detected_ms)
        wait = self._active.get(job.dialogue)
        if (wait is None or wait.question_id != job.question
                or not wait.deadline - self.wait_ms <= onset_ms < wait.deadline
                or job.dialogue in self._jobs):
            return False, events
        self._jobs[job.dialogue] = job
        self._active[job.dialogue] = replace(wait, deadline=wait.deadline + self.grace_ms)
        return True, events

    def complete(self, job, evidence, now):
        events = self.advance(now)
        if self._jobs.get(job.dialogue) != job:
            return None, events
        if (evidence.dialogue.value != job.dialogue or evidence.question.value != job.question
                or evidence.utterance_id != job.utterance):
            return None, events
        wait = self._active[job.dialogue]
        original = replace(wait, deadline=wait.deadline - self.grace_ms)
        decision, emitted = super().reply(evidence, now)
        self._jobs.pop(job.dialogue, None)
        if (current := self._active.get(job.dialogue)) == wait:
            self._active[job.dialogue] = original
            emitted += self.advance(now)
        return decision, events + emitted
