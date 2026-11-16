"""Ablate one piece of stage direction at a time and keep the dialogue fixed."""
from collections import Counter
import json
from pathlib import Path

from engine.dialogues import CafeDialogues
from engine.evidence import EvidenceRouter, Judgment, Observation, ReplyEvidence

POLICIES = ("all", "without_speaker", "without_recipient", "without_question")


def evaluate(scene, policy):
    dialogues = CafeDialogues()
    a = dialogues.open_confirmation("a", "A", "녹차", "한 잔")["question_id"]
    b = dialogues.open_confirmation("b", "B", "보리차", "두 잔")["question_id"]
    current = {"a": a, "b": b}
    if scene.get("prelude") == "correct":
        correction = dialogues.reply(dialogue_id="a", question_id=a, speaker="A",
                                     recipient="카페", text="아니요, 두 잔이요.")
        assert correction["prompt"] == "녹차 두 잔 맞으세요?"
        current["a"] = correction["question_id"]
    assert dialogues.orders() == {}

    target = scene["dialogue"]
    speaker = {"a": "A", "b": "B"}[target] if policy == "without_speaker" else scene["speaker"]
    recipient = dialogues.device if policy == "without_recipient" else scene["recipient"]
    question = current[target] if policy == "without_question" else {
        "current": current[target], "old": a, "other": b, None: None
    }[scene["question"]]

    utterance = "reply"
    voice = Observation("voice/reply", utterance, "voice")
    visual_address = Observation("address/reply", utterance, "gaze")
    evidence = ReplyEvidence(
        utterance, Judgment("받아쓰기", "네", (voice,)), Judgment("화자", speaker, (voice,)),
        Judgment("수신자", recipient, (visual_address,)), Judgment("대화", target),
        Judgment("질문", question),
    )
    decision = EvidenceRouter(dialogues).record(evidence)
    orders = dialogues.orders()
    return {"scene": scene["id"], "decision": decision.status, "orders": orders,
            "correct": orders == scene["expected"],
            "wrong_registrations": sum(order != scene["expected"].get(key)
                                       for key, order in orders.items())}


def main():
    scenes = json.loads(Path(__file__).with_name("scenes.json").read_text(encoding="utf-8"))
    results = {}
    for policy in POLICIES:
        rows = [evaluate(scene, policy) for scene in scenes]
        counts = Counter({"correct": sum(row["correct"] for row in rows),
                          "wrong_registrations": sum(row["wrong_registrations"] for row in rows)})
        results[policy] = {"counts": counts, "scenes": rows}
    assert results["all"]["counts"] == {"correct": 10, "wrong_registrations": 0}
    assert all(results[policy]["counts"]["wrong_registrations"] > 0 for policy in POLICIES[1:])
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
