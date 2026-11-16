"""Context for a café-specific ordering session."""
from copy import copy, deepcopy
import json
from pathlib import Path
import re

from .engine import call
from .guarded import GuardedStream

MENU = Path(__file__).with_name("menu.json")


class CafeStream(GuardedStream):
    def __init__(self, menu=None):
        super().__init__()
        menu = json.loads(MENU.read_text()) if menu is None else menu
        self.menu = {item: tuple(units) for item, units in menu.items()}
        self.engine.lex["objects"] = list(self.menu)
        # This recognizer uses a limited number vocabulary, shared by the parsers.
        self.engine.lex["quantities"] = {
            f"{number} {unit}": f"{number}{unit}"
            for number in ("한", "두", "세", "네", "다섯")
            for unit in sorted({unit for units in self.menu.values() for unit in units})
        }

    def recognition_prompt(self):
        return "카페 주문에서 사용하는 품목과 단위입니다. " + ", ".join(
            f'{item}({" 또는 ".join(units)})' for item, units in self.menu.items()
        ) + "."

    def finish_checked(self, secondary_transcript):
        candidate = copy(self)
        result = candidate.finish()
        if result is None or result["status"] in {"unresolved", "clarification"}:
            return self.finish()

        reference = copy(self)
        reference.cancel()
        reference.feed(secondary_transcript(), limit=0)
        other = reference.finish()
        fields = ("status", "meaning", "proposal")
        if other is None or any(result.get(key) != other.get(key) for key in fields):
            return self._clarify(
                result, "품목과수량", "주문을 정확히 듣지 못했습니다. 메뉴 이름과 수량을 다시 말씀해 주세요."
            )
        self.cancel()
        self.engine = candidate.engine
        self.history_gap = candidate.history_gap
        self._proposal = candidate._proposal
        return result

    def finish(self):
        # Apply on a copy first so a failed menu check cannot alter the live order.
        trial = copy(self)
        trial.engine = deepcopy(self.engine)
        result = super(CafeStream, trial).finish()
        if result is None:
            return None
        order_intent = re.search(
            r"주세요|주시겠어요|주실래요|부탁|만요|바꿔|주문", result["observed"]
        )
        proposed = trial._proposal
        next_order = proposed[0].order if proposed else trial.engine.order
        meaning = result.get("meaning") or ""
        if meaning.startswith("요청(주다("):
            expected = next_order and call(
                "요청", call("주다", "청자", "화자", next_order["품목"], next_order["수량"])
            )
            if meaning != expected:
                return self._clarify(result, "수량", "몇 잔이나 몇 개를 주문하시는지 다시 말씀해 주세요.")
        changed_order = next_order is not None and (
            next_order != self.engine.order or
            meaning.startswith("요청(주다(")
        )
        if changed_order:
            item, amount = next_order["품목"], next_order["수량"]
            unit = next((u for u in self.menu.get(item, ()) if amount.endswith(u)), None)
            if unit is None:
                return self._clarify(result, "품목과단위", "메뉴와 주문 단위를 다시 말씀해 주세요.")
        if result["status"] == "unresolved" and order_intent:
            return self._clarify(result, "품목과수량", "주문을 정확히 듣지 못했습니다. 메뉴 이름과 수량을 다시 말씀해 주세요.")
        self.cancel()
        self.engine = trial.engine
        self.history_gap = trial.history_gap
        self._proposal = trial._proposal
        return result

    def _clarify(self, result, field, prompt):
        self.cancel()
        self._proposal = None
        return {**result, "status": "clarification", "meaning": f"확인({field})", "proposal": None, "prompt": prompt}
