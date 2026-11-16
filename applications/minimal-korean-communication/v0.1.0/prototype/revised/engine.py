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
        self.meeting = None

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
        if len(words) < 4 or words[-1] not in self.lex["loan_verbs"]:
            return None
        roles = {}
        endings = {"subject": (("이가", "이는", "가", "이", "는", "은"), "people"),
                   "other": (("이한테", "이에게", "한테", "에게"), "people"),
                   "object": (("를", "을"), "objects")}
        noun_phrases = words[:-1]
        if len(noun_phrases) != 3:
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
        if set(roles) != set(endings) or "bind" in self.disabled:
            return None
        subject, other = roles["subject"], roles["other"]
        if self.lex["loan_verbs"][words[-1]] == "receive":
            subject, other = other, subject
        return self.record(call("빌려주다", subject, other, roles["object"]))

    def step(self, text):
        text = clean(text)
        match = re.fullmatch(r"(.+?) (한 잔|두 잔|세 개) 주세요", text)
        if match and match[1] in self.lex["objects"]:
            return call("요청", call("주다", "청자", "화자", match[1].replace(" ", ""),
                                    self.lex["quantities"][match[2]]))
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
                self.meeting = dict(zip(("날짜", "시각", "장소"), match.groups()))
            return call("제안", call("만나다", "우리", *match.groups()))
        match = re.fullmatch(r"(날짜|장소)는 (.+?)(?:이야|야)", text)
        if match:
            if self.meeting is None or "update" in self.disabled:
                return "확인(어느약속)"
            role, value = match.groups()
            self.meeting = {**self.meeting, role: value}
            return call("정정", call("만나다", "우리", *self.meeting.values()))
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
