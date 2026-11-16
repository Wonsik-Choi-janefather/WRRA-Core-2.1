"""Keep the separate judgments about each reply before routing it."""
from dataclasses import dataclass

from .dialogues import CafeDialogues


@dataclass(frozen=True)
class Observation:
    observation_id: str
    utterance_id: str
    channel: str


@dataclass(frozen=True)
class Judgment:
    source: str
    value: str | int | None
    observations: tuple[Observation, ...] = ()

    def __post_init__(self):
        if not self.source:
            raise ValueError("A judgment needs its source identifier.")


@dataclass(frozen=True)
class ReplyEvidence:
    utterance_id: str
    text: Judgment
    speaker: Judgment
    recipient: Judgment
    dialogue: Judgment
    question: Judgment

    def __post_init__(self):
        for field in (self.text, self.speaker, self.recipient, self.dialogue):
            if field.value is not None and (not isinstance(field.value, str) or not field.value.strip()):
                raise ValueError("Text and participant identifiers must be nonempty strings or unknown.")
        if self.question.value is not None and (
            type(self.question.value) is not int or self.question.value < 1
        ):
            raise ValueError("Question identifier must be a positive integer or unknown.")


@dataclass(frozen=True)
class Decision:
    evidence: ReplyEvidence
    status: str
    missing: tuple[str, ...] = ()
    active_question: int | None = None
    prompt: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ReissuedQuestion:
    question_id: int
    prompt: str


class EvidenceRouter:
    def __init__(self, dialogues: CafeDialogues):
        self.dialogues = dialogues
        self._decisions: dict[str, Decision] = {}
        self._reissued: dict[str, ReissuedQuestion] = {}

    def record(self, evidence: ReplyEvidence) -> Decision:
        if not evidence.utterance_id:
            raise ValueError("An utterance identifier is required.")
        prior = self._decisions.get(evidence.utterance_id)
        if prior is not None:
            if prior.evidence != evidence:
                raise ValueError("This utterance already has a recorded assessment.")
            return prior

        missing = tuple(name for name in ("text", "speaker", "recipient", "dialogue", "question")
                        if getattr(evidence, name).value is None)
        if missing:
            decision = Decision(evidence, "held", missing)
        elif (reason := self._basis_problem(evidence)) is not None:
            decision = Decision(evidence, "held", reason=reason)
        else:
            result = self.dialogues.reply(
                text=evidence.text.value,
                speaker=evidence.speaker.value,
                recipient=evidence.recipient.value,
                dialogue_id=evidence.dialogue.value,
                question_id=evidence.question.value,
            )
            decision = Decision(evidence, result["status"], active_question=result.get("question_id"),
                                prompt=result.get("prompt"))
        self._decisions[evidence.utterance_id] = decision
        return decision

    def _basis_problem(self, evidence: ReplyEvidence) -> str | None:
        speaker = evidence.speaker.observations
        recipient = evidence.recipient.observations
        if not speaker or not recipient:
            return "missing_observation"
        if any(item.utterance_id != evidence.utterance_id for item in (*speaker, *recipient)):
            return "different_utterance"
        recipient_ids = {item.observation_id for item in recipient}
        if any(item.observation_id in recipient_ids for item in speaker):
            return "shared_observation"
        if not any(item.channel == "voice" for item in speaker):
            return "missing_voice_observation"
        return None

    def reask(self, utterance_id: str) -> ReissuedQuestion | None:
        decision = self.retrieve(utterance_id)
        if decision is None or decision.status not in {"held", "unrouted"}:
            return None
        if utterance_id in self._reissued:
            return None
        evidence = decision.evidence
        if evidence.recipient.value not in {None, self.dialogues.device}:
            return None
        if "text" in decision.missing:
            prefix = "답을 다시 말씀해 주세요. "
        elif decision.status == "held":
            prefix = "주문하신 고객님께 다시 확인하겠습니다. "
        else:
            prefix = "현재 확인할 주문입니다. "
        issued = self.dialogues.renew_confirmation(evidence.dialogue.value, prefix)
        if issued is None:
            return None
        replacement = ReissuedQuestion(*issued)
        self._reissued[utterance_id] = replacement
        return replacement

    def retrieve(self, utterance_id: str) -> Decision | None:
        return self._decisions.get(utterance_id)
