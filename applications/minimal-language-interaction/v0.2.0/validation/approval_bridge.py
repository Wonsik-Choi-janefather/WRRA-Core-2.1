"""Send valid, explicitly affirmed voice replies to the durable order queue."""
import json

from durable_orders import approve


def connect_utterance(cafe, directory, session_id, job, evidence, completed_ms, reference, crash=None):
    if not session_id:
        raise ValueError("A unique session ID is required.")
    assent = {"네", "예", "맞아요", "네 맞아요", "네, 맞아요"}
    text = evidence.text.value
    if text is None or any(value.strip().rstrip(".!") not in assent for value in (text, reference)):
        return None
    decision, _ = cafe.complete(job, evidence, completed_ms)
    if decision is None or decision.status != "accepted":
        return None

    payload = cafe.dialogues.orders()[job.dialogue]
    approval_id = json.dumps((session_id, job.dialogue, job.question),
                             ensure_ascii=False, separators=(",", ":"))
    approve(directory, approval_id, payload, crash)
    return approval_id
