"""Stage spoken corrections until the user confirms the proposed record."""
from copy import deepcopy

from .engine import clean
from .spoken_forms import normalize
from .stream import Stream

CONFIRM = {"네 적용해 주세요", "네 적용해"}
REJECT = {"아니요 취소해 주세요", "아니요 취소해", "취소"}


def directional_particle(text):
    code = ord(text[-1]) - 0xAC00
    return "으로" if 0 <= code < 11172 and code % 28 not in (0, 8) else "로"


class GuardedStream(Stream):
    def __init__(self, engine=None):
        super().__init__(engine)
        self.history_gap = False
        self._proposal = None

    def recognition_lost(self):
        self.history_gap = True
        self._proposal = None

    def _base_result(self, observed):
        features, _ = self.engine.preprocess(observed)
        return {"observed": observed, **features, "meaning": None}

    def finish(self):
        observed = self._text.strip()
        if not observed:
            return None
        self.cancel()
        spoken = clean(observed).replace("네, ", "네 ", 1).replace("아니요, ", "아니요 ", 1)
        proposal, self._proposal = self._proposal, None
        if spoken in CONFIRM:
            result = self._base_result(observed)
            if proposal is None:
                return {**result, "status": "clarification", "meaning": "확인(어느정정)"}
            self.engine, meaning = proposal
            return {**result, "status": "confirmed", "meaning": meaning}
        if spoken in REJECT:
            return {**self._base_result(observed), "status": "rejected"}

        draft = Stream(deepcopy(self.engine))
        draft.feed(normalize(observed), limit=0)
        result = {**draft.finish(), "observed": observed}
        meaning = result["meaning"]
        if meaning is None:
            self.recognition_lost()
            return {**result, "status": "unresolved"}
        if meaning.startswith("확인("):
            return {**result, "status": "clarification"}
        if not meaning.startswith("정정("):
            self.engine = draft.engine
            return {**result, "status": "accepted"}
        if self.history_gap:
            field = "어느약속" if meaning.startswith("정정(만나다(") else "정정대상과새값"
            return {**result, "status": "clarification", "meaning": f"확인({field})",
                    "prompt": "앞선 말 일부를 알아듣지 못했습니다. 바꿀 대상과 새 값을 처음부터 다시 말해 주세요."}
        self._proposal = draft.engine, meaning
        return {**result, "status": "pending", "meaning": None, "proposal": meaning,
                "prompt": self._readback(meaning, draft.engine)}

    def _readback(self, meaning, proposed_engine):
        if meaning.startswith("정정(만나다("):
            for before, after in zip(self.engine.meetings, proposed_engine.meetings):
                if before != after:
                    target = " ".join(before.values())
                    updated = " ".join(after.values())
                    return f"{target} 약속을 {updated}{directional_particle(updated)} 바꿀까요?"
            return "약속은 이미 같은 내용입니다. 그대로 둘까요?"
        if meaning.startswith("정정(주다(") and self.engine.order and proposed_engine.order:
            quantities = {value: surface for surface, value in self.engine.lex["quantities"].items()}
            target = self.engine.order
            updated = proposed_engine.order
            old_amount = quantities.get(target["수량"], target["수량"])
            new_amount = quantities.get(updated["수량"], updated["수량"])
            return (f"{target['품목']} {old_amount} 주문을 {updated['품목']} "
                    f"{new_amount}{directional_particle(new_amount)} 바꿀까요?")
        return f"이 변경을 적용할까요? {meaning}"
