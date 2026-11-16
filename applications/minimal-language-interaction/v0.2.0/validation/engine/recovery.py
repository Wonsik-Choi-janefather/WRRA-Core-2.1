"""Recover a café order from adjacent clarification turns."""
from copy import copy
from dataclasses import dataclass
import re

from .engine import clean
from .menu import CafeStream


@dataclass(frozen=True)
class OrderQuestion:
    item: str
    stage: str
    quantity: str = ""


class RecoveringCafeStream(CafeStream):
    def __init__(self, menu=None):
        super().__init__(menu)
        self.order_question = None

    @property
    def awaiting_order_assent(self):
        return self.order_question is not None and self.order_question.stage == "confirm"

    def finish_short_assent(self, observed, secondary_transcript):
        # Only affirmative tokens are eligible on the short-audio path.
        assent = {"네", "예"}
        if not self.awaiting_order_assent or observed.strip().rstrip(".!") not in assent:
            return None
        reference = secondary_transcript()
        if reference.strip().rstrip(".!") not in assent:
            return None
        self.cancel()
        self.feed("네", limit=0)
        return {**self.finish(), "observed": observed}

    def recognition_lost(self):
        super().recognition_lost()
        self.order_question = None

    def finish_checked(self, secondary_transcript):
        primary = copy(self)
        result = primary.finish()
        if result is None:
            return None
        reference = copy(self)
        reference.cancel()
        reference.feed(secondary_transcript(), limit=0)
        other = reference.finish()
        original_question = self.order_question
        self.cancel()
        self.order_question = None
        self._proposal = None
        if other is not None and all(
            result.get(key) == other.get(key) for key in ("status", "meaning", "proposal")
        ) and primary.order_question == reference.order_question:
            self.engine = primary.engine
            self.history_gap = primary.history_gap
            self._proposal = primary._proposal
            self.order_question = primary.order_question
            return result

        # A menu-only item may be offered for confirmation. Conflicting items
        # from the two passes are discarded, as is any stale prior question.
        candidate = primary.order_question
        reference_items = reference._menu_mentions(other["observed"]) if other else set()
        if (original_question is None and candidate is not None
                and candidate.stage != "confirm" and not reference_items):
            self.order_question = OrderQuestion(candidate.item, "candidate")
            return self._quantity_question(result)
        if self._is_quantity_disagreement(original_question, candidate, other, reference.order_question):
            self.order_question = OrderQuestion(original_question.item, "candidate")
            prompt = f"{original_question.item} 수량을 다시 말씀해 주세요."
            return self._clarify(result, "수량", prompt)
        return self._clarify(result, "품목과수량", "메뉴 이름과 수량을 다시 말씀해 주세요.")

    def _is_quantity_disagreement(self, previous, proposal, other, reference_proposal):
        if previous is None or previous.stage != "confirm" or proposal is None:
            return False
        if proposal.stage != "confirm" or proposal.item != previous.item or other is None:
            return False
        return (
            reference_proposal is not None and reference_proposal.stage == "confirm"
            and reference_proposal.item == previous.item
            or reference_proposal is None and other["status"] in {"unresolved", "clarification"}
            and not self._menu_mentions(other["observed"])
        )

    def _menu_mentions(self, text):
        return {word for word in re.findall(r"[가-힣]+", text) if word in self.menu}

    def _quantity_question(self, result):
        question = self.order_question
        prompt = f"{question.item} 수량을 말씀해 주세요." if question.stage == "known" else "수량을 다시 말씀해 주세요."
        return self._clarify(result, "수량", prompt)

    def finish(self):
        observed = self._text.strip()
        if not observed:
            return None
        text = re.sub(r"^그럼\s+", "", clean(observed))
        question, self.order_question = self.order_question, None
        if question and re.fullmatch(r"(?:아니요|아니오|아니)[, .!?]+(?:됐어요|괜찮아요|취소|취소해 주세요)", text):
            self.cancel()
            return {**self._base_result(observed), "status": "rejected"}
        if question and question.stage == "confirm":
            correction = self._correct_candidate(observed, text, question)
            if correction is not None:
                return correction
            item = self._contrast_item(text, question)
            if item is not None:
                return self._readback_candidate(self._base_result(observed), item, question.quantity)
        match = re.fullmatch(r"(?:(\S+) )?(\S+ \S+?)\s*(?:이요|요|만요| 주세요)", text)
        if match:
            item, quantity = match.groups()
            if quantity in self.engine.lex["quantities"]:
                if item is not None:
                    return self._finish_order(observed, item, quantity)
                if question and question.stage != "confirm":
                    if not self._unit_allowed(question.item, quantity):
                        return self._clarify(self._base_result(observed), "품목과단위",
                                             "메뉴 이름과 주문 단위를 다시 말씀해 주세요.")
                    if question.stage == "known":
                        return self._finish_order(observed, question.item, quantity)
                    self.order_question = OrderQuestion(question.item, "confirm", quantity)
                    return self._clarify(self._base_result(observed), "주문",
                                         f"{question.item} {quantity} 맞으세요?")
                return self._clarify(self._base_result(observed), "품목과수량",
                                     "메뉴 이름과 수량을 다시 말씀해 주세요.")

        if question and question.stage == "confirm":
            if text in {"네", "맞아요", "네 맞아요", "네, 맞아요", "네 적용해 주세요"}:
                return self._finish_order(observed, question.item, question.quantity)
            if text in {"아니요", "취소", "아니요 취소해 주세요"}:
                self.cancel()
                return {**self._base_result(observed), "status": "rejected"}

        items = self._menu_mentions(text)
        item = next(iter(items)) if len(items) == 1 else None
        item_only = self._item_reply(text)
        if item_only is not None:
            self.order_question = OrderQuestion(item_only, "known")
            return self._quantity_question(self._base_result(observed))

        result = super().finish()
        if question and question.stage == "confirm" and result["status"] == "unresolved":
            return self._clarify(
                result, "품목과수량", "확인 응답을 알아듣지 못했습니다. 품목과 수량을 다시 말씀해 주세요."
            )
        first_request, ending, _ = text.partition("주세요")
        if (result["status"] == "clarification" and item and ending
                and first_request.startswith(f"{item} ")
                and not any(q in first_request for q in self.engine.lex["quantities"])):
            self.order_question = OrderQuestion(item, "candidate")
            return self._quantity_question(result)
        return result

    def _correct_candidate(self, observed, text, question):
        negative = re.fullmatch(r"(?:아니요|아니오|아니)(?:[, .!?]+(.+))?", text)
        if not negative:
            return None
        value = negative[1]
        result = self._base_result(observed)
        if value is None or value in {"됐어요", "괜찮아요", "취소", "취소해 주세요"}:
            self.cancel()
            return {**result, "status": "rejected"}

        item = self._item_reply(value)
        quantity = self._quantity_reply(value)
        if item is None and quantity is None:
            return self._clarify(result, "품목과수량", "바꿀 품목이나 수량을 다시 말씀해 주세요.")
        return self._readback_candidate(result, item or question.item, quantity or question.quantity)

    def _contrast_item(self, text, question):
        # Accept a standalone item reply or one preceded by a single unclear
        # word. The two recognition passes must produce the same new candidate.
        prefix, _, suffix = text.rpartition(" ")
        item = self._item_reply(suffix)
        if (item is None or item == question.item or prefix in self.menu
                or (prefix and not re.fullmatch(r"[가-힣]{2,4}[,.]?", prefix))):
            return None
        return item

    def _readback_candidate(self, result, item, quantity):
        if not self._unit_allowed(item, quantity):
            self.order_question = OrderQuestion(item, "candidate")
            return self._clarify(result, "수량", f"{item} 수량과 단위를 다시 말씀해 주세요.")
        self.order_question = OrderQuestion(item, "confirm", quantity)
        return self._clarify(result, "주문", f"{item} {quantity} 맞으세요?")

    def _item_reply(self, text):
        return next((name for name in self.menu if re.fullmatch(
            rf"{re.escape(name)}\s*(?:주세요|이요|요)", text
        )), None)

    def _quantity_reply(self, text):
        return next((quantity for quantity in self.engine.lex["quantities"] if re.fullmatch(
            rf"{re.escape(quantity)}\s*(?:이요|요|만요|주세요)", text
        )), None)

    def _unit_allowed(self, item, quantity):
        return quantity.split()[-1] in self.menu.get(item, ())

    def _finish_order(self, observed, item, quantity):
        if not self._unit_allowed(item, quantity):
            return self._clarify(self._base_result(observed), "품목과단위",
                                 "메뉴 이름과 주문 단위를 다시 말씀해 주세요.")
        self.cancel()
        self.feed(f"{item} {quantity} 주세요", limit=0)
        result = super().finish()
        features, _ = self.engine.preprocess(observed)
        self.history_gap = False
        return {**result, **features, "observed": observed}
