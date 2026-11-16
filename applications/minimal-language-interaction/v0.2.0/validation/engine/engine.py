import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def call(name, *args):
    return f"{name}({','.join(args)})"


def clean(text):
    return text.strip().rstrip(".!?").strip()


class Engine:
    def __init__(self, lexicon=None, disabled=()):
        self.lex = lexicon if lexicon is not None else json.loads((ROOT / "lexicon.json").read_text())
        self.disabled = set(disabled)
        self.last_fact = None
        self.meetings = []
        self.order = None
        self.route = None

    def record(self, fact):
        if "retain" not in self.disabled:
            self.last_fact = fact
        return call("알림", fact)

    def entity(self, token, endings, category):
        for ending in endings:
            if token.endswith(ending) and token[:-len(ending)] in self.lex[category]:
                return token[:-len(ending)]
        return None

    def loan(self, text):
        words = text.split()
        if len(words) < 2 or words[-1] not in self.lex["loan_verbs"]:
            return None
        roles = {}
        endings = {"subject": (("이가", "이는", "가", "이", "는", "은"), "people"),
                   "other": (("이한테", "이에게", "한테", "에게"), "people"),
                   "object": (("를", "을"), "objects")}
        noun_phrases = words[:-1]
        if len(noun_phrases) > 3:
            return None
        for token in noun_phrases:
            matches = [(role, self.entity(token, suffixes, category))
                       for role, (suffixes, category) in endings.items()]
            matches = [(role, value) for role, value in matches if value is not None]
            if not matches and token in self.lex["objects"] and token not in self.lex["people"]:
                matches = [("object", token)]
            if len(matches) != 1 or matches[0][0] in roles:
                return None
            role, roles[role] = matches[0]
        if "bind" in self.disabled:
            return None
        if set(roles) != set(endings):
            if "subject" in roles and len(roles) == 2:
                if "object" not in roles:
                    return "확인(무엇을)"
                return "확인(누구에게)" if self.lex["loan_verbs"][words[-1]] == "give" else "확인(누구에게서)"
            return None
        subject, other = roles["subject"], roles["other"]
        if self.lex["loan_verbs"][words[-1]] == "receive":
            subject, other = other, subject
        return self.record(call("빌려주다", subject, other, roles["object"]))

    def revise(self, record, clarification, predicate, fixed_roles, field, value):
        if record is None or "update" in self.disabled:
            return clarification
        record[field] = value
        return call("정정", call(predicate, *fixed_roles, *record.values()))

    def order_step(self, text):
        match = re.fullmatch(r"(수량|품목)은 (.+?)(?:으)?로 바꿔 주세요", text)
        implicit_quantity = re.fullmatch(r"(.+?)(?:으)?로 바꿔 주세요", text)
        if match or (implicit_quantity and implicit_quantity[1] in self.lex["quantities"]):
            field, value = match.groups() if match else ("수량", implicit_quantity[1])
            values = self.lex["quantities"] if field == "수량" else self.lex["objects"]
            if value not in values:
                return None
            if field == "수량":
                value = values[value]
            return self.revise(self.order, "확인(어느주문)", "주다", ("청자", "화자"), field, value)
        quantities = "|".join(map(re.escape, self.lex["quantities"]))
        match = re.fullmatch(rf"(.+?) ({quantities}) (?:주세요|부탁해요|부탁합니다)", text)
        reverse = re.fullmatch(rf"({quantities}) 주세요, (.+?)로요", text)
        if match or reverse:
            item, quantity = match.groups() if match else tuple(reversed(reverse.groups()))
            if item not in self.lex["objects"]:
                return None
            record = {"품목": item.replace(" ", ""), "수량": self.lex["quantities"][quantity]}
            if "retain" not in self.disabled:
                self.order = record
            return call("요청", call("주다", "청자", "화자", *record.values()))
        if re.fullmatch(rf"(?:{quantities}) (?:주세요|부탁해요|부탁합니다)", text):
            return "확인(무엇을주문할까요)"
        return None

    def route_step(self, text):
        places = self.lex["route_points"]
        directions = self.lex["directions"]
        match = re.fullmatch(r"(방향|지점)은 (.+?)(?:으)?로 바꿔 주세요", text)
        if match:
            field, value = match.groups()
            values = directions if field == "방향" else places
            if value not in values:
                return None
            return self.revise(self.route, "확인(어느길안내)", "돌다", ("청자",), field, values[value])
        match = re.fullmatch(r"(.+?)에서 (.+?)(?:으)?로 (?:도세요|돌아 주세요)", text)
        reverse = re.fullmatch(r"(.+?)(?:으)?로 도세요, (.+?)에서요", text)
        if not (match or reverse):
            return None
        place, direction = match.groups() if match else tuple(reversed(reverse.groups()))
        if direction not in directions:
            return None
        if place not in places:
            return "확인(어느골목)"
        record = {"지점": places[place], "방향": directions[direction]}
        if "retain" not in self.disabled:
            self.route = record
        return call("안내", call("돌다", "청자", *record.values()))

    def normalize_register(self, raw):
        text = clean(raw)
        if "normalize_register" in self.disabled or re.search(r"(?<!\S)(?:안|못)(?!\S)", text):
            return text
        for ending, canonical in self.lex["register_suffixes"].items():
            if not text.endswith(" " + ending):
                continue
            if raw.rstrip().endswith("?") and ending not in ("주실래요", "주시겠어요"):
                return text
            return text[:-len(ending)] + canonical
        if re.match(r"(?:[월화수목금토일]요일 약속 )?(?:날짜|장소|시각)(?:는|은) ", text):
            if raw.rstrip().endswith("?") or re.search(r"아닙니다$|아니에요$", text):
                return text
            for ending, canonical in self.lex["correction_suffixes"].items():
                if text.endswith(ending):
                    return text[:-len(ending)] + canonical
        return text

    def preprocess(self, raw):
        text = clean(raw)
        normalized = self.normalize_register(raw)
        question = raw.rstrip().endswith("?")
        blocked = question and normalized == text and "normalize_register" not in self.disabled
        plain = text if not blocked else None
        # Only registered form-to-form pairs are reduced. Preserve literal
        # negatives, even when part of their ending indicates politeness.
        negated = re.search(r"(?<!\S)(?:안|못)(?!\S)|아닙니다$|아니에요$|지 마세요$|적이 없어요$",text)
        features = []
        ending = None
        for suffix, (ordinary, tags) in sorted(self.lex["honorific_endings"].items(),
                                                key=lambda item: -len(item[0])):
            if not text.endswith(suffix):
                continue
            ending = suffix
            features = tags.copy()
            if plain is not None and not negated:
                plain = text[:-len(suffix)] + ordinary
            break
        if blocked or negated:
            plain = None
        return {
            "plain": plain,
            "honorifics": features,
            "ending": ending,
            "question_mark": question,
            "negation_marker": bool(negated),
        }, None if blocked else normalized

    def analyze(self, text):
        metadata, parser_text = self.preprocess(text)
        sense = self.execute(parser_text) if parser_text is not None else None
        return {**metadata, "meaning": sense}

    def step(self, text):
        return self.analyze(text)["meaning"]

    def execute(self, text):
        for parse in (self.order_step, self.route_step):
            result = parse(text)
            if result is not None:
                return result
        match = re.fullmatch(r"(.+?) 주세요", text)
        if match and match[1] in self.lex["objects"]:
            return call("요청", call("주다", "청자", "화자", match[1]))
        match = re.fullmatch(r"(.+?)(은|는)? (?:(.+?)에 |좀 )?([^ ]+) 줘", text)
        if match and match[1] in self.lex["objects"] and match[4] in self.lex["orders"]:
            args = ["청자", match[1]]
            if match[3]:
                args.append(match[3])
            return call("요청", call(self.lex["orders"][match[4]], *args))
        if text.endswith(" 문자 보내 줘"):
            condition = text.removesuffix(" 문자 보내 줘")
            if condition in self.lex["conditions"]:
                return call("요청", call("조건", call(self.lex["conditions"][condition], "청자"),
                                        call("보내다", "청자", "화자", "문자")))
        match = re.fullmatch(r"(.+?)에서 세워 주세요", text)
        if match:
            return call("요청", call("세우다", "청자", "차", match[1]))
        match = re.fullmatch(r"((?:월|화|수|목|금|토|일)요일) (.+? 시)에 (.+?)에서 만나자", text)
        if match:
            if "retain" not in self.disabled:
                meeting = dict(zip(("날짜", "시각", "장소"), match.groups()))
                if meeting not in self.meetings:
                    self.meetings.append(meeting)
            return call("제안", call("만나다", "우리", *match.groups()))
        match = re.fullmatch(r"(?:([월화수목금토일]요일) 약속 )?(날짜|장소|시각)(?:는|은) (.+?)(?:이야|야)", text)
        if match:
            day, field, value = match.groups()
            candidates = [item for item in self.meetings if day is None or item["날짜"] == day]
            meeting = candidates[0] if len(candidates) == 1 else None
            return self.revise(meeting, "확인(어느약속)", "만나다", ("우리",), field, value)
        match = re.fullmatch(r"(\S+) (\S+) 잠갔어", text)
        if match:
            actor = self.entity(match[1], ("이가", "가", "이"), "people")
            obj = self.entity(match[2], ("을", "를"), "objects")
            if actor and obj:
                return self.record(call("잠그다", actor, obj))
        match = re.fullmatch(r"(\S+) 그 사실을 알아", text)
        if match:
            actor = self.entity(match[1], ("이는", "은", "는"), "people")
            if not actor or "embed" in self.disabled:
                return None
            if self.last_fact is None:
                return "확인(어느사실)"
            return call("알림", call("알다", actor, self.last_fact))
        match = re.fullmatch(r"국(이 식기 전에 먹자|을 먹기 전에 식히자)", text)
        if match:
            serve = call("먹다", "우리", "국")
            before = (serve, call("식다", "국")) if text.startswith("국이") else (
                call("식히다", "우리", "국"), serve)
            return call("제안", call("먼저", *before))
        match = re.fullmatch(r"(.+?)(이|가) (있으면|없으면) (.+?)(는 빼 주세요|로 주세요)", text)
        if match:
            condition = call("있다", match[1])
            if match[3] == "없으면":
                condition = call("부정", condition)
            action = (call("빼다", "청자", match[4]) if match[5] == "는 빼 주세요"
                      else call("주다", "청자", "화자", match[4]))
            return call("요청", call("조건", condition, action))
        match = re.fullmatch(r"(\S+) (내일|오늘) (못 )?온대", text)
        if match:
            actor = self.entity(match[1], ("이가", "가", "이"), "people")
            if actor and "embed" not in self.disabled:
                event = call("오다", actor, match[2])
                return call("알림", call("전언", actor, call("불가", event) if match[3] else event))
        match = re.fullmatch(r"(\S+) (\S+) (\S+) 도착했다고 말했어", text)
        if match:
            source = self.entity(match[1], ("이가", "가", "이"), "people")
            recipient = self.entity(match[2], ("이에게", "이한테", "에게", "한테"), "people")
            actor = self.entity(match[3], ("이가", "가", "이"), "people")
            if source and recipient and actor and "embed" not in self.disabled:
                return call("알림", call("전달하다", source, recipient, call("도착하다", actor)))
        return self.loan(text)
