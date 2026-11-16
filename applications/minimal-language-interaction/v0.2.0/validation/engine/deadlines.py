"""Expire silent confirmations, retry once, and move them to a FIFO queue."""
from collections import deque
from dataclasses import dataclass

from .dialogues import CafeDialogues
from .evidence import EvidenceRouter


@dataclass(frozen=True)
class Wait:
    question_id: int
    deadline: int
    retried: bool = False


class TimedCafe:
    def __init__(self, wait_ms):
        if type(wait_ms) is not int or wait_ms < 1:
            raise ValueError("Wait must be a positive integer number of milliseconds.")
        self.wait_ms = wait_ms
        self.dialogues = CafeDialogues()
        self.evidence = EvidenceRouter(self.dialogues)
        self._clock = 0
        self._active = {}
        self._deferred = deque()

    def _wait(self, dialogue, question_id, *, retried=False):
        wait = Wait(question_id, self._clock + self.wait_ms, retried)
        self._active[dialogue] = wait
        return wait

    def start(self, dialogue, speaker, item, quantity, now):
        events = self.advance(now)
        question = self.dialogues.open_confirmation(dialogue, speaker, item, quantity)
        self._wait(dialogue, question["question_id"])
        return question, events

    def _expiration(self, dialogue, wait):
        return wait.deadline

    def advance(self, now):
        if type(now) is not int or now < self._clock:
            raise ValueError("Use a monotonic integer clock in milliseconds.")
        self._clock = now
        events = []
        ordered = sorted(self._active.items(),
                         key=lambda row: (self._expiration(*row), row[0]))
        for dialogue, wait in ordered:
            if self._expiration(dialogue, wait) > now:
                break
            if wait.retried:
                if self.dialogues.pause_confirmation(dialogue):
                    self._deferred.append(dialogue)
                    events.append({"kind": "deferred", "dialogue": dialogue})
                del self._active[dialogue]
            else:
                renewed = self.dialogues.renew_confirmation(dialogue, "다시 확인하겠습니다. ")
                if renewed is None:
                    del self._active[dialogue]
                    continue
                question_id, prompt = renewed
                self._wait(dialogue, question_id, retried=True)
                events.append({"kind": "retry", "dialogue": dialogue,
                               "question_id": question_id, "prompt": prompt})
        return events

    def reply(self, evidence, now):
        events = self.advance(now)
        old = self.evidence.retrieve(evidence.utterance_id)
        decision = self.evidence.record(evidence)
        dialogue = evidence.dialogue.value
        wait = self._active.get(dialogue)
        if old is None and wait is not None and decision.status not in {"held", "unrouted"}:
            question = decision.active_question
            if question is None:
                del self._active[dialogue]
            elif question != wait.question_id:
                self._wait(dialogue, question)
        return decision, events

    def resume_next(self, now):
        events = self.advance(now)
        if not self._deferred:
            return None, events
        dialogue = self._deferred.popleft()
        question_id, prompt = self.dialogues.renew_confirmation(dialogue, "기다리시던 주문입니다. ")
        self._wait(dialogue, question_id)
        return {"dialogue": dialogue, "question_id": question_id, "prompt": prompt}, events
