"""Route an addressed reply to its own café question."""
from dataclasses import dataclass
from itertools import count

from .recovery import OrderQuestion, RecoveringCafeStream


@dataclass
class Dialogue:
    speaker: str
    stream: RecoveringCafeStream
    question_id: int | None = None


class CafeDialogues:
    def __init__(self, device="카페"):
        if not device:
            raise ValueError("Device identifier is required.")
        self.device = device
        self._dialogues = {}
        self._ids = count(1)

    def has_dialogue(self, dialogue_id):
        return dialogue_id in self._dialogues

    def open_confirmation(self, dialogue_id, speaker, item, quantity):
        if not dialogue_id or not speaker or dialogue_id in self._dialogues:
            raise ValueError("A new dialogue and a speaker identifier are required.")
        stream = RecoveringCafeStream()
        if quantity not in stream.engine.lex["quantities"] or not stream._unit_allowed(item, quantity):
            raise ValueError("Order must use a valid menu item and quantity.")
        stream.order_question = OrderQuestion(item, "confirm", quantity)
        dialogue = Dialogue(speaker, stream, next(self._ids))
        self._dialogues[dialogue_id] = dialogue
        return {"question_id": dialogue.question_id, "prompt": f"{item} {quantity} 맞으세요?"}

    def reply(self, *, dialogue_id, question_id, speaker, recipient, text, reference=None):
        dialogue = self._dialogues.get(dialogue_id)
        if recipient != self.device or dialogue is None or not speaker or speaker != dialogue.speaker:
            return {"status": "unrouted"}
        if dialogue.question_id is None or question_id != dialogue.question_id:
            return {"status": "unrouted"}
        if not text.strip():
            return {"status": "unrouted"}

        previous = dialogue.stream.order_question
        dialogue.stream.feed(text, limit=0)
        result = dialogue.stream.finish_checked(lambda: text if reference is None else reference)
        question = dialogue.stream.order_question
        if question is None:
            dialogue.question_id = None
        elif question != previous or result.get("prompt"):
            dialogue.question_id = next(self._ids)
        return {**result, "question_id": dialogue.question_id, "dialogue_id": dialogue_id}

    def renew_confirmation(self, dialogue_id, prefix):
        dialogue = self._dialogues.get(dialogue_id)
        if dialogue is None or dialogue.stream.order_question is None:
            return None
        question = dialogue.stream.order_question
        dialogue.question_id = next(self._ids)
        if question.stage == "confirm":
            text = f"{question.item} {question.quantity} 맞으세요?"
        else:
            subject = f"{question.item} " if question.stage == "known" else ""
            text = f"{subject}수량을 다시 말씀해 주세요."
        return dialogue.question_id, prefix + text

    def pause_confirmation(self, dialogue_id):
        dialogue = self._dialogues.get(dialogue_id)
        if dialogue is None or dialogue.stream.order_question is None:
            return False
        dialogue.question_id = None
        return True

    def orders(self):
        return {key: dialogue.stream.engine.order.copy()
                for key, dialogue in self._dialogues.items() if dialogue.stream.engine.order is not None}
