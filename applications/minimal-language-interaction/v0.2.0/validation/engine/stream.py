"""Incremental input for recognized Korean text, with explicit turn commitment."""
from copy import copy
from itertools import product
import json
from pathlib import Path
import re

from .engine import Engine

ROOT = Path(__file__).resolve().parent


class Stream:
    def __init__(self, engine=None):
        self.engine = engine if engine is not None else Engine()
        self._text = ""
        self._templates = json.loads((ROOT / "phrases.json").read_text())

    def _candidates(self, observed, limit):
        if not limit or not observed.strip():
            return []
        slots = {"품목": self.engine.lex["objects"], "수량": self.engine.lex["quantities"]}
        candidates = {}
        for template in self._templates:
            pattern = template["template"]
            keys = re.findall(r"\{([^{}]+)\}", pattern)
            for values in product(*(slots[key] for key in keys)):
                phrase = pattern.format(**dict(zip(keys, values)))
                if phrase != observed and phrase.startswith(observed):
                    candidates[phrase] = max(candidates.get(phrase, 0), template["weight"])
        return sorted(candidates, key=lambda phrase: (-candidates[phrase], phrase))[:limit]

    def _input_for_parser(self, observed):
        # An explicit self-repair within one supported order construction.
        quantities = "|".join(map(re.escape, self.engine.lex["quantities"]))
        # A completed request followed by a same-turn quantity repair.
        # Keep the request ending so honorific analysis sees the original cue.
        repair = re.fullmatch(
            rf"(.+?) ({quantities}) (주세요|주실래요\?)[.!]?\s+아니\s*,?\s+({quantities})만요[.!]?",
            observed,
        )
        if repair and repair[1] in self.engine.lex["objects"]:
            item, _, request, quantity = repair.groups()
            return f"{item} {quantity} {request}"
        match = re.fullmatch(
            rf"(.+?) ({quantities})\s*,?\s+아니\s*,?\s+({quantities})만 (주세요|주실래요\?)[.!]?",
            observed,
        )
        if match and match[1] in self.engine.lex["objects"]:
            return f"{match[1]} {match[3]} {match[4]}"
        return observed

    def _slots(self, observed):
        quantities = "|".join(map(re.escape, self.engine.lex["quantities"]))
        order = re.match(rf"^(.+?) ({quantities})(?:\s|$|,)", observed)
        change = re.match(rf"^({quantities})(?:으)?로(?:\s|$)", observed)
        if order and order[1] in self.engine.lex["objects"]:
            item, quantity = order.groups()
            repair = re.search(rf"(?:^|[ ,])아니\s*,?\s+({quantities})(?:만|[ ,]|$)", observed)
            return {"품목": item, "수량": repair[1] if repair else quantity,
                    "부정_표지": bool(re.search(r"(?:^|\s)(?:안|못)(?:\s|$)", observed))}
        if change:
            return {"수량": change[1], "정정_단서": "바꿔" in observed}
        return {}

    def feed(self, chunk, limit=5):
        """Append only observed text. Predictions do not enter the input."""
        if not isinstance(chunk, str):
            raise TypeError("chunk must be a string")
        if limit < 0:
            raise ValueError("limit must be non-negative")
        self._text += chunk
        observed = self._text.lstrip()
        # Use the same parser provisionally on a disposable copy of its
        # mutable state; the live dialogue state belongs to finish().
        preview = copy(self.engine)
        preview.meetings = [dict(record) for record in self.engine.meetings]
        preview.order = None if self.engine.order is None else dict(self.engine.order)
        preview.route = None if self.engine.route is None else dict(self.engine.route)
        return {"observed": self._text, "tentative_slots": self._slots(observed),
                "completions": self._candidates(observed, limit),
                "tentative": preview.analyze(self._input_for_parser(observed)) if observed else None}

    def cancel(self):
        """Discard the current input without running any dialogue update."""
        self._text = ""

    def finish(self):
        """Commit exactly the observed turn when its boundary is supplied."""
        observed = self._text.strip()
        if not observed:
            return None
        result = self.engine.analyze(self._input_for_parser(observed))
        self.cancel()
        return {"observed": observed, **result}
