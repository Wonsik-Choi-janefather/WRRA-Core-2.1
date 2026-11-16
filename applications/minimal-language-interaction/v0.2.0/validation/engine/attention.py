"""Ground the customer and the order card in a confirmation question."""
from dataclasses import dataclass

from .dialogues import CafeDialogues


@dataclass(frozen=True)
class OrderCard:
    owner: str
    item: str
    quantity: str


class CafeAttention:
    def __init__(self, customer_names, cards):
        self.names = dict(customer_names)
        self.cards = dict(cards)
        self.dialogues = CafeDialogues()

    def ask(self, *, called_name="고객님", gaze_customer=None, pointed_card=None, displayed_cards=()):
        customer = self._customer(called_name, gaze_customer)
        card_id = self._card(pointed_card, displayed_cards)
        if customer is None or card_id is None:
            missing = "손님과 주문" if customer is None and card_id is None else (
                "손님" if customer is None else "주문"
            )
            return {"status": "ungrounded", "missing": missing}

        card = self.cards[card_id]
        if card.owner != customer:
            return {"status": "ungrounded", "missing": "손님과 주문의 연결"}

        if self.dialogues.has_dialogue(card_id):
            return {"status": "already_opened", "dialogue_id": card_id}

        question = self.dialogues.open_confirmation(card_id, customer, card.item, card.quantity)
        return {**question, "status": "opened", "customer": customer, "dialogue_id": card_id,
                "prompt": f"{called_name}, 이게 맞으시죠?"}

    def _customer(self, name, gaze):
        named = {customer for customer, label in self.names.items() if label == name}
        if name != "고객님" and not named:
            return None
        if gaze is not None:
            return gaze if gaze in self.names and (name == "고객님" or gaze in named) else None
        return next(iter(named)) if len(named) == 1 and name != "고객님" else None

    def _card(self, pointed, displayed):
        visible = set(displayed) if displayed else set()
        if pointed is not None:
            return pointed if pointed in self.cards and (not visible or pointed in visible) else None
        if len(visible) != 1:
            return None
        candidate = next(iter(visible))
        return candidate if candidate in self.cards else None
